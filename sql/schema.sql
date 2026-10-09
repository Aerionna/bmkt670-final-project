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