# Adapted from the instructor-provided pipeline example.
import subprocess
import sys

# Scripts to run, in order
steps = [
    "etl/extract_border_crossings.py",  # extract: BTS border crossings API
    "etl/extract_exchange_rates.py",    # extract: Bank of Canada exchange rate API
    "etl/extract_canadian_travel.py",   # extract: Statistics Canada travel API
    "etl/transform.py",                 # clean, match keys, fill gaps, build features
    "etl/load.py",                      # recreate tables, then load into Postgres
    "etl/quality_checks.py",            # print PASS/FAIL for each check
]

for step in steps:
    print(f"\n=== Running {step} ===")
    result = subprocess.run([sys.executable, step], check=False)

    if result.returncode != 0:
        print(f"\nStopped: {step} failed. Fix it and run again.")
        sys.exit(1)

print("\nPipeline finished.")
