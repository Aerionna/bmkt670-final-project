# transform.py
# Purpose: Read the three raw files in data/raw/, clean them, and save one CSV
#          file per table in sql/schema.sql to data/clean/.
#          The raw files are only read, never changed.
# Run from the project folder:  python etl/transform.py

import json  # reads the raw JSON files
from pathlib import Path  # helps build file paths that work on any computer

import pandas as pd  # reads, cleans and saves table-style data

# --- 1. File locations --------------------------------------------------------
# Build the paths from this file's location so it works from any folder.
project_root = Path(__file__).resolve().parent.parent
raw_folder = project_root / "data" / "raw"
clean_folder = project_root / "data" / "clean"
clean_folder.mkdir(parents=True, exist_ok=True)  # create the folder if it's missing

# The analysis period starts in January 2017.
START_MONTH = pd.Timestamp("2017-01-01")


# --- 2. BTS border crossings (CSV) --------------------------------------------
# Read port_code as text so a code like "3301" is stored as text, as in schema.sql.
bts = pd.read_csv(raw_folder / "border_crossings_raw.csv", dtype={"port_code": str})

# Stop if a column we need is missing.
for column in ["port_code", "port_name", "state", "border", "measure", "date", "value"]:
    if column not in bts.columns:
        raise SystemExit(f"Error: BTS file is missing the column '{column}'")

# The extract script already filtered these values. Check that every row has them.
if (bts["state"] != "Montana").any():
    raise SystemExit("Error: BTS file has a state other than 'Montana'")
if (bts["border"] != "US-Canada Border").any():
    raise SystemExit("Error: BTS file has a border other than 'US-Canada Border'")
if (bts["measure"] != "Personal Vehicle Passengers").any():
    raise SystemExit("Error: BTS file has a measure other than 'Personal Vehicle Passengers'")

# Turn the text date (for example "2026-08-01T00:00:00.000") into a real date.
bts["month_start"] = pd.to_datetime(bts["date"])

# Save Willow Creek's 2016 rows before the 2017 filter removes them.
# Step 6 uses them to fill Willow Creek's missing 2017 months.
willow_creek_2016 = bts[(bts["port_code"] == "3325") & (bts["month_start"].dt.year == 2016)]

# Keep only January 2017 and later.
bts_raw_rows = len(bts)
bts = bts[bts["month_start"] >= START_MONTH]
bts_rows_removed = bts_raw_rows - len(bts)

# Create month_id in YYYYMM format, for example 2026 * 100 + 8 = 202608.
bts["month_id"] = bts["month_start"].dt.year * 100 + bts["month_start"].dt.month


# --- 3. Bank of Canada exchange rates (JSON) ----------------------------------
with open(raw_folder / "exchange_rates_raw.json") as file:
    exchange_json = json.load(file)

# Stop if the parts of the file we need are missing.
if "observations" not in exchange_json:
    raise SystemExit("Error: exchange rate file has no 'observations'")
if "FXMUSDCAD" not in exchange_json.get("seriesDetail", {}):
    raise SystemExit("Error: exchange rate file is not series FXMUSDCAD")

# Each observation looks like {"d": "2017-01-01", "FXMUSDCAD": {"v": "1.3193"}}.
# Collect the date and the rate from each one into two lists.
exchange_dates = []
exchange_values = []
for observation in exchange_json["observations"]:
    if "d" not in observation or "FXMUSDCAD" not in observation:
        raise SystemExit(f"Error: exchange rate observation is missing a field: {observation}")
    exchange_dates.append(observation["d"])
    exchange_values.append(observation["FXMUSDCAD"]["v"])

exchange = pd.DataFrame({"date": exchange_dates, "usd_cad_rate": exchange_values})

# The rate is stored as text (for example "1.3193"), so convert it to a number.
exchange["usd_cad_rate"] = exchange["usd_cad_rate"].astype(float)

# Turn the date into a real date, keep 2017 and later, and create month_id.
exchange["month_start"] = pd.to_datetime(exchange["date"])
exchange = exchange[exchange["month_start"] >= START_MONTH]
exchange["month_id"] = exchange["month_start"].dt.year * 100 + exchange["month_start"].dt.month


