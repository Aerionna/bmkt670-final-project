# Practice Streamlit app for the Montana Border Crossings Dashboard.
# The season table and chart use made-up numbers. The section at the bottom
# tests the connection to our PostgreSQL database.

import os  # reads the settings that load_dotenv puts into the environment
from pathlib import Path  # builds file paths that work on any computer

import pandas as pd
import psycopg2  # talks to PostgreSQL
import streamlit as st
from dotenv import load_dotenv  # reads the .env file

# Page title at the top of the app
st.title("Montana Border Crossings Dashboard")

# One sentence explaining the purpose of the dashboard
st.write(
    "This dashboard will help a Montana destination organization "
    "understand and predict inbound border crossings."
)

# A drop-down menu so the user can pick a season
season = st.selectbox("Choose a season:", ["Winter", "Spring", "Summer", "Fall"])

# Show the season the user picked
st.write("You selected:", season)

# A small table of made-up crossing numbers (sample data, not real)
sample_data = pd.DataFrame(
    {
        "Season": ["Winter", "Spring", "Summer", "Fall"],
        "Crossings": [12000, 18000, 35000, 22000],
    }
)

# Display the table
st.subheader("Sample Crossings by Season")
st.dataframe(sample_data)

# Display a bar chart using the same table
# set_index tells Streamlit to use Season as the labels on the x-axis
st.bar_chart(sample_data.set_index("Season"))


# --- Live data from PostgreSQL ------------------------------------------------
st.subheader("Live PostgreSQL Data")

# Read .env from the project folder (one level up from this dashboard folder).
# The values are never printed or shown on the page.
project_root = Path(__file__).resolve().parent.parent
load_dotenv(project_root / ".env")

# Make a list of any database settings that are missing from .env.
missing_settings = []
for setting_name in ["DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD"]:
    if not os.getenv(setting_name):
        missing_settings.append(setting_name)

if missing_settings:
    # Only the setting NAMES are shown, never their values.
    st.error("These settings are missing from .env: " + ", ".join(missing_settings))
else:
    connection = None  # stays None if the connection never opens
    try:
        connection = psycopg2.connect(
            host=os.getenv("DB_HOST"),
            port=os.getenv("DB_PORT"),
            dbname=os.getenv("DB_NAME"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
        )
        cursor = connection.cursor()

        # Get the 10 newest months: DESC sorts from newest to oldest.
        cursor.execute(
            "SELECT * FROM ml_features_crossings ORDER BY month_id DESC LIMIT 10"
        )
        rows = cursor.fetchall()  # every row, as a list of tuples

        # cursor.description has one entry per column; the first item is its name.
        column_names = []
        for column in cursor.description:
            column_names.append(column[0])

        cursor.close()

        # Turn the rows and column names into a table and show it.
        live_data = pd.DataFrame(rows, columns=column_names)
        st.dataframe(live_data)

    except psycopg2.Error as error:
        # Show only the type of error, not its full text, so no connection
        # details (and never the password) appear on the page.
        st.error(
            "Could not load data from PostgreSQL "
            f"({type(error).__name__}). Check that the database is running "
            "and that the settings in .env are correct."
        )

    finally:
        # "finally" always runs, so the connection is closed even after an error.
        if connection is not None:
            connection.close()
