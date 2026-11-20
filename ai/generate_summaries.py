# Purpose: Ask Claude for a short, plain-language summary of each TEST month's
#          prediction and save the summaries to the ai_summaries table.
# Run after model/train_model.py, because it reads the predictions table.

import os  # reads the settings that load_dotenv puts into the environment
import re  # finds patterns in text (used to count sentences and find numbers)
import sys  # lets the script stop with an error code
from datetime import datetime  # records when the summaries were made
from decimal import ROUND_HALF_UP, Decimal  # rounds .5 up, e.g. 62,468.50 -> 62,469
from pathlib import Path  # builds file paths that work on any computer

import anthropic  # the official Claude API package
import pandas as pd
import psycopg2  # talks to PostgreSQL
from dotenv import load_dotenv  # reads the .env file

# A small, low-cost model is enough for short, repetitive summaries.
MODEL = "claude-haiku-5-5"

# If a reply fails the checks below, ask once more before giving up.
MAX_ATTEMPTS = 2

# Finds numbers such as 2017, 46,221 or 1.3962 (commas only between digit groups).
NUMBER_PATTERN = r"\d+(?:,\d{3})*(?:\.\d+)?"

# Limits for each summary, so a manager can scan it quickly.
SENTENCES_REQUIRED = 2
MAX_WORDS = 54  # "under 55 words"


def whole_number(value):
    """Format a number as a whole number with commas, rounding .5 up.

    Python's normal rounding sends .5 to the nearest EVEN number, so 62,468.50
    would show as 62,468. ROUND_HALF_UP gives the conventional 62,469 instead.
    (For negative numbers it rounds away from zero: -16,247.50 -> -16,248.)
    """
    rounded = Decimal(str(value)).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    return f"{int(rounded):,}"

# --- 1. Settings --------------------------------------------------------------
# Read .env from the project folder. The values (including the API key) are
# never printed.
project_root = Path(__file__).resolve().parent.parent
load_dotenv(project_root / ".env")

for setting_name in ["DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD", "ANTHROPIC_API_KEY"]:
    if not os.getenv(setting_name):
        raise SystemExit(f"Error: the setting {setting_name} is missing from .env")


def connect():
    """Open a new PostgreSQL connection using the .env settings."""
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT"),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
    )


def read_table(cursor, sql):
    """Run one query and return the results as a pandas DataFrame."""
    cursor.execute(sql)
    rows = cursor.fetchall()  # every row, as a list of tuples

    # cursor.description has one entry per column; the first item is its name.
    column_names = []
    for column in cursor.description:
        column_names.append(column[0])
    return pd.DataFrame(rows, columns=column_names)


# --- 2. Read the test rows and the train rows ---------------------------------
# Test months: predictions + the features the model used + a readable month.
TEST_ROWS_SQL = """
    SELECT
        p.month_id,
        m.month_start,
        m.month_number,
        p.actual,
        p.predicted,
        p.error,
        f.crossings_lag1,
        f.crossings_rolling_3,
        f.national_travel_lag1,
        f.usd_cad_rate_lag1,
        f.is_spring,
        f.is_summer,
        f.is_fall
    FROM predictions AS p
    JOIN ml_features_crossings AS f ON p.month_id = f.month_id
    JOIN dim_month AS m ON p.month_id = m.month_id
    WHERE p.split = 'test'
    ORDER BY p.month_id
"""

# Train months ONLY: used for the historical averages. Validate and test
# results are never used to build these comparisons.
TRAIN_ROWS_SQL = """
    SELECT month_number, statewide_crossings
    FROM ml_features_crossings
    WHERE split = 'train'
"""

connection = connect()
try:
    cursor = connection.cursor()
    test_rows = read_table(cursor, TEST_ROWS_SQL)
    train_rows = read_table(cursor, TRAIN_ROWS_SQL)
    cursor.close()
finally:
    # Close now: the API calls below can take a while, and we don't need the
    # database until it is time to save.
    connection.close()

print(f"Test rows found: {len(test_rows)}")
print(f"Train rows used for historical averages: {len(train_rows)}")
if test_rows.empty or train_rows.empty:
    raise SystemExit("Error: test or train rows are missing. Run model/train_model.py first.")


# --- 3. Historical averages from the train rows -------------------------------
def season_name(month_number):
    """Winter = Dec-Feb, Spring = Mar-May, Summer = Jun-Aug, Fall = Sep-Nov."""
    if month_number in (12, 1, 2):
        return "Winter"
    if month_number in (3, 4, 5):
        return "Spring"
    if month_number in (6, 7, 8):
        return "Summer"
    return "Fall"


train_rows["season"] = train_rows["month_number"].apply(season_name)

