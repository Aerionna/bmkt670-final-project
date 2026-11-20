# Canadian Visitation to Montana 

## Business Question
How many inbound personal-vehicle passenger crossings should Montana expect at its Canadian border ports next month?

## Target Variable
Monthly inbound personal-vehicle passenger crossings at Montana–Canada ports.

## Prediction Unit
One row in my ML feature table = one month of statewide Montana crossings.

## Data Sources
| Source | What It Provides | Access |
|---|---|---|
| [Bureau of Transportation Statistics: Border Crossing Entry Data](https://data.transportation.gov/Research-and-Statistics/Border-Crossing-Entry-Data/keg4-3bc2) | Monthly inbound U.S.–Canada border-crossing statistics by state, port, mode and measure, including personal vehicles and passengers. | CSV export or API |
| [Bank of Canada: Monthly Exchange Rates](https://www.bankofcanada.ca/rates/exchange/monthly-exchange-rates/) | Monthly exchange rates between the Canadian dollar and the U.S. dollar. | CSV, JSON or XML |
| [Statistics Canada: Travel Between Canada and Other Countries](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=2410005301) | National Canada–U.S. travel trends, including Canadian residents returning from the United States. | [CSV download or Web Data Service API](https://www.statcan.gc.ca/en/developers/wds/user-guide) |

[For hand-downloaded files, list the URL, date downloaded, and the clicks or filters you used.]

## How to Run
Prerequisites:
- PostgreSQL is running.
- A local `.env` file in the repository's top-level folder contains `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` and `ANTHROPIC_API_KEY`. Every script reads the database password from `DB_PASSWORD` in this file, and `.env` is ignored by Git.

Run every command below from the repository's top-level folder.

1. Activate the virtual environment:

   ```powershell
   .venv\Scripts\Activate.ps1
   ```

2. Install the requirements if needed (the first time, or after `requirements.txt` changes):

   ```powershell
   pip install -r requirements.txt
   ```

3. Run the pipeline first, so PostgreSQL is rebuilt and the saved model file exists:

   ```powershell
   python run_pipeline.py
   ```

   This one command downloads all three raw sources, transforms them into clean tables and the ML feature table, recreates and loads the PostgreSQL database, runs all six quality checks, trains the model (saving its predictions and `model/crossings_model.joblib`), and writes the AI summaries. The final AI-summary step calls the Claude API; a normal full run costs about $0.01.

4. Start the dashboard:

   ```powershell
   streamlit run dashboard/app.py
   ```

   Run this from the top-level folder while the virtual environment is active, so Streamlit uses the project's installed packages. The dashboard opens in a browser. It reads from PostgreSQL and the saved model file and makes no API calls.


## AI Usage
ChatGPT for Final Project scope and organization, ClaudeCode for coding assistance.

## Data Limitations 
- BTS personal-vehicle passenger crossings count entries rather than unique
  travelers. One person may cross the border multiple times.
- The BTS data do not identify nationality, trip purpose, overnight stays or
  final destination. Inbound crossings are therefore a proxy for Canadian
  visitation, not a direct count of Canadian tourists visiting Montana.
- Statistics Canada measures Canadian residents returning to Canada from the
  United States. It provides a national U.S. travel trend but does not identify
  Montana as the destination.