# --- 4. Statistics Canada travel (JSON) ---------------------------------------
with open(raw_folder / "canadian_travel_raw.json") as file:
    travel_json = json.load(file)

# The file is a list with one entry for our one vector. Check it is the right one.
travel_object = travel_json[0]["object"]
if travel_json[0]["status"] != "SUCCESS":
    raise SystemExit("Error: Statistics Canada file does not have status SUCCESS")
if travel_object["vectorId"] != 1296956601:
    raise SystemExit("Error: Statistics Canada file is not vector 1296956601")
if travel_object["productId"] != 24100053:
    raise SystemExit("Error: Statistics Canada file is not table 24-10-0053-01")

# Each data point is one month. Turn the list of data points into a DataFrame.
travel = pd.DataFrame(travel_object["vectorDataPoint"])

# Stop if a column we need is missing.
for column in ["refPer", "value", "statusCode", "symbolCode", "scalarFactorCode"]:
    if column not in travel.columns:
        raise SystemExit(f"Error: Statistics Canada file is missing the field '{column}'")

# 0 means a normal value with no flag, reported in units (not thousands).
for column in ["statusCode", "symbolCode", "scalarFactorCode"]:
    if (travel[column] != 0).any():
        raise SystemExit(f"Error: Statistics Canada field '{column}' has a value other than 0")

# Turn the date into a real date, keep 2017 and later, and create month_id.
travel["month_start"] = pd.to_datetime(travel["refPer"])
travel = travel[travel["month_start"] >= START_MONTH]
travel["month_id"] = travel["month_start"].dt.year * 100 + travel["month_start"].dt.month

# The count is stored as a decimal (for example 2198865.0), so convert it to a whole number.
travel["canadian_auto_return_trips"] = travel["value"].astype(int)


# --- 5. Build the clean tables ------------------------------------------------
# dim_month: one row for every month from January 2017 to the latest month
# found in any of the three sources.
latest_month = max(bts["month_start"].max(),
                   exchange["month_start"].max(),
                   travel["month_start"].max())
all_months = pd.date_range(start=START_MONTH, end=latest_month, freq="MS")  # "MS" = month start

dim_month = pd.DataFrame({"month_start": all_months})
dim_month["year"] = dim_month["month_start"].dt.year
dim_month["month_number"] = dim_month["month_start"].dt.month
dim_month["month_name"] = dim_month["month_start"].dt.month_name()
dim_month["month_id"] = dim_month["year"] * 100 + dim_month["month_number"]
dim_month["month_start"] = dim_month["month_start"].dt.strftime("%Y-%m-%d")  # YYYY-MM-DD text
dim_month = dim_month[["month_id", "month_start", "year", "month_number", "month_name"]]

# dim_port: one row per port that has data in 2017 or later.
dim_port = bts[["port_code", "port_name"]].drop_duplicates()
dim_port = dim_port.sort_values("port_code")

# fact_border_crossings: one row per port per month.
fact_border_crossings = bts[["month_id", "port_code", "value"]]
fact_border_crossings = fact_border_crossings.rename(columns={"value": "passenger_crossings"})
fact_border_crossings = fact_border_crossings.sort_values(["month_id", "port_code"])

# fact_exchange_rates: one row per month.
fact_exchange_rates = exchange[["month_id", "usd_cad_rate"]].sort_values("month_id")

# fact_national_travel: one row per month.
fact_national_travel = travel[["month_id", "canadian_auto_return_trips"]].sort_values("month_id")


# --- 6. Fill Willow Creek's missing 2017 months -------------------------------
# Willow Creek (3325) has no BTS rows for April to October 2017. We fill each
# missing month with the port's value from the same month in 2016.
# See docs/missing_data.md for the reasons behind this decision.
fill_port_code = "3325"
fill_month_numbers = [4, 5, 6, 7, 8, 9, 10]  # April to October

