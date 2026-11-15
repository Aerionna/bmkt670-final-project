# Montana Border Crossings Dashboard - Page 1: "What Happened?"
# Every number on this page comes live from our PostgreSQL database.

import os  # reads the settings that load_dotenv puts into the environment
from pathlib import Path  # builds file paths that work on any computer

import altair as alt  # draws charts (installed together with Streamlit)
import pandas as pd
import psycopg2  # talks to PostgreSQL
import streamlit as st
from dotenv import load_dotenv  # reads the .env file

# The seasons in calendar order. We use this list to keep charts in this order.
SEASON_ORDER = ["Winter", "Spring", "Summer", "Fall"]

# SQL that adds up passenger crossings across all ports for each month.
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


def load_monthly_totals():
    """Run the SQL above and return the results as a pandas DataFrame."""
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
        cursor.execute(MONTHLY_TOTALS_SQL)
        rows = cursor.fetchall()  # every row, as a list of tuples

        # cursor.description has one entry per column; the first item is its name.
        column_names = []
        for column in cursor.description:
            column_names.append(column[0])

        cursor.close()
    finally:
        # "finally" always runs, so the connection is closed even after an error.
        connection.close()

    data = pd.DataFrame(rows, columns=column_names)
    # Turn the date column into a pandas date so the line chart reads it as time.
    data["month_start"] = pd.to_datetime(data["month_start"])
    return data


# --- Page heading -------------------------------------------------------------
st.title("What Happened?")
st.write(
    "How have inbound passenger crossings at Montana's Canadian border "
    "changed over time and by season?"
)

# --- Load the data ------------------------------------------------------------
try:
    monthly = load_monthly_totals()
except psycopg2.Error as error:
    # Show only the type of error, not its full text, so no connection
    # details (and never the password) appear on the page.
    st.error(
        "Could not load data from PostgreSQL "
        f"({type(error).__name__}). Check that the database is running "
        "and that the settings in .env are correct."
    )
    st.stop()  # nothing else on the page can work without data

# --- Year filters -------------------------------------------------------------
# The list of years comes from the data, not typed into the code.
available_years = sorted(monthly["year"].unique().tolist())

# st.columns(2) makes two side-by-side spaces for the dropdowns.
left_column, right_column = st.columns(2)
with left_column:
    # index=0 starts on the first (earliest) year.
    start_year = st.selectbox("Start year", available_years, index=0)
with right_column:
    # index=len(...) - 1 starts on the last (latest) year.
    end_year = st.selectbox("End year", available_years, index=len(available_years) - 1)

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

# --- Chart 1: monthly crossings over time ------------------------------------
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

# --- Chart 2: average monthly crossings by season ----------------------------
st.subheader("Average Monthly Passenger Crossings by Season")

# Average the monthly totals within each season.
season_averages = selected.groupby("season", as_index=False)["total_crossings"].mean()

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
