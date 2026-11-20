# Montana Border Crossings Dashboard
#   Page 1: "What Happened?"
#   Page 2: "How Good Are the Predictions?"
#   Page 3: "What Should We Do?"
#   Page 4: "Explore Border Ports"
# Every number on these pages comes live from our PostgreSQL database.
# Page 3 also loads the saved model file; the dashboard never retrains it.

import os  # reads the settings that load_dotenv puts into the environment
from decimal import ROUND_HALF_UP, Decimal  # rounds .5 up, e.g. 62,468.50 -> 62,469
from pathlib import Path  # builds file paths that work on any computer

import altair as alt  # draws charts (installed together with Streamlit)
import joblib  # loads the saved model file
import pandas as pd
import psycopg2  # talks to PostgreSQL
import streamlit as st
from dotenv import load_dotenv  # reads the .env file

# The seasons in calendar order. We use this list to keep charts in this order.
SEASON_ORDER = ["Winter", "Spring", "Summer", "Fall"]

# Page 1 SQL: add up passenger crossings across all ports for each month.
# The CASE statement labels each month with its season.
MONTHLY_TOTALS_SQL = """
    SELECT
        m.month_start,
        m.year,
        CASE
            WHEN m.month_number IN (12, 1, 2) THEN 'Winter'
            WHEN m.month_number IN (3, 4, 5)  THEN 'Spring'
            WHEN m.month_number IN (6, 7, 8)  THEN 'Summer'
            ELSE 'Fall'
        END AS season,
        SUM(f.passenger_crossings) AS total_crossings
    FROM fact_border_crossings AS f
    JOIN dim_month AS m ON f.month_id = m.month_id
    GROUP BY m.month_start, m.year, m.month_number
    ORDER BY m.month_start
"""

# Page 2 SQL: the model's predictions for the validate and test months ONLY.
# Train rows are left out because the model already saw them while learning,
# so they would make the model look better than it really is.
EVALUATION_SQL = """
    SELECT
        m.month_start,
        m.month_number,
        p.split,
        p.actual,
        p.predicted
    FROM predictions AS p
    JOIN dim_month AS m ON p.month_id = m.month_id
    WHERE p.split IN ('validate', 'test')
    ORDER BY m.month_start
"""

# Page 2 SQL: the baseline guess is the average month in the TRAINING data.
TRAIN_AVERAGE_SQL = """
    SELECT AVG(statewide_crossings) AS train_average
    FROM ml_features_crossings
    WHERE split = 'train'
"""

# Page 3 SQL: the saved AI summaries for the test months. The dashboard only
# reads these from PostgreSQL; it never calls the Claude API itself.
AI_SUMMARIES_SQL = """
    SELECT
        m.month_start,
        a.summary,
        a.generated_at
    FROM ai_summaries AS a
    JOIN predictions AS p ON a.month_id = p.month_id
    JOIN dim_month AS m ON a.month_id = m.month_id
    WHERE p.split = 'test'
    ORDER BY m.month_start
"""

# Page 4 SQL: passenger crossings for every port in every month.
PORT_MONTHLY_SQL = """
    SELECT
        m.month_start,
        m.year,
        p.port_code,
        p.port_name,
        f.passenger_crossings
    FROM fact_border_crossings AS f
    JOIN dim_port AS p ON f.port_code = p.port_code
    JOIN dim_month AS m ON f.month_id = m.month_id
    ORDER BY m.month_start, p.port_name
"""

# Page 3: recommendations use months from this year onward, so the averages are
# not dominated by the COVID closure or the higher pre-COVID traffic.
RECENT_START_YEAR = 2022

# Page 3: the saved model file that model/train_model.py creates.
MODEL_PATH = Path(__file__).resolve().parent.parent / "model" / "crossings_model.joblib"

# Page 3: the model's inputs, in the exact order the model was trained with.
FEATURE_COLUMNS = [
    "usd_cad_rate_lag1",
    "national_travel_lag1",
    "crossings_lag1",
    "crossings_rolling_3",
    "is_spring",
    "is_summer",
    "is_fall",
]

# Page 3 SQL: the Random Forest's average miss (MAE) on the test months only.
TEST_MAE_SQL = """
    SELECT
        AVG(ABS(actual - predicted)) AS test_mae,
        COUNT(*) AS test_months
    FROM predictions
    WHERE split = 'test'
"""