# Average (and number of train months) for each calendar month, e.g. every August.
month_averages = train_rows.groupby("month_number")["statewide_crossings"].agg(["mean", "count"])
# Average (and number of train months) for each season.
season_averages = train_rows.groupby("season")["statewide_crossings"].agg(["mean", "count"])


# --- 4. One reusable prompt template ------------------------------------------
# The {curly_brace} names are filled in with each month's facts below.
PROMPT_TEMPLATE = """You are writing for the CEO of a Montana destination organization.
Write exactly 2 plain-language sentences, under 55 words in total, as one paragraph
that a manager can scan in a few seconds.

Sentence 1: State the predicted crossings, the actual crossings, and whether the
model predicted too high or too low.
Sentence 2: Give only the single most useful explanation for the miss that the
supplied patterns support, such as how the actual result compares with the
historical training average for this month or season, or with recent months.

Rules:
- Pick one explanation. Do not list every pattern or feature.
- Say "historical training data" when referring to the training period. Do not
  name years or a year range.
- Use only the facts listed below. Do not mention weather, politics, events,
  marketing, border policies or any other outside information.
- Use cautious language such as "may have", "appears to" or "suggests". Never say a
  pattern or feature caused travel to change.
- The numbers count inbound personal-vehicle passengers crossing from Canada into
  Montana. Do not describe them as confirmed tourists or as Canadian residents.
- Copy numbers exactly as written below. Do not calculate new numbers, differences
  or percentages.
- Return plain text only: no line breaks, no heading, no Markdown.

Facts for {month}:
- Predicted crossings: {predicted}
- Actual crossings: {actual}
- Direction of the miss: the model predicted too {direction} by {miss_size}
- Prediction error (actual minus predicted): {error}
- Previous month's Montana crossings: {crossings_lag1}
- Average Montana crossings over the previous three months: {crossings_rolling_3}
- Season: {season} (season indicators: is_spring={is_spring}, is_summer={is_summer}, is_fall={is_fall})
- Historical training data average for {month_name} ({month_count} {month_name} months): {month_average}
- Historical training data average for {season} months ({season_count} months): {season_average}
- Previous month's national count of Canadian residents returning from the U.S. by automobile: {national_travel_lag1}
- Previous month's exchange rate (Canadian dollars per U.S. dollar): {usd_cad_rate_lag1}
"""


def build_facts(row):
    """Collect one month's facts as text, rounded half up, with commas."""
    month_number = int(row["month_number"])
    season = season_name(month_number)
    if row["predicted"] > row["actual"]:
        direction = "high"
    else:
        direction = "low"

    return {
        "month": f"{row['month_start']:%B %Y}",
        "month_name": f"{row['month_start']:%B}",
        "predicted": whole_number(row["predicted"]),
        "actual": whole_number(row["actual"]),
        "direction": direction,
        "miss_size": whole_number(abs(row["error"])),
        "error": whole_number(row["error"]),
        "crossings_lag1": whole_number(row["crossings_lag1"]),
        "crossings_rolling_3": whole_number(row["crossings_rolling_3"]),
        "season": season,
        "is_spring": row["is_spring"],
        "is_summer": row["is_summer"],
        "is_fall": row["is_fall"],
        "month_count": int(month_averages.loc[month_number, "count"]),
        "month_average": whole_number(month_averages.loc[month_number, "mean"]),
        "season_count": int(season_averages.loc[season, "count"]),
        "season_average": whole_number(season_averages.loc[season, "mean"]),
        "national_travel_lag1": whole_number(row["national_travel_lag1"]),
        "usd_cad_rate_lag1": f"{row['usd_cad_rate_lag1']:.4f}",
    }


def check_summary(summary, facts):
    """Return a problem description, or None if the summary looks right."""
    if not summary:
        return "the summary is empty"
    # One paragraph: no line breaks at all.
    if "\n" in summary:
        return "the summary has more than one paragraph or line"
    # Markdown signs: headings (#), bold (**), or text starting with a bullet.
    if "#" in summary or "**" in summary or re.match(r"\s*[-*] ", summary):
        return "the summary contains Markdown"
    # A sentence ends with . ! or ? followed by a space or the end of the text.
    # (Decimals such as 1.3962 are not counted, because no space follows the dot.)
    sentence_count = len(re.findall(r"[.!?](\s|$)", summary))
    if sentence_count != SENTENCES_REQUIRED:
        return f"the summary has {sentence_count} sentences instead of {SENTENCES_REQUIRED}"
    # Words are the pieces of text separated by spaces.
    word_count = len(summary.split())
    if word_count > MAX_WORDS:
        return f"the summary has {word_count} words (limit {MAX_WORDS})"

    # Every number in the summary must be one of the supplied facts.
    # Small whole numbers (0-12) are allowed for counts such as "five Augusts".
    allowed_numbers = set()
    for value in facts.values():
        for number in re.findall(NUMBER_PATTERN, str(value)):
            allowed_numbers.add(number)
    for number in re.findall(NUMBER_PATTERN, summary):
        if number not in allowed_numbers and not (number.isdigit() and int(number) <= 12):
            return f"the summary contains the number {number}, which is not in the facts"
    return None


