"""Quick check that we can connect to the PostgreSQL database and see its tables."""

# --- Imports ---
# os: lets us read environment variables (settings stored outside the code).
import os

# psycopg2: the library Python uses to talk to a PostgreSQL database.
import psycopg2
# load_dotenv: reads a local .env file and loads its values as environment variables.
from dotenv import load_dotenv

# --- Load settings ---
# Read the .env file in this folder so os.getenv() can find our database settings.
# Keeping passwords in .env (not in the code) means they don't end up on GitHub.
load_dotenv()

# --- Connection details ---
# Gather everything psycopg2 needs to find and log in to the database.
# Each value comes from the .env file; if one is missing, os.getenv() returns None.
db_config = {
    "host": os.getenv("DB_HOST"),          # server address, e.g. "localhost"
    "port": os.getenv("DB_PORT"),          # PostgreSQL's port, usually 5432
    "dbname": os.getenv("DB_NAME"),        # which database on the server to use
    "user": os.getenv("DB_USER"),          # the username to log in with
    "password": os.getenv("DB_PASSWORD"),  # that user's password
}

# --- SQL query ---
# Ask PostgreSQL for the names of all tables in the "public" schema
# (the default place where tables are created), sorted alphabetically.
# information_schema.tables is a built-in view that lists every table.
table_query = """
    SELECT table_name
    FROM information_schema.tables
    WHERE table_schema = 'public'
    ORDER BY table_name;
"""

# --- Talk to the database ---
# Open a connection using the settings above. The ** "unpacks" the dictionary,
# so this is the same as connect(host=..., port=..., dbname=..., ...).
with psycopg2.connect(**db_config) as connection:
    # A cursor is the object that actually sends SQL and holds the results.
    # Using "with" closes the cursor automatically when we're done.
    with connection.cursor() as cursor:
        # Confirm which database we're connected to.
        # fetchone() returns one row as a tuple, so [0] grabs its first value.
        cursor.execute("SELECT current_database();")
        database_name = cursor.fetchone()[0]

        # Run the table-listing query. fetchall() returns every row as a
        # list of tuples, e.g. [("crossings",), ("months",)].
        cursor.execute(table_query)
        tables = cursor.fetchall()

# --- Show the results ---
# Print the database name and how many tables were found.
print(f"Database: {database_name}")
print(f"Tables found: {len(tables)}")

# Print each table name on its own line. Each row is a one-item tuple,
# so table[0] pulls out the name itself.
for table in tables:
    print(f"- {table[0]}")