# Page 3 SQL: automatic inputs for the prediction tool. For every month it finds
# the exchange rate, national travel count, statewide crossings, and the average
# crossings over that month and the two before it. It keeps only months that
# have all of them. These are the "previous month" values for a target month.
INPUT_MONTHS_SQL = """
    WITH statewide AS (
        SELECT month_id, SUM(passenger_crossings) AS crossings
        FROM fact_border_crossings
        GROUP BY month_id
    ),
    by_month AS (
        SELECT
            m.month_start,
            e.usd_cad_rate,
            t.canadian_auto_return_trips,
            s.crossings,
            AVG(s.crossings) OVER three_months AS crossings_average_3,
            COUNT(s.crossings) OVER three_months AS crossing_months_3,
            LAG(m.month_start, 2) OVER (ORDER BY m.month_start) AS two_months_earlier
        FROM dim_month AS m
        LEFT JOIN statewide AS s ON m.month_id = s.month_id
        LEFT JOIN fact_exchange_rates AS e ON m.month_id = e.month_id
        LEFT JOIN fact_national_travel AS t ON m.month_id = t.month_id
        WINDOW three_months AS (
            ORDER BY m.month_start ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
        )
    )
    SELECT *
    FROM by_month
    WHERE usd_cad_rate IS NOT NULL
      AND canadian_auto_return_trips IS NOT NULL
      AND crossings IS NOT NULL
      AND crossing_months_3 = 3
      -- the three rows must be three back-to-back calendar months
      AND two_months_earlier = month_start - INTERVAL '2 months'
    ORDER BY month_start
"""


def run_query(sql):
    """Run one SQL query and return the results as a pandas DataFrame."""
    # Read .env from the project folder (one level up from this dashboard folder).
    # The values are never printed or shown on the page.
    project_root = Path(__file__).resolve().parent.parent
    load_dotenv(project_root / ".env")

    connection = psycopg2.connect(
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT"),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
    )
    try:
        cursor = connection.cursor()
        cursor.execute(sql)
        rows = cursor.fetchall()  # every row, as a list of tuples

        # cursor.description has one entry per column; the first item is its name.
        column_names = []
        for column in cursor.description:
            column_names.append(column[0])

        cursor.close()
    finally:
        # "finally" always runs, so the connection is closed even after an error.
        connection.close()

    return pd.DataFrame(rows, columns=column_names)


def whole_number(value):
    """Format a number as a whole number with commas, rounding .5 up.

    Python's normal rounding sends .5 to the nearest EVEN number, so 62,468.50
    would show as 62,468. ROUND_HALF_UP gives the conventional 62,469, which
    also matches how the chart tooltips round.
    """
    rounded = Decimal(str(value)).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    return f"{int(rounded):,}"


def show_database_error(error):
    """Show a friendly error without any connection details or the password."""
    # Only the type of error is shown, not its full text.
    st.error(
        "Could not load data from PostgreSQL "
        f"({type(error).__name__}). Check that the database is running "
        "and that the settings in .env are correct."
    )
    st.stop()  # nothing else on the page can work without data


def season_for_month(month_number):
    """Return the season name for a month number (1 = January)."""
    if month_number in (12, 1, 2):
        return "Winter"
    if month_number in (3, 4, 5):
        return "Spring"
    if month_number in (6, 7, 8):
        return "Summer"
    return "Fall"


def season_indicators(month_number):
    """Build the three 0/1 season fields the model was trained with.

    Winter is the baseline season, so a winter month has all three set to 0.
    """
    season = season_for_month(month_number)
    return {
        "is_spring": 1 if season == "Spring" else 0,
        "is_summer": 1 if season == "Summer" else 0,
        "is_fall": 1 if season == "Fall" else 0,
    }