filled_records = []
for month_number in fill_month_numbers:
    month_id_2017 = 2017 * 100 + month_number

    # Confirm the 2017 row really is absent.
    existing_2017_row = fact_border_crossings[
        (fact_border_crossings["port_code"] == fill_port_code)
        & (fact_border_crossings["month_id"] == month_id_2017)
    ]
    if len(existing_2017_row) > 0:
        raise SystemExit(f"Error: Willow Creek already has a row for {month_id_2017}")

    # Confirm the matching 2016 row exists (exactly one).
    source_2016_row = willow_creek_2016[willow_creek_2016["month_start"].dt.month == month_number]
    if len(source_2016_row) != 1:
        raise SystemExit(f"Error: expected one Willow Creek row for month {month_number} of 2016")

    # Copy the 2016 value into a new 2017 row.
    filled_records.append({
        "month_id": month_id_2017,
        "port_code": fill_port_code,
        "passenger_crossings": source_2016_row["value"].iloc[0],
    })

# Add the filled rows to the fact table and put the rows back in order.
filled_rows = pd.DataFrame(filled_records)
fact_border_crossings = pd.concat([fact_border_crossings, filled_rows])
fact_border_crossings = fact_border_crossings.sort_values(["month_id", "port_code"])


# --- 7. Check the clean tables ------------------------------------------------
# Each table's primary key (from schema.sql) must not repeat.
if dim_month["month_id"].duplicated().any():
    raise SystemExit("Error: dim_month has duplicate month_id values")
if dim_port["port_code"].duplicated().any():
    raise SystemExit("Error: dim_port has duplicate port_code values (a code has two names)")
if fact_border_crossings.duplicated(subset=["month_id", "port_code"]).any():
    raise SystemExit("Error: fact_border_crossings has duplicate month_id + port_code rows")
if fact_exchange_rates["month_id"].duplicated().any():
    raise SystemExit("Error: fact_exchange_rates has duplicate month_id values")
if fact_national_travel["month_id"].duplicated().any():
    raise SystemExit("Error: fact_national_travel has duplicate month_id values")

# Counts cannot be negative, and an exchange rate must be above zero.
if (fact_border_crossings["passenger_crossings"] < 0).any():
    raise SystemExit("Error: fact_border_crossings has negative passenger_crossings")
if (fact_national_travel["canadian_auto_return_trips"] < 0).any():
    raise SystemExit("Error: fact_national_travel has negative canadian_auto_return_trips")
if (fact_exchange_rates["usd_cad_rate"] <= 0).any():
    raise SystemExit("Error: fact_exchange_rates has a usd_cad_rate that is not above zero")

# After filling, every active port should have one row for every BTS month
# (12 ports x 116 months = 1,392 rows with the current raw file).
expected_border_rows = len(dim_port) * fact_border_crossings["month_id"].nunique()
if len(fact_border_crossings) != expected_border_rows:
    raise SystemExit(f"Error: fact_border_crossings has {len(fact_border_crossings)} rows, "
                     f"expected {expected_border_rows}")


# --- 8. Find absent port-month rows (should be none after step 6) -------------
# Each active port should have a row for every BTS month. List any that do not.
bts_month_ids = sorted(fact_border_crossings["month_id"].unique())
absent_rows = []
for port_code in dim_port["port_code"]:
    port_month_ids = fact_border_crossings[fact_border_crossings["port_code"] == port_code]["month_id"]
    for month_id in bts_month_ids:
        if month_id not in port_month_ids.values:
            absent_rows.append((port_code, month_id))


# --- 9. Build the ML feature table --------------------------------------------
# One row per month: add the passenger crossings of all ports together.
ml_features = fact_border_crossings.groupby("month_id", as_index=False)["passenger_crossings"].sum()
ml_features = ml_features.rename(columns={"passenger_crossings": "statewide_crossings"})

# Join the month details, exchange rate and national travel count on month_id.
# how="inner" keeps only the months that every table has.
ml_features = ml_features.merge(dim_month, on="month_id", how="inner")
ml_features = ml_features.merge(fact_exchange_rates, on="month_id", how="inner")
ml_features = ml_features.merge(fact_national_travel, on="month_id", how="inner")

# Put the months in time order and number the rows 0, 1, 2, ...
ml_features = ml_features.sort_values("month_id").reset_index(drop=True)

