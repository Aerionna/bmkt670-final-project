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
1. Create and activate a virtual environment
2. Install packages: pip install -r requirements.txt
3. Create a .env file with your API keys and DB_PASSWORD 
4. Pull the data: run each script in etl/ (e.g., python etl/extract_games.py)  
5. Build the database: run sql/schema.sql in pgAdmin or psql
6. Confirm it worked: python db_check.py (should print all table names)


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