# =============================================================================
# Page 1: What Happened?
# =============================================================================
def show_page_1():
    # --- Page heading ---------------------------------------------------------
    st.title("What Happened?")
    st.write(
        "How have inbound passenger crossings at Montana's Canadian border "
        "changed over time and by season?"
    )

    # --- Load the data --------------------------------------------------------
    try:
        monthly = run_query(MONTHLY_TOTALS_SQL)
    except psycopg2.Error as error:
        show_database_error(error)
    # Turn the date column into a pandas date so the line chart reads it as time.
    monthly["month_start"] = pd.to_datetime(monthly["month_start"])

    # --- Year filters ---------------------------------------------------------
    # The list of years comes from the data, not typed into the code.
    available_years = sorted(monthly["year"].unique().tolist())

    # st.columns(2) makes two side-by-side spaces for the dropdowns.
    left_column, right_column = st.columns(2)
    with left_column:
        # index=0 starts on the first (earliest) year.
        start_year = st.selectbox("Start year", available_years, index=0)
    with right_column:
        # index=len(...) - 1 starts on the last (latest) year.
        end_year = st.selectbox(
            "End year", available_years, index=len(available_years) - 1
        )

    # Data note about the latest year, built from the newest month in the data
    # so it stays correct when new months are loaded.
    latest_month = monthly["month_start"].max()
    if latest_month.month != 12:
        st.info(
            f"Data note: {latest_month.year} data currently runs through "
            f"{latest_month:%B}. Seasonal averages involving {latest_month.year} "
            "use only the months available."
        )

    # Stop here if the years are in the wrong order.
    if start_year > end_year:
        st.warning(
            "The start year must be the same as or earlier than the end year. "
            "Please change your selection."
        )
        st.stop()

    # Keep only the months inside the chosen years. Both charts use this table.
    selected = monthly[(monthly["year"] >= start_year) & (monthly["year"] <= end_year)]

    # Caption naming the first and last months actually shown.
    first_shown = selected["month_start"].min()
    last_shown = selected["month_start"].max()
    st.caption(f"Showing {first_shown:%B %Y} through {last_shown:%B %Y}.")

    # --- Chart 1: monthly crossings over time --------------------------------
    st.subheader("Monthly Passenger Crossings Statewide")

    line_chart = (
        alt.Chart(selected)
        .mark_line()
        .encode(
            x=alt.X("month_start:T", title="Month"),
            # format=",.0f" shows whole numbers with commas, e.g. 100,000
            y=alt.Y(
                "total_crossings:Q",
                title="Passenger crossings",
                axis=alt.Axis(format=",.0f"),
            ),
            tooltip=[
                alt.Tooltip("month_start:T", title="Month", format="%B %Y"),
                alt.Tooltip("total_crossings:Q", title="Crossings", format=","),
            ],
        )
    )
    st.altair_chart(line_chart, width="stretch")
    st.write(
        "Each point is the total number of inbound passengers who crossed into "
        "Montana from Canada in one month, added up across all ports."
    )

    # --- Chart 2: average monthly crossings by season ------------------------
    st.subheader("Average Monthly Passenger Crossings by Season")

    # Average the monthly totals within each season.
    season_averages = selected.groupby("season", as_index=False)[
        "total_crossings"
    ].mean()

    # The bars and their labels share the same x and y settings, so we set them once.
    base = alt.Chart(season_averages).encode(
        # sort=SEASON_ORDER keeps the bars in calendar order, not alphabetical.
        x=alt.X("season:N", title="Season", sort=SEASON_ORDER),
        # format=",.0f" shows whole numbers with commas, e.g. 100,000
        y=alt.Y(
            "total_crossings:Q",
            title="Average monthly crossings",
            axis=alt.Axis(format=",.0f"),
        ),
    )

    bars = base.mark_bar().encode(
        tooltip=[
            alt.Tooltip("season:N", title="Season"),
            alt.Tooltip("total_crossings:Q", title="Average per month", format=",.0f"),
        ],
    )

    # Text placed just above each bar showing its average, e.g. 110,966
    labels = base.mark_text(baseline="bottom", dy=-4).encode(
        text=alt.Text("total_crossings:Q", format=",.0f"),
    )

    # "+" draws the labels on top of the bars as one chart.
    st.altair_chart(bars + labels, width="stretch")
    st.write(
        "Each bar shows how many inbound passengers crossed in a typical month of "
        "that season during the selected years (Winter = Dec-Feb, Spring = Mar-May, "
        "Summer = Jun-Aug, Fall = Sep-Nov)."
    )


