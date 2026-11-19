# Montana Border Crossings Dashboard
#   Page 1: "What Happened?"
#   Page 2: "How Good Are the Predictions?"
# Every number on these pages comes live from our PostgreSQL database.

import os  # reads the settings that load_dotenv puts into the environment
from pathlib import Path  # builds file paths that work on any computer

import altair as alt  # draws charts (installed together with Streamlit)
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


def show_database_error(error):
    """Show a friendly error without any connection details or the password."""
    # Only the type of error is shown, not its full text.
    st.error(
        "Could not load data from PostgreSQL "
        f"({type(error).__name__}). Check that the database is running "
        "and that the settings in .env are correct."
    )
    st.stop()  # nothing else on the page can work without data


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
        st.metric("Random Forest MAE", f"{model_mae:,.0f}")
    with right_column:
        st.metric("Baseline MAE (training average)", f"{baseline_mae:,.0f}")

    # Explain the comparison in plain language.
    difference = baseline_mae - model_mae
    if difference > 0:
        percent_better = difference / baseline_mae * 100
        st.write(
            f"On the {len(results)} validate and test months, the model's predictions "
            f"were off by {difference:,.0f} fewer crossings per month on average than "
            f"always guessing the training average of {train_average:,.0f}, "
            f"about {percent_better:.0f}% less error."
        )
    else:
        st.write(
            f"On the {len(results)} validate and test months, the model did not beat "
            f"always guessing the training average of {train_average:,.0f}."
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

    # .style.format controls how numbers look: commas, and two decimals for the ratio.
    st.dataframe(
        table.style.format(
            {
                "actual": "{:,.0f}",
                "predicted": "{:,.0f}",
                "absolute_error": "{:,.0f}",
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
            f"{worst['predicted']:,.0f} crossings but {worst['actual']:,.0f} actually "
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
# Sidebar navigation: show the page the user picks.
# =============================================================================
page = st.sidebar.radio(
    "Go to page:",
    ["1. What Happened", "2. How Good Are the Predictions?"],
)

if page == "1. What Happened":
    show_page_1()
else:
    show_page_2()
