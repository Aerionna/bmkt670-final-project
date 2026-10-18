# load.py
# Purpose: Rebuild the PostgreSQL tables from sql/schema.sql and load the six
#          clean CSV files from data/clean/ into them, all in one transaction.
# Run from the project folder:  python etl/load.py

import os  # reads the settings that load_dotenv puts into the environment
from pathlib import Path  # helps build file paths that work on any computer

import psycopg2  # talks to the PostgreSQL database
from dotenv import load_dotenv  # reads the .env file

# --- 1. File locations --------------------------------------------------------
# Build the paths from this file's location so it works from any folder.
project_root = Path(__file__).resolve().parent.parent
schema_file = project_root / "sql" / "schema.sql"
clean_folder = project_root / "data" / "clean"

# Load order matters: the dimension tables come first because the fact tables
# and the ML table point to them (foreign keys).
table_names = [
    "dim_month",
    "dim_port",
    "fact_border_crossings",
    "fact_exchange_rates",
    "fact_national_travel",
    "ml_features_crossings",
]

# Row counts with the current source files. These grow when the APIs publish
# new months, so a difference is only reported, not treated as an error.
expected_row_counts = {
    "dim_month": 117,
    "dim_port": 12,
    "fact_border_crossings": 1392,
    "fact_exchange_rates": 117,
    "fact_national_travel": 115,
    "ml_features_crossings": 90,
}


# --- 2. Database settings -----------------------------------------------------
# Read .env from the project folder. The values are never printed.
load_dotenv(project_root / ".env")

for setting_name in ["DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD"]:
    if not os.getenv(setting_name):
        raise SystemExit(f"Error: the setting {setting_name} is missing from .env")


# --- 3. Check that every file exists before touching the database -------------
required_files = [schema_file]
for table_name in table_names:
    required_files.append(clean_folder / f"{table_name}.csv")

for file_path in required_files:
    if not file_path.exists():
        raise SystemExit(f"Error: required file not found: {file_path}. "
                         f"The database was not changed.")


# --- 4. Rebuild the tables and load the CSV files -----------------------------
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
    # A cursor is the object that sends SQL to the database.
    cursor = connection.cursor()

    # Run schema.sql: it drops and recreates every table, so running this
    # script again never creates duplicate rows.
    schema_sql = schema_file.read_text(encoding="utf-8")
    cursor.execute(schema_sql)
    print("Ran sql/schema.sql: dropped and recreated all tables")

    for table_name in table_names:
        # COPY reads the whole CSV file into the table. HEADER true skips the
        # first line, which holds the column names.
        csv_path = clean_folder / f"{table_name}.csv"
        with open(csv_path, encoding="utf-8") as csv_file:
            cursor.copy_expert(f"COPY {table_name} FROM STDIN WITH (FORMAT csv, HEADER true)",
                               csv_file)

        # Count the rows that are now in the table.
        cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
        row_count = cursor.fetchone()[0]  # fetchone() returns one row; [0] is its first value
        print(f"Loaded {table_name}: {row_count} rows")
        if row_count != expected_row_counts[table_name]:
            print(f"  Note: expected {expected_row_counts[table_name]} rows with the current "
                  f"source files, got {row_count}")

    # Nothing is saved until this line. It only runs if every step above worked.
    connection.commit()
    print("Committed: the database was rebuilt and all six tables were loaded.")

except (psycopg2.Error, OSError) as error:
    # psycopg2.Error = any database problem; OSError = a problem reading a file.
    # Undo everything since the connection opened, so no half-loaded tables remain.
    if connection is not None:
        connection.rollback()
    print("Error: the load failed and was rolled back. No changes were saved.")
    print(f"Details: {error}")
    raise SystemExit(1)

finally:
    # Always close the cursor and connection, whether the load worked or not.
    if cursor is not None:
        cursor.close()
    if connection is not None:
        connection.close()
