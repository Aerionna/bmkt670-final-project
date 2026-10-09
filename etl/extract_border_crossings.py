# extract_border_crossings.py
# Purpose: Download monthly border-crossing counts for Montana's Canadian ports
#          and save them, unchanged, as a raw CSV file.
# Run from the project folder:  python etl/extract_border_crossings.py

from io import StringIO    # lets pandas read downloaded text as if it were a file
from pathlib import Path   # helps build file paths that work on any computer

import pandas as pd        # reads and saves table-style data
import requests            # downloads data from the internet

# --- 1. Where the data comes from ---------------------------------------------
# Bureau of Transportation Statistics "Border Crossing Entry Data".
# This dataset only counts INBOUND crossings (people entering the U.S.).
BASE_URL = "https://data.transportation.gov/resource/keg4-3bc2.csv"

# The filters we want. requests will encode the spaces for us,
# which avoids the "URL can't contain control characters" error.
params = {
    "$where": (
        "state='Montana' "
        "AND border='US-Canada Border' "
        "AND measure='Personal Vehicle Passengers'"  # people, not "Personal Vehicles" (cars)
    ),
    "$limit": 50000,  # max rows to return (we expect about 4,400)
}

# --- 2. Download the data -----------------------------------------------------
response = requests.get(BASE_URL, params=params, timeout=60)
response.raise_for_status()  # stop with a clear error if the download failed

# Turn the downloaded text into a pandas table (DataFrame)
df = pd.read_csv(StringIO(response.text))

# --- 3. Save the raw data -----------------------------------------------------
# Build the path from this file's location so it works from any folder.
project_root = Path(__file__).resolve().parent.parent
output_folder = project_root / "data" / "raw"
output_folder.mkdir(parents=True, exist_ok=True)  # create the folder if it's missing

output_file = output_folder / "border_crossings_raw.csv"
df.to_csv(output_file, index=False)

# --- 4. Confirm it worked -----------------------------------------------------
# Each row is one port in one month (not a single crossing).
print(f"Downloaded {len(df)} rows")
print(f"Saved to {output_file}")
