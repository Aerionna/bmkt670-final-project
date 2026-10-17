# Missing Data

| Table | Column | % missing | Decision | Why |
| :---- | :----- | :-------- | :------- | :-- |
| fact_border_crossings | passenger_crossings | 0.50% before treatment | Fill the seven absent Willow Creek records for April–October 2017 with the same port’s values from the corresponding months in 2016 | The gap appears to be a reporting omission rather than zero traffic. Prior-year matching months preserve the port’s seasonal pattern and use only information available before the missing period. |

## Notes

- **How the percentage was calculated:** 7 missing values out of 1,392
  expected port-month observations (12 active ports × 116 months, January 2017
  to August 2026). 7 / 1,392 = 0.50%.
- **The seven filled values are estimates, not reported 2017 observations.**
  `etl/transform.py` looks them up from Willow Creek’s (port 3325) 2016 rows in
  `data/raw/border_crossings_raw.csv` and copies each one into the same month of
  2017. The raw file is not changed.

  | 2017 month | Filled value | Copied from |
  | :--------- | -----------: | :---------- |
  | April | 409 | April 2016 |
  | May | 493 | May 2016 |
  | June | 534 | June 2016 |
  | July | 857 | July 2016 |
  | August | 797 | August 2016 |
  | September | 493 | September 2016 |
  | October | 421 | October 2016 |

- **All other columns in the five clean tables have 0% missing values.** This
  covers every column in `dim_month`, `dim_port`, `fact_border_crossings`,
  `fact_exchange_rates` and `fact_national_travel`.
- **COVID-period values remain unchanged.** The very low counts in 2020 and
  2021 (for example, the statewide total of 2,621 in April 2020) are reported
  observations, not missing data, so they are not filled or adjusted.