# =============================================================================
# Page 2: How Good Are the Predictions?
# =============================================================================
def show_page_2():
    # --- Page heading ---------------------------------------------------------
    st.title("How Good Are the Predictions?")
    st.write("Can we trust the model, and where does it make its largest errors?")

    # --- Load the data --------------------------------------------------------
    try:
        results = run_query(EVALUATION_SQL)
        train_average_table = run_query(TRAIN_AVERAGE_SQL)
    except psycopg2.Error as error:
        show_database_error(error)

    # PostgreSQL returns NUMERIC values as Decimals; float() makes them normal numbers.
    results["actual"] = results["actual"].astype(float)
    results["predicted"] = results["predicted"].astype(float)
    train_average = float(train_average_table["train_average"][0])

    # A readable month for tables and tooltips, e.g. "August 2026".
    results["month"] = pd.to_datetime(results["month_start"]).dt.strftime("%B %Y")

    # error = actual - predicted. A negative error means the model guessed too high.
    results["error"] = results["actual"] - results["predicted"]
    results["absolute_error"] = results["error"].abs()

    # MAE (mean absolute error) = the average size of the misses.
    model_mae = results["absolute_error"].mean()

    # The baseline guesses the same training average for every month.
    baseline_mae = (results["actual"] - train_average).abs().mean()

    # --- Section 1: predicted vs. actual -------------------------------------
    st.subheader("Predicted vs. Actual Monthly Crossings")

    # Use the same range on both axes so the diagonal line sits at 45 degrees.
    axis_max = max(results["actual"].max(), results["predicted"].max()) * 1.05
    same_scale = alt.Scale(domain=[0, axis_max])

    points = (
        alt.Chart(results)
        .mark_circle(size=80)
        .encode(
            x=alt.X(
                "actual:Q",
                title="Actual crossings",
                scale=same_scale,
                axis=alt.Axis(format=",.0f"),
            ),
            y=alt.Y(
                "predicted:Q",
                title="Predicted crossings",
                scale=same_scale,
                axis=alt.Axis(format=",.0f"),
            ),
            # One color for validate months and another for test months.
            color=alt.Color(
                "split:N",
                title="Split",
                scale=alt.Scale(domain=["validate", "test"]),
            ),
            tooltip=[
                alt.Tooltip("month:N", title="Month"),
                alt.Tooltip("split:N", title="Split"),
                alt.Tooltip("actual:Q", title="Actual", format=",.0f"),
                alt.Tooltip("predicted:Q", title="Predicted", format=",.0f"),
                alt.Tooltip(
                    "error:Q", title="Error (actual - predicted)", format=",.0f"
                ),
            ],
        )
    )

    # A dashed line from (0, 0) to the top corner, where predicted = actual.
    diagonal_points = pd.DataFrame(
        {"actual": [0, axis_max], "predicted": [0, axis_max]}
    )
    diagonal = (
        alt.Chart(diagonal_points)
        .mark_line(color="gray", strokeDash=[6, 4])
        .encode(x="actual:Q", y="predicted:Q")
    )

    st.altair_chart(diagonal + points, width="stretch")
    st.write(
        "Each dot is one month the model did not learn from; dots closer to the "
        "dashed diagonal line are more accurate, and dots above the line are months "
        "the model predicted too high."
    )

    # --- Section 2: model MAE vs. baseline MAE -------------------------------
    st.subheader("Model Error Compared with a Simple Baseline")

    # st.columns(2) puts the two numbers side by side.
    left_column, right_column = st.columns(2)
    with left_column:
        st.metric("Random Forest MAE", whole_number(model_mae))
    with right_column:
        st.metric("Baseline MAE (training average)", whole_number(baseline_mae))

    # Explain the comparison in plain language.
    difference = baseline_mae - model_mae
    if difference > 0:
        percent_better = difference / baseline_mae * 100
        st.write(
            f"On the {len(results)} validate and test months, the model's predictions "
            f"were off by {whole_number(difference)} fewer crossings per month on average than "
            f"always guessing the training average of {whole_number(train_average)}, "
            f"about {percent_better:.0f}% less error."
        )
    else:
        st.write(
            f"On the {len(results)} validate and test months, the model did not beat "
            f"always guessing the training average of {whole_number(train_average)}."
        )

    # --- Section 3: biggest misses -------------------------------------------
    st.subheader("Five Biggest Misses")

    # How many times bigger each miss is than the model's typical (average) miss.
    results["times_model_mae"] = results["absolute_error"] / model_mae
    # A miss more than twice the typical miss is marked as unusual.
    results["unusual"] = results["absolute_error"] > 2 * model_mae

    # Sort from largest to smallest miss and keep the top five.
    biggest_misses = results.sort_values("absolute_error", ascending=False).head(5)

    table = biggest_misses[
        [
            "month",
            "split",
            "actual",
            "predicted",
            "absolute_error",
            "times_model_mae",
            "unusual",
        ]
    ].copy()
    table["unusual"] = table["unusual"].map({True: "Yes", False: "No"})

    # .style.format controls how numbers look: whole numbers with commas
    # (rounded half up), and two decimals for the ratio.
    st.dataframe(
        table.style.format(
            {
                "actual": whole_number,
                "predicted": whole_number,
                "absolute_error": whole_number,
                "times_model_mae": "{:.2f}",
            }
        ),
        hide_index=True,
    )

    # --- Section 4: explain the largest unusual miss -------------------------
    unusual_misses = biggest_misses[biggest_misses["unusual"]]
    if unusual_misses.empty:
        st.write("None of the validate or test months had an unusually large miss.")
    else:
        # The table is sorted, so the first unusual row is the largest one.
        worst = unusual_misses.iloc[0]
        if worst["predicted"] > worst["actual"]:
            direction = "too high"
        else:
            direction = "too low"
        summary = (
            f"The largest unusual miss was {worst['month']}, when the model predicted "
            f"{whole_number(worst['predicted'])} crossings but {whole_number(worst['actual'])} actually "
            f"crossed, about {worst['times_model_mae']:.1f} times its typical error and "
            f"{direction}."
        )

        # Only give the project's explanation when it fits: a summer overprediction.
        if worst["month_number"] in (6, 7, 8) and direction == "too high":
            month_name = worst["month"].split()[0]  # e.g. "August 2026" -> "August"
            reason = (
                " A possible model limitation, not a proven cause: the model relied "
                "heavily on the summer indicator and on the higher pre-COVID summer "
                "crossing levels in its training data, so it may not have fully "
                f"captured the lower {month_name} traffic seen in recent years."
            )
        else:
            reason = " The project's analysis did not identify a cause for this miss."
        st.write(summary + reason)


