# quality_checks.py
# Purpose: Run six data-quality checks on the tables loaded into PostgreSQL.
#          This script only reads data. It never changes the database or the CSV files.
# Run from the project folder:  python etl/quality_checks.py

import os  # reads the settings that load_dotenv puts into the environment
from pathlib import Path  # helps build file paths that work on any computer

import pandas as pd  # reads the clean CSV files to count their rows
import psycopg2  # talks to the PostgreSQL database
from dotenv import load_dotenv  # reads the .env file

# --- 1. File locations and database settings ----------------------------------
# Build the paths from this file's location so it works from any folder.
project_root = Path(__file__).resolve().parent.parent
clean_folder = project_root / "data" / "clean"

# Read .env from the project folder. The values are never printed.
load_dotenv(project_root / ".env")

table_names = [
    "dim_month",
    "dim_port",
    "fact_border_crossings",
    "fact_exchange_rates",
    "fact_national_travel",
    "ml_features_crossings",
]


# --- 2. Helper functions ------------------------------------------------------
def run_count_query(sql):
    """Run a SQL query that returns one number, and return that number."""
    cursor.execute(sql)
    return cursor.fetchone()[0]  # fetchone() returns one row; [0] is its first value


def print_result(check_label, description, number_found):
    """Print [PASS] if number_found is 0, otherwise [FAIL]. Return True if it passed."""
    passed = number_found == 0
    status = "PASS" if passed else "FAIL"
    print(f"[{status}] {check_label}: {description} (found: {number_found})")
    print()
    return passed


# --- 3. Connect to the database -----------------------------------------------
connection = psycopg2.connect(
    host=os.getenv("DB_HOST"),
    port=os.getenv("DB_PORT"),
    dbname=os.getenv("DB_NAME"),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
)
cursor = connection.cursor()

# Each check adds True (passed) or False (failed) to this list.
check_results = []

