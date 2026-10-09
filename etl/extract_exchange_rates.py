# extract_exchange_rates.py
# Purpose: Download the monthly average USD-to-CAD exchange rate from the
#          Bank of Canada and save the API response, unchanged, as raw JSON.
# Run from the project folder:  python etl/extract_exchange_rates.py

from pathlib import Path   # helps build file paths that work on any computer

import requests            # downloads data from the internet

# --- 1. Where the data comes from ---------------------------------------------
# Bank of Canada Valet API (docs: https://www.bankofcanada.ca/valet/docs).
# Series FXMUSDCAD = monthly average value of 1 U.S. dollar in Canadian dollars.
# With no date filters, the API returns every available month.
API_URL = "https://www.bankofcanada.ca/valet/observations/FXMUSDCAD/json"

# --- 2. Download the data -----------------------------------------------------
response = requests.get(API_URL, timeout=60)
response.raise_for_status()  # stop with a clear error if the download failed

# Read the JSON so we can count the observations (this does not change the file).
data = response.json()
observation_count = len(data["observations"])  # one observation = one month

# --- 3. Save the raw data -----------------------------------------------------
# Build the path from this file's location so it works from any folder.
project_root = Path(__file__).resolve().parent.parent
output_folder = project_root / "data" / "raw"
output_folder.mkdir(parents=True, exist_ok=True)  # create the folder if it's missing

# Write the exact bytes the API sent us, so the file is the original response.
output_file = output_folder / "exchange_rates_raw.json"
output_file.write_bytes(response.content)

# --- 4. Confirm it worked -----------------------------------------------------
print(f"Downloaded {observation_count} observations")
print(f"Saved to {output_file}")
