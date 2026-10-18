DROP TABLE IF EXISTS ml_features_crossings CASCADE;
DROP TABLE IF EXISTS fact_national_travel CASCADE;
DROP TABLE IF EXISTS fact_exchange_rates CASCADE;
DROP TABLE IF EXISTS fact_border_crossings CASCADE;
DROP TABLE IF EXISTS dim_port CASCADE;
DROP TABLE IF EXISTS dim_month CASCADE;

-- One row represents one calendar month.
CREATE TABLE dim_month (
    month_id       INTEGER PRIMARY KEY,
    month_start    DATE NOT NULL UNIQUE,
    year           INTEGER NOT NULL,
    month_number   INTEGER NOT NULL CHECK (month_number BETWEEN 1 AND 12),
    month_name     TEXT NOT NULL
);


-- One row represents one Montana port on the U.S.-Canada border.
CREATE TABLE dim_port (
    port_code      TEXT PRIMARY KEY,
    port_name      TEXT NOT NULL
);


-- One row represents inbound personal-vehicle passenger crossings
-- at one Montana border port during one month.
CREATE TABLE fact_border_crossings (
    month_id             INTEGER NOT NULL
                         REFERENCES dim_month(month_id),
    port_code            TEXT NOT NULL
                         REFERENCES dim_port(port_code),
    passenger_crossings  INTEGER NOT NULL
                         CHECK (passenger_crossings >= 0),

    PRIMARY KEY (month_id, port_code)
);


-- One row represents the monthly average value of one U.S. dollar
-- expressed in Canadian dollars.
CREATE TABLE fact_exchange_rates (
    month_id       INTEGER PRIMARY KEY
                   REFERENCES dim_month(month_id),
    usd_cad_rate   NUMERIC(10,6) NOT NULL
                   CHECK (usd_cad_rate > 0)
);


-- One row represents the monthly national count of Canadian residents
-- returning from the United States by automobile.
CREATE TABLE fact_national_travel (
    month_id                  INTEGER PRIMARY KEY
                              REFERENCES dim_month(month_id),
    canadian_auto_return_trips INTEGER NOT NULL
                              CHECK (canadian_auto_return_trips >= 0)
);


-- One row represents one statewide Montana month used for modeling.
-- statewide_crossings is the target. Every *_lag1 and rolling field uses
-- prior months only. Winter (December-February) is the baseline season,
-- so a row with is_spring, is_summer and is_fall all equal to 0 is winter.
CREATE TABLE ml_features_crossings (
    month_id              INTEGER PRIMARY KEY
                          REFERENCES dim_month(month_id),
    month_start           DATE NOT NULL UNIQUE,
    year                  INTEGER NOT NULL,
    month_number          INTEGER NOT NULL CHECK (month_number BETWEEN 1 AND 12),
    statewide_crossings   INTEGER NOT NULL CHECK (statewide_crossings >= 0),
    usd_cad_rate_lag1     NUMERIC(10,6) NOT NULL CHECK (usd_cad_rate_lag1 > 0),
    national_travel_lag1  INTEGER NOT NULL CHECK (national_travel_lag1 >= 0),
    crossings_lag1        INTEGER NOT NULL CHECK (crossings_lag1 >= 0),
    crossings_rolling_3   NUMERIC(12,2) NOT NULL CHECK (crossings_rolling_3 >= 0),
    is_spring             SMALLINT NOT NULL CHECK (is_spring IN (0, 1)),
    is_summer             SMALLINT NOT NULL CHECK (is_summer IN (0, 1)),
    is_fall               SMALLINT NOT NULL CHECK (is_fall IN (0, 1)),
    split                 TEXT NOT NULL
                          CHECK (split IN ('train', 'validate', 'test'))
);