# "try ... finally" makes sure the connection is closed even if a query fails.
# A real error (such as a broken query) still stops the script with an error message.
try:
    # --- Check 1: No duplicate primary keys -----------------------------------
    # Duplicates = total rows minus the number of different key values.
    primary_keys = {
        "dim_month": "month_id",
        "dim_port": "port_code",
        "fact_border_crossings": "month_id, port_code",
        "fact_exchange_rates": "month_id",
        "fact_national_travel": "month_id",
        "ml_features_crossings": "month_id",
    }
    print("Check 1: duplicate primary keys")
    total_duplicates = 0
    for table_name, key_columns in primary_keys.items():
        duplicates = run_count_query(
            f"SELECT COUNT(*) - COUNT(DISTINCT ({key_columns})) FROM {table_name}"
        )
        print(f"  {table_name} ({key_columns}): {duplicates} duplicates")
        total_duplicates += duplicates
    check_results.append(
        print_result("Check 1", "No duplicate primary keys in any table", total_duplicates)
    )

    # --- Check 2: No orphaned foreign keys ------------------------------------
    # LEFT JOIN keeps every child row. If no matching parent row exists, the
    # parent's column is NULL, so those rows are orphans.
    foreign_keys = [
        ("fact_border_crossings", "month_id", "dim_month"),
        ("fact_border_crossings", "port_code", "dim_port"),
        ("fact_exchange_rates", "month_id", "dim_month"),
        ("fact_national_travel", "month_id", "dim_month"),
        ("ml_features_crossings", "month_id", "dim_month"),
    ]
    print("Check 2: orphaned foreign keys")
    total_orphans = 0
    for child_table, key_column, parent_table in foreign_keys:
        orphans = run_count_query(f"""
            SELECT COUNT(*)
            FROM {child_table} AS child
            LEFT JOIN {parent_table} AS parent
                ON child.{key_column} = parent.{key_column}
            WHERE parent.{key_column} IS NULL
        """)
        print(f"  {child_table}.{key_column} -> {parent_table}.{key_column}: {orphans} orphans")
        total_orphans += orphans
    check_results.append(
        print_result("Check 2", "No orphaned foreign keys", total_orphans)
    )

    # --- Check 3: No missing required values ----------------------------------
    # Every column in schema.sql is required (NOT NULL), so check them all.
    required_columns = {
        "dim_month": ["month_id", "month_start", "year", "month_number", "month_name"],
        "dim_port": ["port_code", "port_name"],
        "fact_border_crossings": ["month_id", "port_code", "passenger_crossings"],
        "fact_exchange_rates": ["month_id", "usd_cad_rate"],
        "fact_national_travel": ["month_id", "canadian_auto_return_trips"],
        "ml_features_crossings": [
            "month_id", "month_start", "year", "month_number", "statewide_crossings",
            "usd_cad_rate_lag1", "national_travel_lag1", "crossings_lag1",
            "crossings_rolling_3", "is_spring", "is_summer", "is_fall", "split",
        ],
    }
    print("Check 3: missing required values")
    total_missing = 0
    for table_name, column_names in required_columns.items():
        table_missing = 0
        for column_name in column_names:
            table_missing += run_count_query(
                f"SELECT COUNT(*) FROM {table_name} WHERE {column_name} IS NULL"
            )
        print(f"  {table_name} ({len(column_names)} columns): {table_missing} missing values")
        total_missing += table_missing
    check_results.append(
        print_result("Check 3", "No missing values in required columns", total_missing)
    )

    # --- Check 4: Valid numeric values and category codes ---------------------
    # Each query counts the rows that break one rule.
    # "NOT BETWEEN 0.5 AND 2.0" also catches rates of 0 or below.
    validity_rules = [
        ("passenger_crossings >= 0",
         "SELECT COUNT(*) FROM fact_border_crossings WHERE passenger_crossings < 0"),
        ("usd_cad_rate > 0 and between 0.5 and 2.0",
         "SELECT COUNT(*) FROM fact_exchange_rates WHERE usd_cad_rate NOT BETWEEN 0.5 AND 2.0"),
        ("canadian_auto_return_trips >= 0",
         "SELECT COUNT(*) FROM fact_national_travel WHERE canadian_auto_return_trips < 0"),
        ("statewide_crossings >= 0",
         "SELECT COUNT(*) FROM ml_features_crossings WHERE statewide_crossings < 0"),
        ("usd_cad_rate_lag1 > 0 and between 0.5 and 2.0",
         ("SELECT COUNT(*) FROM ml_features_crossings "
          "WHERE usd_cad_rate_lag1 NOT BETWEEN 0.5 AND 2.0")),
        ("national_travel_lag1 >= 0",
         "SELECT COUNT(*) FROM ml_features_crossings WHERE national_travel_lag1 < 0"),
        ("crossings_lag1 >= 0",
         "SELECT COUNT(*) FROM ml_features_crossings WHERE crossings_lag1 < 0"),
        ("crossings_rolling_3 >= 0",
         "SELECT COUNT(*) FROM ml_features_crossings WHERE crossings_rolling_3 < 0"),
        ("is_spring is 0 or 1",
         "SELECT COUNT(*) FROM ml_features_crossings WHERE is_spring NOT IN (0, 1)"),
        ("is_summer is 0 or 1",
         "SELECT COUNT(*) FROM ml_features_crossings WHERE is_summer NOT IN (0, 1)"),
        ("is_fall is 0 or 1",
         "SELECT COUNT(*) FROM ml_features_crossings WHERE is_fall NOT IN (0, 1)"),
        ("at most one season indicator is 1",
         "SELECT COUNT(*) FROM ml_features_crossings WHERE is_spring + is_summer + is_fall > 1"),
        ("split is train, validate or test",
         ("SELECT COUNT(*) FROM ml_features_crossings "
          "WHERE split NOT IN ('train', 'validate', 'test')")),
        ("dim_month.month_number between 1 and 12",
         "SELECT COUNT(*) FROM dim_month WHERE month_number NOT BETWEEN 1 AND 12"),
        ("ml_features_crossings.month_number between 1 and 12",
         "SELECT COUNT(*) FROM ml_features_crossings WHERE month_number NOT BETWEEN 1 AND 12"),
    ]
    print("Check 4: valid numeric values and category codes")
    total_violations = 0
    for rule_description, sql in validity_rules:
        violations = run_count_query(sql)
        print(f"  {rule_description}: {violations} invalid")
        total_violations += violations
    check_results.append(
        print_result("Check 4", "All numeric values and category codes are valid", total_violations)
    )

    # --- Check 5: Clean CSV row counts match PostgreSQL -----------------------
    # The CSV files are only read, to count their rows.
    print("Check 5: clean CSV row counts vs. PostgreSQL row counts")
    mismatched_tables = 0
    for table_name in table_names:
        csv_row_count = len(pd.read_csv(clean_folder / f"{table_name}.csv"))
        database_row_count = run_count_query(f"SELECT COUNT(*) FROM {table_name}")
        match_text = "match" if csv_row_count == database_row_count else "MISMATCH"
        print(f"  {table_name}: CSV {csv_row_count}, database {database_row_count} ({match_text})")
        if csv_row_count != database_row_count:
            mismatched_tables += 1
    check_results.append(
        print_result("Check 5", "Tables whose CSV and database row counts differ", mismatched_tables)
    )

    # --- Check 6: ML target matches the border-crossing facts -----------------
    # Add up the ports for each month, then compare with statewide_crossings.
    # A month with no fact rows (NULL total) also counts as a mismatch.
    print("Check 6: ML statewide_crossings vs. sum of fact_border_crossings")
    mismatched_months = run_count_query("""
        SELECT COUNT(*)
        FROM ml_features_crossings AS ml
        LEFT JOIN (
            SELECT month_id, SUM(passenger_crossings) AS fact_total
            FROM fact_border_crossings
            GROUP BY month_id
        ) AS monthly_totals
            ON ml.month_id = monthly_totals.month_id
        WHERE monthly_totals.fact_total IS NULL
           OR monthly_totals.fact_total <> ml.statewide_crossings
    """)
    ml_month_count = run_count_query("SELECT COUNT(*) FROM ml_features_crossings")
    print(f"  ML months compared: {ml_month_count}")
    check_results.append(
        print_result("Check 6", "ML months whose target does not equal the fact-table sum",
                     mismatched_months)
    )

finally:
    # Always close the cursor and connection, even if a query failed.
    cursor.close()
    connection.close()


# --- 4. Summary ---------------------------------------------------------------
checks_passed = check_results.count(True)
checks_failed = check_results.count(False)
print(f"Checks passed: {checks_passed}")
print(f"Checks failed: {checks_failed}")
if checks_failed == 0:
    print("Overall pipeline quality: PASS")
else:
    print("Overall pipeline quality: FAIL")