# =============================================================================
# Page 3: What Should We Do?
# =============================================================================
def show_page_3():
    # --- Page heading ---------------------------------------------------------
    st.title("What Should We Do?")
    st.write(
        "Based on predicted border traffic, should the organization adjust "
        "marketing aimed at Canadian travelers?"
    )

    # --- Load the data --------------------------------------------------------
    try:
        monthly = run_query(MONTHLY_TOTALS_SQL)
        test_mae_table = run_query(TEST_MAE_SQL)
        input_months = run_query(INPUT_MONTHS_SQL)
    except psycopg2.Error as error:
        show_database_error(error)

    if test_mae_table["test_months"][0] == 0:
        st.warning("No test predictions are saved yet. Run model/train_model.py first.")
        st.stop()

    # PostgreSQL returns AVG as a Decimal; float() makes it a normal number.
    test_mae = float(test_mae_table["test_mae"][0])
    test_months = int(test_mae_table["test_months"][0])

    # Recent months only, then the average monthly crossings in each season.
    monthly["month_start"] = pd.to_datetime(monthly["month_start"])
    recent = monthly[monthly["year"] >= RECENT_START_YEAR]
    recent_averages = recent.groupby("season")["total_crossings"].mean()

    summer_average = recent_averages["Summer"]
    winter_average = recent_averages["Winter"]
    # The lower-demand season is whichever of fall and winter has fewer crossings.
    if recent_averages["Fall"] < winter_average:
        low_season = "Fall"
    else:
        low_season = "Winter"
    low_average = recent_averages[low_season]

    # --- Section 1: recommendations ------------------------------------------
    st.subheader("Recommendations")
    st.caption(
        f"Based on monthly crossings from {recent['month_start'].min():%B %Y} through "
        f"{recent['month_start'].max():%B %Y}. Starting in {RECENT_START_YEAR} keeps the "
        "averages from being dominated by the COVID border closure or the higher "
        "pre-COVID traffic."
    )
    st.markdown(
        f"1. **Seasonal planning:** Since {RECENT_START_YEAR}, an average summer month "
        f"has had **{whole_number(summer_average)}** crossings, compared with "
        f"**{whole_number(winter_average)}** in an average winter month. Plan Canadian "
        "campaigns in spring so they are running before the higher-demand summer period.\n"
        f"2. **Lower-demand promotion:** An average {low_season.lower()} month has had "
        f"**{whole_number(low_average)}** crossings since {RECENT_START_YEAR}, about "
        f"{low_average / summer_average:.0%} of the summer level. Targeted offers aimed at "
        f"Canadian travelers could help support these lower-demand months.\n"
        f"3. **Flexible budgeting:** On the {test_months} test months, the Random "
        f"Forest's predictions missed by **{whole_number(test_mae)}** crossings on "
        "average (test MAE). Plan around a range of about that much above and below a "
        "forecast, rather than treating it as an exact count."
    )

    # --- Section 2: model limit ----------------------------------------------
    st.subheader("Model Limit")
    st.warning(
        "The border-crossing data counts all inbound personal-vehicle passengers, not "
        "confirmed Canadian tourists. The forecast should be used as an indicator of "
        "travel demand, not an exact visitor count."
    )

    # --- Section 3: future prediction tool -----------------------------------
    st.subheader("Predict Next Month")
    show_prediction_tool(input_months, recent_averages, test_mae)

    # --- Section 4: AI summary for one test month ----------------------------
    show_ai_summary()


