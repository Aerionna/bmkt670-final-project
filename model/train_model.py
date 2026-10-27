# train_model.py
# Purpose: Read the ML feature table (ml_features_crossings) from PostgreSQL,
#          split it into train, validate and test DataFrames, and explore the
#          training rows with summaries and charts.
# Run from the project folder:  python model/train_model.py

import os  # reads the settings that load_dotenv puts into the environment
from pathlib import Path  # helps build file paths that work on any computer

import matplotlib.pyplot as plt  # draws and saves the charts
import pandas as pd  # holds the table as a DataFrame
import psycopg2  # talks to the PostgreSQL database
from dotenv import load_dotenv  # reads the .env file
from matplotlib.ticker import MaxNLocator  # makes an axis use whole-number ticks

# --- 1. Database settings -----------------------------------------------------
# Read .env from the project folder. The values are never printed.
project_root = Path(__file__).resolve().parent.parent
load_dotenv(project_root / ".env")

for setting_name in ["DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD"]:
    if not os.getenv(setting_name):
        raise SystemExit(f"Error: the setting {setting_name} is missing from .env")


# --- 2. Read the ML feature table from PostgreSQL -----------------------------
connection = psycopg2.connect(
    host=os.getenv("DB_HOST"),
    port=os.getenv("DB_PORT"),
    dbname=os.getenv("DB_NAME"),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
)
cursor = connection.cursor()

# ORDER BY month_id keeps the months in time order.
cursor.execute("SELECT * FROM ml_features_crossings ORDER BY month_id")
rows = cursor.fetchall()  # every row, as a list of tuples

# cursor.description has one entry per column; the first item of each is its name.
column_names = []
for column in cursor.description:
    column_names.append(column[0])

# We have the data, so close the cursor and connection.
cursor.close()
connection.close()

df = pd.DataFrame(rows, columns=column_names)

# PostgreSQL NUMERIC values arrive as Decimal objects. Convert them to floats
# so they work cleanly with charts and machine-learning models.
numeric_columns = [
    "usd_cad_rate_lag1",
    "crossings_rolling_3",
]

df[numeric_columns] = df[numeric_columns].astype(float)

if len(df) == 0:
    raise ValueError("The query returned no rows from ml_features_crossings")


# --- 3. Split into train, validate and test -----------------------------------
train = df[df["split"] == "train"]
validate = df[df["split"] == "validate"]
test = df[df["split"] == "test"]


# --- 4. Check the split -------------------------------------------------------
# Every row must have one of the three allowed split values.
if not df["split"].isin(["train", "validate", "test"]).all():
    raise ValueError("The split column has a value other than train, validate or test")

# None of the three DataFrames may be empty.
if len(train) == 0:
    raise ValueError("The train split is empty")
if len(validate) == 0:
    raise ValueError("The validate split is empty")
if len(test) == 0:
    raise ValueError("The test split is empty")

# Together, the three splits must contain every row exactly once.
if len(train) + len(validate) + len(test) != len(df):
    raise ValueError("The train, validate and test row counts do not add up to the total")


# --- 5. Print the results -----------------------------------------------------
print(f"Total ML rows: {len(df)}")
print(f"train:    {len(train)} rows, months {train['month_id'].min()} to {train['month_id'].max()}")
print(f"validate: {len(validate)} rows, months {validate['month_id'].min()} to {validate['month_id'].max()}")
print(f"test:     {len(test)} rows, months {test['month_id'].min()} to {test['month_id'].max()}")
print("(expected with the current source files: 90 total, 59 train, 12 validate, 19 test)")


# --- 6. Explore the training rows only ----------------------------------------
# Only train is used from here on. Looking at validate or test now could
# influence modeling choices with answers the model should not have seen.
print()
print("Training data: statewide_crossings summary")
print(train["statewide_crossings"].describe())

# Correlation: +1 = move together, -1 = move opposite, 0 = no straight-line pattern.
print()
print("Training data: correlation with statewide_crossings")
for feature in ["crossings_rolling_3", "usd_cad_rate_lag1", "national_travel_lag1"]:
    correlation = train["statewide_crossings"].corr(train[feature])
    print(f"  {feature}: {correlation:.3f}")

# Save the charts in docs/figures/ (created if it does not exist yet).
figures_folder = project_root / "docs" / "figures"
figures_folder.mkdir(parents=True, exist_ok=True)

# Chart 1: histogram of the target.
plt.figure(figsize=(8, 5))
plt.hist(train["statewide_crossings"], bins=10, edgecolor="black")
plt.title("Distribution of Monthly Statewide Crossings — Training Data")
plt.xlabel("Statewide Passenger Crossings")
plt.ylabel("Number of Months")
# A histogram counts whole months, so show only whole-number ticks (no 2.5 or 7.5).
plt.gca().yaxis.set_major_locator(MaxNLocator(integer=True))
plt.tight_layout()
plt.savefig(figures_folder / "statewide_crossings_distribution.png", dpi=300)
plt.close()  # close the figure so repeated runs do not leave it open

# Chart 2: average target by season.
# Work on a copy of train so the original train DataFrame is not changed.
# Turn the three 0/1 season fields back into one readable label.
season_data = train.copy()
season_data["season"] = "Winter"  # all three fields are 0 for December-February
season_data.loc[season_data["is_spring"] == 1, "season"] = "Spring"
season_data.loc[season_data["is_summer"] == 1, "season"] = "Summer"
season_data.loc[season_data["is_fall"] == 1, "season"] = "Fall"

# Count the months and average the target in each season, in calendar order.
season_order = ["Winter", "Spring", "Summer", "Fall"]
season_counts = season_data.groupby("season")["statewide_crossings"].count()[season_order]
season_averages = season_data.groupby("season")["statewide_crossings"].mean()[season_order]

print()
print("Training data: statewide_crossings by season")
for season in season_order:
    print(f"  {season}: {season_counts[season]} months, average {season_averages[season]:,.0f}")

plt.figure(figsize=(8, 5))
plt.bar(season_order, season_averages, edgecolor="black")
plt.title("Average Monthly Statewide Crossings by Season — Training Data")
plt.xlabel("Season")
plt.ylabel("Average Statewide Passenger Crossings")
plt.tight_layout()
plt.savefig(figures_folder / "crossings_by_season.png", dpi=300)
plt.close()

# Chart 3: target vs. the previous month's exchange rate.
plt.figure(figsize=(8, 5))
plt.scatter(train["usd_cad_rate_lag1"], train["statewide_crossings"])
plt.title("Statewide Crossings vs. Previous Month’s USD/CAD Rate")
plt.xlabel("Previous Month’s USD/CAD Rate")
plt.ylabel("Statewide Passenger Crossings")
plt.tight_layout()
plt.savefig(figures_folder / "crossings_vs_exchange_rate.png", dpi=300)
plt.close()

# Chart 4: target vs. the previous month's national automobile travel.
plt.figure(figsize=(8, 5))
plt.scatter(train["national_travel_lag1"], train["statewide_crossings"])
plt.title("Statewide Crossings vs. Previous Month’s National Automobile Travel")
plt.xlabel("Previous Month’s Canadian Automobile Trips")
plt.ylabel("Statewide Passenger Crossings")
plt.ticklabel_format(axis="x", style="plain")  # show 2000000, not "2.0" with a "1e6" label
plt.tight_layout()
plt.savefig(figures_folder / "crossings_vs_national_travel.png", dpi=300)
plt.close()

print()
print(f"Saved 4 charts to {figures_folder}")