# shift(1) below means "the row above". That is only the previous calendar
# month if no month is skipped, so confirm the months are continuous.
months_in_range = pd.date_range(start=ml_features["month_start"].iloc[0],
                                end=ml_features["month_start"].iloc[-1], freq="MS")
if len(ml_features) != len(months_in_range):
    raise SystemExit("Error: the joined monthly data skips a month, so the lags would be wrong")

# Lag features: shift(1) moves every value down one row, so each month gets
# the previous month's value and never its own.
ml_features["usd_cad_rate_lag1"] = ml_features["usd_cad_rate"].shift(1)
ml_features["national_travel_lag1"] = ml_features["canadian_auto_return_trips"].shift(1)
ml_features["crossings_lag1"] = ml_features["statewide_crossings"].shift(1)

# Rolling average of the three previous months. shift(1) comes first so the
# current month is left out, then rolling(3) averages the three rows above.
rolling_window = 3
ml_features["crossings_rolling_3"] = (
    ml_features["statewide_crossings"].shift(1).rolling(rolling_window).mean()
)

# The first three months do not have three earlier months, so their rolling
# average is empty. Remove exactly those first rows (not dropna on everything).
history_rows_removed = rolling_window
ml_features = ml_features.iloc[history_rows_removed:]

# Remove March 2020 to December 2021 (COVID border restrictions). This is done
# after the lags so the months right after COVID still have lag values.
# The fact tables and CSV files above still keep these months.
is_covid_month = (ml_features["month_id"] >= 202003) & (ml_features["month_id"] <= 202112)
covid_rows_removed = is_covid_month.sum()
ml_features = ml_features[~is_covid_month]  # ~ means "not": keep the non-COVID rows

# Season indicators. Winter (December-February) is the baseline, so it has 0 in all three.
ml_features["is_spring"] = ml_features["month_number"].isin([3, 4, 5]).astype(int)
ml_features["is_summer"] = ml_features["month_number"].isin([6, 7, 8]).astype(int)
ml_features["is_fall"] = ml_features["month_number"].isin([9, 10, 11]).astype(int)

# Split by year: through 2023 = train, 2024 = validate, 2025 and later = test.
ml_features["split"] = "train"
ml_features.loc[ml_features["year"] == 2024, "split"] = "validate"
ml_features.loc[ml_features["year"] >= 2025, "split"] = "test"

# shift() turned the lag columns into decimals. Make the counts whole numbers
# again and round the rolling average to 2 decimals, as in schema.sql.
ml_features["national_travel_lag1"] = ml_features["national_travel_lag1"].astype(int)
ml_features["crossings_lag1"] = ml_features["crossings_lag1"].astype(int)
ml_features["crossings_rolling_3"] = ml_features["crossings_rolling_3"].round(2)

# Keep only the schema.sql columns, in the same order.
ml_features_crossings = ml_features[[
    "month_id", "month_start", "year", "month_number", "statewide_crossings",
    "usd_cad_rate_lag1", "national_travel_lag1", "crossings_lag1", "crossings_rolling_3",
    "is_spring", "is_summer", "is_fall", "split",
]]


# --- 10. Check the ML feature table -------------------------------------------
# The last month should be the latest month that all three sources share.
latest_shared_month_id = min(fact_border_crossings["month_id"].max(),
                             fact_exchange_rates["month_id"].max(),
                             fact_national_travel["month_id"].max())
if ml_features_crossings["month_id"].iloc[0] != 201704:
    raise SystemExit("Error: the ML table should start in 201704")
if ml_features_crossings["month_id"].iloc[-1] != latest_shared_month_id:
    raise SystemExit(f"Error: the ML table should end in {latest_shared_month_id}")
if ml_features_crossings["month_id"].duplicated().any():
    raise SystemExit("Error: the ML table has duplicate month_id values")
if ml_features_crossings.isna().any().any():
    raise SystemExit("Error: the ML table has missing values")
if covid_rows_removed != 22:
    raise SystemExit(f"Error: expected to remove 22 COVID rows, removed {covid_rows_removed}")
if ((ml_features_crossings["month_id"] >= 202003) & (ml_features_crossings["month_id"] <= 202112)).any():
    raise SystemExit("Error: the ML table still has COVID-period rows")
