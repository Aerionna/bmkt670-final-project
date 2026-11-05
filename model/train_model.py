# train_model.py
# Purpose: Read the ML feature table (ml_features_crossings) from PostgreSQL,
#          split it into train, validate and test DataFrames, explore the
#          training rows with summaries and charts, score a baseline and three
#          regression models on the validation rows, test the selected model,
#          and save its predictions to the predictions table.
# Run from the project folder:  python model/train_model.py

import os  # reads the settings that load_dotenv puts into the environment
from pathlib import Path  # helps build file paths that work on any computer

import matplotlib.pyplot as plt  # draws and saves the charts
import pandas as pd  # holds the table as a DataFrame
import psycopg2  # talks to the PostgreSQL database
from dotenv import load_dotenv  # reads the .env file
from matplotlib.ticker import MaxNLocator  # makes an axis use whole-number ticks
from sklearn.ensemble import RandomForestRegressor  # many trees averaged together
from sklearn.linear_model import LinearRegression  # straight-line model
from sklearn.tree import DecisionTreeRegressor  # one tree of yes/no splits

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


# --- 7. Baseline model: predict the training mean -----------------------------
# The simplest sensible guess for any month is the average month seen in training.
# Later models must beat this baseline to be worth using.
# Only train is used here, so no validation answers leak into the prediction.
baseline_prediction = train["statewide_crossings"].mean()

# The baseline ignores every feature, so every validation month gets the same
# prediction: the training mean.
# MAE = the average of |actual - predicted|. Lower MAE is better.
validation_errors = (validate["statewide_crossings"] - baseline_prediction).abs()
baseline_mae = validation_errors.mean()

print()
print("Baseline model (training mean)")
print(f"  Training mean used as the prediction: {baseline_prediction:,.0f}")
print(f"  Validation rows scored: {len(validate)}")
print(f"  Baseline validation MAE: {baseline_mae:,.0f}")


# --- 8. Train and compare three models ----------------------------------------
# The features the models may use. Other columns are left out on purpose:
#   month_id, month_start - identifiers that label the row
#   split                 - an administrative label (train, validate or test)
#   statewide_crossings   - the target; using it would give away the answer
#   year, month_number    - could impose a misleading time trend (the season
#                           fields already describe the time of year)
feature_columns = [
    "usd_cad_rate_lag1",
    "national_travel_lag1",
    "crossings_lag1",
    "crossings_rolling_3",
    "is_spring",
    "is_summer",
    "is_fall",
]
target_column = "statewide_crossings"

# X = the features (inputs), y = the target (the answer to predict).
X_train = train[feature_columns]
y_train = train[target_column]
X_validate = validate[feature_columns]
y_validate = validate[target_column]

# There are only 59 training rows, so trees could memorize single months.
# max_depth and min_samples_leaf keep the trees small so they learn general
# patterns instead. random_state=42 gives the same result on every run.
models = {
    "Linear Regression": LinearRegression(),
    "Decision Tree": DecisionTreeRegressor(
        max_depth=3,
        min_samples_leaf=2,
        random_state=42,
    ),
    "Random Forest": RandomForestRegressor(
        n_estimators=100,
        max_depth=4,
        min_samples_leaf=2,
        random_state=42,
    ),
}

# The comparison table starts with the baseline row from section 7.
results = [{"Model": "Baseline (training mean)", "Validation MAE": baseline_mae}]

for model_name, model in models.items():
    model.fit(X_train, y_train)  # learn from the training rows only
    predictions = model.predict(X_validate)  # predict the validation months
    # Same MAE as the baseline: the average of |actual - predicted|.
    validation_mae = (y_validate - predictions).abs().mean()
    results.append({"Model": model_name, "Validation MAE": validation_mae})

results_table = pd.DataFrame(results)

print()
print(f"Model comparison ({len(validate)} validation months, lower MAE is better)")
print(results_table.to_string(index=False, formatters={"Validation MAE": "{:,.0f}".format}))

# Find the row with the lowest validation MAE.
best_row = results_table.loc[results_table["Validation MAE"].idxmin()]
print()
print(f"Lowest validation MAE: {best_row['Model']} ({best_row['Validation MAE']:,.0f})")
if best_row["Validation MAE"] < baseline_mae:
    improvement = baseline_mae - best_row["Validation MAE"]
    print(f"It beats the baseline MAE of {baseline_mae:,.0f} by {improvement:,.0f} crossings.")
else:
    print(f"No model beats the baseline MAE of {baseline_mae:,.0f}.")


# --- 9. Final test of the selected model --------------------------------------
# Random Forest was selected in Step 5 because it had the lowest validation MAE.
# The test rows are the final, unbiased check: the model has never seen them,
# and they were not used to choose the model. After this score is seen, the
# model, features and settings must not be changed to improve it, or the test
# would no longer be a fair check.
selected_model_name = "Random Forest"
selected_model = models[selected_model_name]  # already fitted on train only

# Validation MAE of the same fitted model, for a direct comparison.
selected_validation_mae = (y_validate - selected_model.predict(X_validate)).abs().mean()

# Use the same seven features as training.
X_test = test[feature_columns]
y_test = test[target_column]

# Predict the test months once and score them with the same MAE as before.
test_predictions = selected_model.predict(X_test)
test_mae = (y_test - test_predictions).abs().mean()

# Positive difference = the test error is larger than the validation error.
mae_difference = test_mae - selected_validation_mae
percent_difference = mae_difference / selected_validation_mae * 100

print()
print("Final test result")
print(f"  Selected model: {selected_model_name}")
print(f"  Validation MAE: {selected_validation_mae:,.0f}")
print(f"  Test rows: {len(test)}, months {test['month_id'].min()} to {test['month_id'].max()}")
print(f"  Test MAE: {test_mae:,.0f}")
print(f"  Test minus validation MAE: {mae_difference:+,.0f}")
if percent_difference > 0:
    print(f"  Test MAE is {percent_difference:.1f}% higher than validation MAE")