def show_prediction_tool(input_months, recent_averages, test_mae):
    """The Page 3 prediction form. It uses the saved model and never retrains it.

    It uses "return" instead of st.stop() when something is missing, so the
    AI summary section below it still shows.
    """
    # Load the model saved by model/train_model.py.
    if not MODEL_PATH.exists():
        st.error(
            "The saved model file was not found. Run model/train_model.py to "
            "create model/crossings_model.joblib."
        )
        return
    bundle = joblib.load(MODEL_PATH)
    model = bundle["model"]
    saved_features = list(bundle["feature_names"])

    # The inputs must have exactly the same names, in the same order, as training.
    if saved_features != FEATURE_COLUMNS or list(model.feature_names_in_) != FEATURE_COLUMNS:
        st.error(
            "Prediction stopped: the dashboard's feature names or their order do not "
            "match the saved model. Rerun model/train_model.py, or update "
            "FEATURE_COLUMNS in dashboard/app.py to match."
        )
        st.write(f"Saved with the model: {saved_features}")
        st.write(f"Used by the dashboard: {FEATURE_COLUMNS}")
        return

    if input_months.empty:
        st.warning("The database has no month with all the inputs the model needs.")
        return

    # --- Prediction month -----------------------------------------------------
    # The model predicts one month ahead, so the prediction month is the next
    # calendar month after today. The month and year are labels only.
    this_month = pd.Timestamp.today().normalize().replace(day=1)
    prediction_month = this_month + pd.DateOffset(months=1)
    prediction_label = f"{prediction_month:%B %Y}"
    st.markdown(f"**Prediction month: {prediction_label}**")
    st.caption(
        "This model is designed to predict one month ahead. It is not intended to "
        "forecast travel several years into the future."
    )

    # --- Default inputs -------------------------------------------------------
    # The latest complete set of inputs in PostgreSQL (sorted oldest to newest).
    input_months["month_start"] = pd.to_datetime(input_months["month_start"])
    source = input_months.iloc[-1]
    source_label = f"{source['month_start']:%B %Y}"
    st.info(
        f"Default values come from **{source_label}**, the latest month with "
        "complete model inputs in the database. You can change any of them."
    )

    # Warn when the defaults are older than the month just before the prediction.
    if source["month_start"] != prediction_month - pd.DateOffset(months=1):
        st.warning(
            f"The latest complete model inputs are from {source_label}. Update these "
            "values with newer information or reasonable estimates before using this "
            "as a current forecast."
        )

    # The season fields come from the prediction month; winter is all zeros.
    target_season = season_for_month(prediction_month.month)
    indicators = season_indicators(prediction_month.month)

    # --- The four model inputs (editable) -------------------------------------
    left_column, right_column = st.columns(2)
    with left_column:
        exchange_rate = st.number_input(
            "Previous month's USD/CAD exchange rate",
            min_value=0.01,
            value=float(source["usd_cad_rate"]),
            step=0.01,
            format="%.4f",
            help="Canadian dollars per U.S. dollar, averaged over the month. A higher "
            "number means U.S. trips cost Canadians more.",
        )
        national_trips = st.number_input(
            "Previous month's national Canadian automobile trips",
            min_value=0,
            value=int(source["canadian_auto_return_trips"]),
            step=10000,
            help="Canadian residents across Canada who returned from the U.S. by car "
            "(Statistics Canada).",
        )
    with right_column:
        previous_crossings = st.number_input(
            "Previous month's statewide Montana crossings",
            min_value=0,
            value=int(source["crossings"]),
            step=1000,
            help="Inbound personal-vehicle passengers at all Montana ports.",
        )
        three_month_average = st.number_input(
            "Average statewide Montana crossings, previous three months",
            min_value=0.0,
            value=float(source["crossings_average_3"]),
            step=1000.0,
            format="%.2f",
            help="Average monthly crossings over the three months before the "
            "prediction month.",
        )
    st.caption(f"Season used by the model: {target_season}.")

    if st.button("Predict Monthly Crossings"):
        # One row of inputs, with the columns in the exact order the model expects.
        # The month and year are only labels; the model was not trained with them.
        inputs = {
            "usd_cad_rate_lag1": exchange_rate,
            "national_travel_lag1": national_trips,
            "crossings_lag1": previous_crossings,
            "crossings_rolling_3": three_month_average,
            **indicators,
        }
        input_row = pd.DataFrame([inputs], columns=FEATURE_COLUMNS)
        prediction = float(model.predict(input_row)[0])

        # Typical-error planning range; the lower end cannot go below zero.
        range_low = max(0, prediction - test_mae)
        range_high = prediction + test_mae

        st.metric(f"Predicted crossings for {prediction_label}", whole_number(prediction))
        st.write(
            f"Planning range: **{whole_number(range_low)} to {whole_number(range_high)}** "
            f"crossings (the prediction plus or minus the test MAE of {whole_number(test_mae)})."
        )
        st.caption(
            "This is a typical-error planning range based on the model's average miss "
            "on test months. It is not a statistical confidence interval, and actual "
            "crossings can fall outside it."
        )

        # Compare with the recent average for the target month's season.
        # "Meaningfully" different = more than the test MAE away.
        season_average = recent_averages[target_season]
        difference = prediction - season_average
        comparison = (
            f"The prediction is {whole_number(abs(difference))} crossings "
            f"{'below' if difference < 0 else 'above'} the recent {target_season.lower()} "
            f"average of {whole_number(season_average)} (since {RECENT_START_YEAR})."
        )
        if difference < -test_mae:
            st.warning(
                f"{comparison} Consider increased Canadian marketing or targeted "
                "promotions for this month."
            )
        elif difference > test_mae:
            st.success(
                f"{comparison} Maintain visibility with Canadian travelers while "
                "avoiding unnecessary discounting."
            )
        else:
            st.info(
                f"{comparison} That is within the model's typical error, so maintaining "
                "the current marketing level looks reasonable."
            )