# --- 5. Ask Claude for every summary (one API call per test row) --------------
# anthropic.Anthropic() reads ANTHROPIC_API_KEY from the environment, which
# load_dotenv filled from .env. The key is never printed.
client = anthropic.Anthropic()

summaries = []  # (month_id, summary) pairs, saved only after ALL are checked
api_calls = 0
input_tokens = 0
output_tokens = 0

for index, row in test_rows.iterrows():
    facts = build_facts(row)
    prompt = PROMPT_TEMPLATE.format(**facts)
    month_label = facts["month"]

    # Try up to MAX_ATTEMPTS times; stop the loop as soon as a reply passes.
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = client.messages.create(
                model=MODEL,
                # A ceiling, not a target: the model's thinking counts toward it,
                # so leave room for thinking plus the short answer. Only the
                # tokens actually used are billed.
                max_tokens=4096,
                # "low" effort keeps a simple task fast and inexpensive.
                output_config={"effort": "low"},
                messages=[{"role": "user", "content": prompt}],
            )
        except anthropic.APIStatusError as error:
            # Shows only the status code and error type, never the API key.
            raise SystemExit(
                f"Error: the Claude API returned status {error.status_code} "
                f"({type(error).__name__}) for {month_label}. Nothing was saved."
            )
        except anthropic.APIConnectionError:
            raise SystemExit(f"Error: could not reach the Claude API for {month_label}. Nothing was saved.")

        api_calls += 1
        input_tokens += response.usage.input_tokens
        output_tokens += response.usage.output_tokens

        # The reply is a list of blocks; keep only the text blocks.
        text_parts = []
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
        summary = " ".join(text_parts).strip()

        # "end_turn" means Claude finished normally (not cut off or declined).
        if response.stop_reason != "end_turn":
            problem = f"Claude stopped early (stop_reason = {response.stop_reason})"
        else:
            problem = check_summary(summary, facts)

        if problem is None:
            break  # this reply passed every check
        print(f"  {month_label}, attempt {attempt}: {problem}")

    if problem is not None:
        # Report the tokens used so far, so the cost of a failed run is known.
        print(f"API calls made: {api_calls}")
        print(f"Tokens used: {input_tokens:,} input, {output_tokens:,} output")
        raise SystemExit(f"Error: no valid summary for {month_label}. Nothing was saved.\n{summary}")

    summaries.append((int(row["month_id"]), summary))

print(f"API calls made: {api_calls}")
print(f"Tokens used: {input_tokens:,} input, {output_tokens:,} output")


# --- 6. Save all summaries in one transaction ---------------------------------
generated_at = datetime.now()
summary_rows = []
for month_id, summary in summaries:
    summary_rows.append((month_id, summary, generated_at))

connection = None
try:
    connection = connect()
    cursor = connection.cursor()

    # Empty the table first, so a rerun never creates duplicates.
    # psycopg2 starts a transaction automatically; nothing is final until commit.
    cursor.execute("TRUNCATE TABLE ai_summaries")
    cursor.executemany(
        "INSERT INTO ai_summaries (month_id, summary, generated_at) VALUES (%s, %s, %s)",
        summary_rows,
    )

    # Check the count before committing: one summary per test row.
    cursor.execute("SELECT COUNT(*) FROM ai_summaries")
    saved_count = cursor.fetchone()[0]
    if saved_count != len(test_rows):
        raise ValueError(f"ai_summaries has {saved_count} rows, but there are {len(test_rows)} test rows")

    # Nothing is saved until this line.
    connection.commit()
    print(f"Summaries saved: {saved_count}")

except (psycopg2.Error, ValueError) as error:
    if connection is not None:
        connection.rollback()
    print("Error: saving failed and was rolled back. The old summaries were kept.")
    print(f"Details: {type(error).__name__}")
    sys.exit(1)

finally:
    if connection is not None:
        connection.close()


# --- 7. Show three samples for a manual check ---------------------------------
# The first, middle and last test months.
summary_lookup = dict(summaries)
sample_positions = [0, len(test_rows) // 2, len(test_rows) - 1]

print()
print("Sample summaries for review:")
for position in sample_positions:
    row = test_rows.iloc[position]
    print()
    summary = summary_lookup[int(row["month_id"])]
    print(
        f"{row['month_start']:%B %Y} | actual {whole_number(row['actual'])} | "
        f"predicted {whole_number(row['predicted'])} | {len(summary.split())} words"
    )
    print(summary)
