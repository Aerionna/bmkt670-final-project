# extract_canadian_travel.py
# Purpose: Download the monthly number of Canadian residents returning from the
#          United States by automobile (all travellers, same-day and overnight)
#          from Statistics Canada and save the API response, unchanged, as raw JSON.
# Run from the project folder:  python etl/extract_canadian_travel.py

from datetime import date  # gives today's date for the end of the date range
from pathlib import Path   # helps build file paths that work on any computer

import requests            # downloads data from the internet

# --- 1. Where the data comes from ---------------------------------------------
# Statistics Canada Web Data Service (WDS)
# (docs: https://www.statcan.gc.ca/en/developers/wds/user-guide).
# Vector 1296956601 is one series from table 24-10-0053-01:
#   GEO = Canada
#   Traveller characteristics = Canadian residents returning from the
#                               United States of America, land, automobile
#   Traveller type = Travellers (same-day and overnight trips together)
API_URL = "https://www150.statcan.gc.ca/t1/wds/rest/getDataFromVectorByReferencePeriodRange"

params = {
    "vectorIds": '"1296956601"',                     # the API expects the ID inside double quotes
    "startRefPeriod": "2017-01-01",                  # first month to return
    "endReferencePeriod": date.today().isoformat(),  # last month to return: today (YYYY-MM-DD)
}

# --- 2. Download the data -----------------------------------------------------
response = requests.get(API_URL, params=params, timeout=60)
response.raise_for_status()  # stop with a clear error if the download failed

# A successful answer is a list with one entry per vector:
# [{"status": "SUCCESS", "object": {..., "vectorDataPoint": [...]}}]
api_result = response.json()
if not api_result or api_result[0].get("status") != "SUCCESS":
    raise SystemExit(f"Error: the API did not return SUCCESS. Response was: {api_result}")

# Read the observations so we can count them (this does not change the file).
data_points = api_result[0]["object"]["vectorDataPoint"]  # one data point = one month

# --- 3. Save the raw data -----------------------------------------------------
# Build the path from this file's location so it works from any folder.
project_root = Path(__file__).resolve().parent.parent
output_folder = project_root / "data" / "raw"
output_folder.mkdir(parents=True, exist_ok=True)  # create the folder if it's missing

# Write the exact bytes the API sent us, so the file is the original response.
output_file = output_folder / "canadian_travel_raw.json"
output_file.write_bytes(response.content)

# --- 4. Confirm it worked -----------------------------------------------------
print(f"Downloaded {len(data_points)} items in vectorDataPoint")
print(f"Saved to {output_file}")