def show_ai_summary():
    """Page 3: the saved AI summary for one test month (moved here from Page 2)."""
    st.subheader("AI Summary of a Test Month")

    # This section has its own error handling, so the rest of the page still
    # shows if the summaries have not been generated yet.
    try:
        ai_summaries = run_query(AI_SUMMARIES_SQL)
    except psycopg2.Error:
        ai_summaries = pd.DataFrame()

    if ai_summaries.empty:
        st.info("No AI summaries are saved yet. Run ai/generate_summaries.py to create them.")
    else:
        # A readable month for the dropdown, e.g. "August 2026".
        ai_summaries["month"] = pd.to_datetime(ai_summaries["month_start"]).dt.strftime(
            "%B %Y"
        )
        month_options = ai_summaries["month"].tolist()

        # index=len(...) - 1 starts on the most recent test month.
        chosen_month = st.selectbox(
            "Choose a test month:", month_options, index=len(month_options) - 1
        )
        chosen = ai_summaries[ai_summaries["month"] == chosen_month].iloc[0]

        st.write(chosen["summary"])
        st.caption(
            "Written by Claude (an AI model) using only this month's saved facts, "
            f"on {chosen['generated_at']:%B %d, %Y}. It describes the numbers but "
            "does not prove why crossings changed."
        )


