# Field Sources

This data dictionary traces every field in `sql/schema.sql` back to the raw
files in `data/raw/`, which the scripts in `etl/` produce.

The project predicts **one statewide Montana monthly total** of inbound
personal-vehicle passenger crossings. The border-crossing tables keep
port-level detail. The future ML feature table (not part of `schema.sql`) will
add the ports together into one statewide row per month and join the other
monthly tables on `month_id`.

Raw files:

| Raw file | Produced by | Source |
|---|---|---|
| `data/raw/border_crossings_raw.csv` | `etl/extract_border_crossings.py` | Bureau of Transportation Statistics (BTS), Border Crossing Entry Data (`keg4-3bc2`) |
| `data/raw/exchange_rates_raw.json` | `etl/extract_exchange_rates.py` | Bank of Canada Valet API, series `FXMUSDCAD` |
| `data/raw/canadian_travel_raw.json` | `etl/extract_canadian_travel.py` | Statistics Canada Web Data Service `getDataFromVectorByReferencePeriodRange`, vector `1296956601` (table 24-10-0053-01) |

## Field Table

| Table | Field | Comes from | How | Used for |
|---|---|---|---|---|
| dim_month | month_id | BTS `date`, Bank of Canada `observations[].d`, Statistics Canada `vectorDataPoint[].refPer` | Calculated in Python in YYYYMM format (for example, `2026-08-01T00:00:00.000` → `202608`; `2026-07-01` → `202607`). One row per calendar month. | **Key.** Primary key of `dim_month` and the shared join key that lines up all monthly tables in the future ML feature table. |
| dim_month | month_start | Same source date fields as `month_id` | Calculated in Python as the first day of the month (for example, `2026-08-01`). | **Dashboard field.** Date axis for time-series charts. Also used to sort months when building lagged features. |
| dim_month | year | Same source date fields as `month_id` | Calculated in Python from the month date (for example, `2026`). | **Dashboard field.** Filters and groups by year. Possible **input to future features**, such as a trend term. |
| dim_month | month_number | Same source date fields as `month_id` | Calculated in Python from the month date (1–12). | **Input to future features.** Captures seasonality, for example as a month indicator. Also a **dashboard field.** |
| dim_month | month_name | Same source date fields as `month_id` | Calculated in Python from the month date (for example, `August`). | **Dashboard field.** Readable month label. |
| dim_port | port_code | BTS `port_code` | Copied from the raw CSV and stored as text (the raw file holds it as a number, for example `3301`). One row per distinct port. | **Key.** Primary key of `dim_port`. |
| dim_port | port_name | BTS `port_name` | Copied from the raw CSV (for example, `Sweetgrass`). The raw file has exactly one name per `port_code`. | **Dashboard field.** Port label for port-level charts and maps. |
| fact_border_crossings | month_id | Joined from `dim_month.month_id` | Calculated in Python from BTS `date` in YYYYMM format, then matched to `dim_month` (foreign key). | **Key.** Part of the composite primary key; links each port-month to its month. Used to group ports into statewide monthly totals. |
| fact_border_crossings | port_code | Joined from `dim_port.port_code` | Taken from BTS `port_code`, stored as text, and matched to `dim_port` (foreign key). | **Key.** Part of the composite primary key. Not a model feature, because the model works at the statewide level. Supports port-level dashboard views. |
| fact_border_crossings | passenger_crossings | BTS `value` | Copied from the raw CSV. The rows are already limited to Montana, the U.S.–Canada border and `Personal Vehicle Passengers`. | **Model outcome.** The historical target the model learns from, after the port values are added together for each month to give one statewide total. Lagged statewide totals can also be **inputs to future features**. Port-level values are a **dashboard field.** |
| fact_exchange_rates | month_id | Joined from `dim_month.month_id` | Calculated in Python from Bank of Canada `observations[].d` (for example, `2026-09-01` → `202609`) in YYYYMM format, then matched to `dim_month` (foreign key). | **Key.** Primary key and link to `dim_month`; joins the rate to the statewide monthly row. |
| fact_exchange_rates | usd_cad_rate | Bank of Canada `observations[].FXMUSDCAD.v` | Converted from a text string (for example, `"1.3962"`) to a number. It is the monthly average value of 1 U.S. dollar in Canadian dollars. | **Model feature, or input to lagged features** (for example, the prior month's rate). A higher value means the U.S. is more expensive for Canadians. Also a **dashboard field.** |
| fact_national_travel | month_id | Joined from `dim_month.month_id` | Calculated in Python from Statistics Canada `vectorDataPoint[].refPer` (for example, `2026-07-01` → `202607`) in YYYYMM format, then matched to `dim_month` (foreign key). | **Key.** Primary key and link to `dim_month`; joins the national travel count to the statewide monthly row. |
| fact_national_travel | canadian_auto_return_trips | Statistics Canada `vectorDataPoint[].value` | Converted from a decimal-format number (for example, `2198865.0`) to an integer. The API request already limits the data to vector `1296956601`, which counts all Canadian residents returning from the U.S. by automobile (same-day and overnight). | **Model feature, or input to lagged features** (for example, the prior month's national count). It shows the national trend in Canadians driving to the U.S. Also a **dashboard field.** |

## Source Fields Used but Not Stored

These source columns are used to filter, select records, create keys or
validate the data. Their values are not stored as fields in the schema.

### BTS: `border_crossings_raw.csv`

| Source column | Value used | Purpose |
|---|---|---|
| `state` | `Montana` | API filter (`$where`) in `extract_border_crossings.py`. Keeps Montana ports only. |
| `border` | `US-Canada Border` | API filter. Excludes U.S.–Mexico ports. |
| `measure` | `Personal Vehicle Passengers` | API filter. Keeps people in personal vehicles, not `Personal Vehicles` (the vehicle count), buses, trucks or pedestrians. |
| `date` | All months (raw range `1996-01` to `2026-08`) | Used to create `month_id` and the other `dim_month` fields. Not stored in its raw timestamp form. |
| `latitude`, `longitude`, `point` | n/a | Not used and not stored. They could support a future map. |

Validation checked against the raw file: all 4,433 rows have the three filter
values above. Each `port_code` has exactly one `port_name` (13 ports). There
are no duplicate port-month rows and no missing `value` entries.

### Bank of Canada: `exchange_rates_raw.json`

| Source field | Value used | Purpose |
|---|---|---|
| Series ID `FXMUSDCAD` (in the API URL and as the key in `seriesDetail` and each observation) | `FXMUSDCAD` | Selects the monthly average USD/CAD series. `seriesDetail.FXMUSDCAD.description` confirms "Monthly average exchange rate of the US dollar in Canadian dollars." Used for validation. |
| `observations[].d` | All months (raw range `2017-01-01` to `2026-09-01`, 117 months) | Used to create `month_id`. Not stored in its raw form. |

### Statistics Canada: `canadian_travel_raw.json`

| Source field | Value used | Purpose |
|---|---|---|
| `vectorIds` (API parameter) | `"1296956601"` | Selects the single series used. See the series choice note below. |
| `startRefPeriod` (API parameter) | `2017-01-01` | API filter: first month returned, matching the start of the Bank of Canada data. |
| `endReferencePeriod` (API parameter) | Today's date, generated in Python | API filter: last month returned (the latest published month). |
| `status` | `SUCCESS` | Validation: the script stops if the API does not return `SUCCESS`. |
| `object.vectorId`, `object.productId`, `object.coordinate` | `1296956601`, `24100053`, `1.47.1.0.0.0.0.0.0.0` | Validation: confirms the response is the requested series from table 24-10-0053-01. |
| `vectorDataPoint[].refPer` | All months returned (`2017-01-01` to `2026-07-01`, 115 points on 2026-10-07) | Used to create `month_id`. Not stored in its raw form. |
| `vectorDataPoint[].statusCode`, `symbolCode`, `scalarFactorCode` | `0` expected | Validation: `0` means a normal value with no status flag, reported in units (not thousands). |
| `refPer2`, `refPerRaw`, `refPerRaw2`, `decimals`, `securityLevelCode`, `releaseTime`, `frequencyCode` | n/a | Not used and not stored. |

The series is **not seasonally adjusted.** Table 24-10-0053-01 publishes only
unadjusted counts.

## Statistics Canada Series Choice

Vector `1296956601` was chosen (decision made 2026-10-07). In table
24-10-0053-01 it is the series with:

- `GEO` = `Canada`
- `Traveller characteristics` = `Canadian residents returning from the United States of America, land, automobile`
- `Traveller type` = `Travellers` (same-day and overnight trips together)

The same table has two narrower alternatives that were not used:
`Excursionists (same-day)` (vector `1296956602`) and `Tourists (overnight)`
(vector `1296956603`).

## Coverage Notes

- Monthly ranges in the raw files: BTS `1996-01`–`2026-08`, Bank of Canada
  `2017-01`–`2026-09`, Statistics Canada `2017-01`–`2026-07` (start set by
  `startRefPeriod`). An inner join on
  `month_id` across all three gives about `2017-01`–`2026-07`.
- See the Data Limitations section in `README.md`. BTS counts crossings, not
  unique travelers or nationality. Statistics Canada is a national trend and
  does not identify Montana as the destination.