else:
    print(f"  Test MAE is {abs(percent_difference):.1f}% lower than validation MAE")


# --- 10. Feature importance of the selected model -----------------------------
# feature_importances_ comes from how the trees were built on the training rows,
# so no validation or test answers are used here.
# - Higher importance means the Random Forest relied more heavily on that feature.
# - Importance does not prove that a feature causes changes in crossings.
# - Importance does not show whether a feature raises or lowers predictions.
# - Features that carry similar information, such as crossings_lag1 and
#   crossings_rolling_3, may divide the importance between them.
importance_table = pd.DataFrame(
    {
        "Feature": feature_columns,  # same order the model was trained with
        "Importance": selected_model.feature_importances_,
    }
)
importance_table = importance_table.sort_values("Importance", ascending=False)

print()
print("Random Forest feature importance (highest first)")
print(importance_table.to_string(index=False, formatters={"Importance": "{:.1%}".format}))

print()
print("Top five features")
top_five = importance_table.head(5)
print(top_five.to_string(index=False, formatters={"Importance": "{:.1%}".format}))

# The importance values should add up to 1 (100%).
importance_total = importance_table["Importance"].sum()
print()
print(f"Total importance: {importance_total:.1%}")
if abs(importance_total - 1) > 0.001:
    raise ValueError("The feature importance values do not add up to about 100%")


# --- 11. Save the predictions to PostgreSQL -----------------------------------
# Use the same Random Forest (fitted on train only) to predict every ML row.
# - Train predictions are included for completeness, but their errors look
#   better than they really are, because the model learned from those rows.
# - Validate and test errors are the meaningful measures of how the model
#   does on months it has not seen.
all_predictions = selected_model.predict(df[feature_columns])

predictions_df = pd.DataFrame()
predictions_df["month_id"] = df["month_id"]
predictions_df["split"] = df["split"]
predictions_df["actual"] = df["statewide_crossings"]
predictions_df["predicted"] = all_predictions.round(2)
# error = actual - predicted. A positive error means the model predicted too
# low; a negative error means it predicted too high.
predictions_df["error"] = (predictions_df["actual"] - predictions_df["predicted"]).round(2)
predictions_df["model_name"] = "random_forest"

# psycopg2 needs regular Python values (int, float, str), not pandas/numpy ones.
prediction_rows = []
for index, row in predictions_df.iterrows():
    prediction_rows.append(
        (
            int(row["month_id"]),
            str(row["split"]),
            int(row["actual"]),
            float(row["predicted"]),
            float(row["error"]),
            str(row["model_name"]),
        )
    )

# Start with "no connection yet" so the cleanup step below knows what to close.
connection = None
cursor = None

try:
    connection = psycopg2.connect(
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT"),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
    )
    cursor = connection.cursor()

    # TRUNCATE empties the table first, so running this script again never
    # creates duplicate rows. psycopg2 starts a transaction automatically.
    cursor.execute("TRUNCATE TABLE predictions")
    cursor.executemany(
        "INSERT INTO predictions (month_id, split, actual, predicted, error, model_name) "
        "VALUES (%s, %s, %s, %s, %s, %s)",
        prediction_rows,
    )

    # Nothing is saved until this line. It only runs if every insert worked.
    connection.commit()

    # Check what is now in the database.
    print()
    print("Saved predictions to PostgreSQL")
    # The table must have one row for every ML row, and the same rows in each split.
    cursor.execute("SELECT COUNT(*) FROM predictions")
    prediction_count = cursor.fetchone()[0]
    print(f"  Total prediction rows: {prediction_count}")
    if prediction_count != len(df):
        raise ValueError(f"predictions has {prediction_count} rows, but the ML table has {len(df)}")

    for split_name in ["train", "validate", "test"]:
        cursor.execute("SELECT COUNT(*) FROM predictions WHERE split = %s", (split_name,))
        split_count = cursor.fetchone()[0]
        print(f"  {split_name} rows: {split_count}")
        if split_count != (df["split"] == split_name).sum():
            raise ValueError(f"predictions has a different number of {split_name} rows than the ML table")

    cursor.execute("SELECT DISTINCT model_name FROM predictions")
    print(f"  Model name: {cursor.fetchone()[0]}")

    # COUNT(*) - COUNT(DISTINCT month_id) is 0 when every month_id is unique.
    cursor.execute("SELECT COUNT(*) - COUNT(DISTINCT month_id) FROM predictions")
    duplicate_count = cursor.fetchone()[0]
    if duplicate_count != 0:
        raise ValueError(f"predictions has {duplicate_count} duplicate month_id values")
    print("  No duplicate month_id values")

    cursor.execute("SELECT COUNT(*) FROM predictions WHERE error <> actual - predicted")
    wrong_error_count = cursor.fetchone()[0]
    if wrong_error_count != 0:
        raise ValueError(f"{wrong_error_count} rows have error not equal to actual - predicted")
    print("  Every error equals actual - predicted")
    print("  Reminder: only validate and test errors measure performance on unseen months.")

except (psycopg2.Error, OSError) as error:
    # psycopg2.Error = any database problem; OSError = a connection or file problem.
    # Undo everything since the connection opened, so no half-loaded table remains.
    if connection is not None:
        connection.rollback()
    print("Error: saving the predictions failed and was rolled back.")
    print(f"Details: {error}")
    raise SystemExit(1)

finally:
    # Always close the cursor and connection, whether the save worked or not.
    if cursor is not None:
        cursor.close()
    if connection is not None:
        connection.close()