# =============================================================================
# Page 4: Explore Border Ports
# =============================================================================
def show_page_4():
    # --- Page heading ---------------------------------------------------------
    st.title("Explore Border Ports")
    st.write("How do border-crossing patterns differ among Montana's ports of entry?")

    # --- Load the data --------------------------------------------------------
    try:
        port_monthly = run_query(PORT_MONTHLY_SQL)
    except psycopg2.Error as error:
        show_database_error(error)
    port_monthly["month_start"] = pd.to_datetime(port_monthly["month_start"])

    # --- Filters --------------------------------------------------------------
    # The years and ports come from the data, not typed into the code.
    available_years = sorted(port_monthly["year"].unique().tolist())

    # Ports sorted from most to fewest crossings in the complete dataset.
    port_totals = (
        port_monthly.groupby("port_name")["passenger_crossings"]
        .sum()
        .sort_values(ascending=False)
    )
    all_ports = port_totals.index.tolist()
    top_three_ports = all_ports[:3]  # the default, so the line chart is not crowded

    left_column, right_column = st.columns(2)
    with left_column:
        start_year = st.selectbox("Start year", available_years, index=0)
    with right_column:
        end_year = st.selectbox(
            "End year", available_years, index=len(available_years) - 1
        )

    select_all = st.checkbox("Select all ports")
    # When "Select all ports" is ticked, every port is chosen and the list is locked.
    selected_ports = st.multiselect(
        "Montana border ports",
        all_ports,
        default=all_ports if select_all else top_three_ports,
        disabled=select_all,
        help="Ports are listed from most to fewest total crossings.",
    )

    # Stop here if the years are in the wrong order or no port is chosen.
    if start_year > end_year:
        st.warning(
            "The start year must be the same as or earlier than the end year. "
            "Please change your selection."
        )
        st.stop()
    if not selected_ports:
        st.info("Choose at least one port, or tick \"Select all ports\", to see the charts.")
        st.stop()

    # All ports in the chosen years (for the statewide total), then the chosen ports.
    in_years = port_monthly[
        (port_monthly["year"] >= start_year) & (port_monthly["year"] <= end_year)
    ]
    selected = in_years[in_years["port_name"].isin(selected_ports)]

    # --- Data notes -----------------------------------------------------------
    first_month = selected["month_start"].min()
    last_month = selected["month_start"].max()
    st.caption(f"Showing {first_month:%B %Y} through {last_month:%B %Y}.")
    if last_month.month != 12:
        st.info(
            f"Data note: {last_month.year} contains only the months currently "
            f"available in PostgreSQL (through {last_month:%B})."
        )

    # --- Summary numbers ------------------------------------------------------
    selected_total = selected["passenger_crossings"].sum()
    # Add the chosen ports together for each month, then average those months.
    monthly_combined = selected.groupby("month_start")["passenger_crossings"].sum()
    average_monthly = monthly_combined.mean()
    # The statewide total uses ALL ports, even when only some are selected.
    statewide_total = in_years["passenger_crossings"].sum()
    share_of_state = selected_total / statewide_total * 100

    col_1, col_2, col_3 = st.columns(3)
    with col_1:
        st.metric("Total crossings (selected ports)", whole_number(selected_total))
    with col_2:
        st.metric("Average monthly crossings (combined)", whole_number(average_monthly))
    with col_3:
        st.metric("Share of statewide crossings", f"{share_of_state:.1f}%")

    # --- Chart 1: monthly crossings by port ----------------------------------
    st.subheader("Monthly Passenger Crossings by Port")

    line_chart = (
        alt.Chart(selected)
        .mark_line()
        .encode(
            x=alt.X("month_start:T", title="Month"),
            # format=",.0f" shows whole numbers with commas, e.g. 100,000
            y=alt.Y(
                "passenger_crossings:Q",
                title="Passenger crossings",
                axis=alt.Axis(format=",.0f"),
            ),
            # One color per port; tableau20 has enough colors for all 12 ports.
            color=alt.Color(
                "port_name:N",
                title="Port",
                sort=selected_ports,
                scale=alt.Scale(scheme="tableau20"),
            ),
            tooltip=[
                alt.Tooltip("month_start:T", title="Month", format="%B %Y"),
                alt.Tooltip("port_name:N", title="Port"),
                alt.Tooltip("port_code:N", title="Port code"),
                alt.Tooltip("passenger_crossings:Q", title="Crossings", format=",.0f"),
            ],
        )
    )
    st.altair_chart(line_chart, width="stretch")
    st.write(
        "This chart shows how monthly crossing volume changes over time at the "
        "selected ports."
    )

    # --- Chart 2: average monthly crossings by port --------------------------
    st.subheader("Average Monthly Passenger Crossings by Port")

    port_averages = selected.groupby("port_name", as_index=False)[
        "passenger_crossings"
    ].mean()

    # Horizontal bars leave room for port names; sort="-x" puts the largest on top.
    base = alt.Chart(port_averages).encode(
        y=alt.Y("port_name:N", title="Port", sort="-x"),
        x=alt.X(
            "passenger_crossings:Q",
            title="Average monthly crossings",
            axis=alt.Axis(format=",.0f"),
        ),
    )
    bars = base.mark_bar().encode(
        tooltip=[
            alt.Tooltip("port_name:N", title="Port"),
            alt.Tooltip("passenger_crossings:Q", title="Average per month", format=",.0f"),
        ],
    )
    # Text just to the right of each bar showing its average, e.g. 24,620
    labels = base.mark_text(align="left", dx=4).encode(
        text=alt.Text("passenger_crossings:Q", format=",.0f"),
    )
    st.altair_chart(bars + labels, width="stretch")
    st.write(
        "Each bar shows how many inbound passengers crossed at that port in a "
        "typical month of the selected period, from busiest to least busy."
    )


# =============================================================================
# Sidebar navigation: show the page the user picks.
# =============================================================================
page = st.sidebar.radio(
    "Go to page:",
    [
        "1. What Happened",
        "2. How Good Are the Predictions?",
        "3. What Should We Do?",
        "4. Explore Border Ports",
    ],
)

if page == "1. What Happened":
    show_page_1()
elif page == "2. How Good Are the Predictions?":
    show_page_2()
elif page == "3. What Should We Do?":
    show_page_3()
else:
    show_page_4()