for column in ["is_spring", "is_summer", "is_fall"]:
    if not ml_features_crossings[column].isin([0, 1]).all():
        raise SystemExit(f"Error: {column} has a value other than 0 or 1")
if not ml_features_crossings["split"].isin(["train", "validate", "test"]).all():
    raise SystemExit("Error: split has a value other than train, validate or test")
if (ml_features_crossings[["statewide_crossings", "national_travel_lag1",
                           "crossings_lag1", "crossings_rolling_3"]] < 0).any().any():
    raise SystemExit("Error: the ML table has a negative count")
if (ml_features_crossings["usd_cad_rate_lag1"] <= 0).any():
    raise SystemExit("Error: the ML table has a usd_cad_rate_lag1 that is not above zero")


# --- 11. Save the clean tables ------------------------------------------------
dim_month.to_csv(clean_folder / "dim_month.csv", index=False)
dim_port.to_csv(clean_folder / "dim_port.csv", index=False)
fact_border_crossings.to_csv(clean_folder / "fact_border_crossings.csv", index=False)
fact_exchange_rates.to_csv(clean_folder / "fact_exchange_rates.csv", index=False)
fact_national_travel.to_csv(clean_folder / "fact_national_travel.csv", index=False)
ml_features_crossings.to_csv(clean_folder / "ml_features_crossings.csv", index=False)


# --- 12. Print a summary ------------------------------------------------------
print(f"BTS raw rows before the 2017 filter: {bts_raw_rows}")
print(f"BTS rows removed by the date filter:  {bts_rows_removed}")
print()
print(f"dim_month:             {len(dim_month)} rows")
print(f"dim_port:              {len(dim_port)} rows (active ports)")
print(f"fact_border_crossings: {len(fact_border_crossings)} rows, "
      f"months {fact_border_crossings['month_id'].min()} to {fact_border_crossings['month_id'].max()}")
print(f"fact_exchange_rates:   {len(fact_exchange_rates)} rows, "
      f"months {fact_exchange_rates['month_id'].min()} to {fact_exchange_rates['month_id'].max()}")
print(f"fact_national_travel:  {len(fact_national_travel)} rows, "
      f"months {fact_national_travel['month_id'].min()} to {fact_national_travel['month_id'].max()}")
print()
print(f"Number of active ports: {len(dim_port)}")
print()
print(f"Filled {len(filled_rows)} Willow Creek (3325) rows with the value from the same month in 2016:")
for index, row in filled_rows.iterrows():
    print(f"  month {row['month_id']}: {row['passenger_crossings']} "
          f"(copied from month {row['month_id'] - 100})")
print()
print(f"fact_border_crossings has {len(fact_border_crossings)} rows "
      f"(expected {expected_border_rows} = {len(dim_port)} ports x "
      f"{fact_border_crossings['month_id'].nunique()} months)")
print("No duplicate primary keys found in any table.")
if absent_rows:
    print(f"WARNING: {len(absent_rows)} port-month rows are still absent:")
    for port_code, month_id in absent_rows:
        port_name = dim_port[dim_port["port_code"] == port_code]["port_name"].iloc[0]
        print(f"  {port_name} ({port_code}), month {month_id}")
else:
    print("No missing port-month rows remain.")
print()
print("ml_features_crossings:")
print(f"  Removed the first {history_rows_removed} rows because they do not have "
      f"{rolling_window} previous months for crossings_rolling_3.")
print(f"  Excluded {covid_rows_removed} rows (March 2020 to December 2021) because COVID border "
      f"restrictions made them unrepresentative of normal travel demand.")
print(f"  {len(ml_features_crossings)} rows, months {ml_features_crossings['month_id'].iloc[0]} "
      f"to {ml_features_crossings['month_id'].iloc[-1]}")
print(f"  train: {(ml_features_crossings['split'] == 'train').sum()}, "
      f"validate: {(ml_features_crossings['split'] == 'validate').sum()}, "
      f"test: {(ml_features_crossings['split'] == 'test').sum()}")
print("  (expected with the current source files: 90 rows, 59 train, 12 validate, 19 test)")
print()
print(f"Saved 6 CSV files to {clean_folder}")
