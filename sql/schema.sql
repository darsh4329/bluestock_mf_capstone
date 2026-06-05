-- ============================================
-- PostgreSQL Star Schema for Mutual Fund Analytics
-- ============================================

-- Dimension: Fund
CREATE TABLE dim_fund (
    scheme_code INTEGER PRIMARY KEY,
    scheme_name TEXT,
    fund_house TEXT,
    category TEXT,
    sub_category TEXT,
    risk_grade TEXT,
    launch_date DATE,
    amc_name TEXT
);

-- Dimension: Date
CREATE TABLE dim_date (
    date_id INTEGER PRIMARY KEY,
    full_date DATE UNIQUE,
    year INTEGER,
    quarter INTEGER,
    month INTEGER,
    month_name TEXT,
    week INTEGER,
    day_of_week INTEGER,
    is_weekend BOOLEAN
);

-- Fact: NAV History
CREATE TABLE fact_nav (
    nav_id SERIAL PRIMARY KEY,          -- Changed from AUTOINCREMENT
    scheme_code INTEGER,
    date_id INTEGER,
    nav_value REAL,
    FOREIGN KEY (scheme_code) REFERENCES dim_fund(scheme_code),
    FOREIGN KEY (date_id) REFERENCES dim_date(date_id)
);

-- Fact: Investor Transactions
CREATE TABLE fact_transactions (
    transaction_id SERIAL PRIMARY KEY,  -- Changed from AUTOINCREMENT
    scheme_code INTEGER,
    date_id INTEGER,
    investor_id TEXT,
    transaction_type TEXT,
    amount REAL,
    units REAL,
    kyc_status TEXT,
    FOREIGN KEY (scheme_code) REFERENCES dim_fund(scheme_code),
    FOREIGN KEY (date_id) REFERENCES dim_date(date_id)
);

-- Fact: Scheme Performance
CREATE TABLE fact_performance (
    performance_id SERIAL PRIMARY KEY,  -- Changed from AUTOINCREMENT
    scheme_code INTEGER,
    as_of_date_id INTEGER,
    return_1m REAL,
    return_3m REAL,
    return_6m REAL,
    return_1y REAL,
    return_3y REAL,
    return_5y REAL,
    expense_ratio REAL,
    sharpe_ratio REAL,
    alpha REAL,
    beta REAL,
    FOREIGN KEY (scheme_code) REFERENCES dim_fund(scheme_code),
    FOREIGN KEY (as_of_date_id) REFERENCES dim_date(date_id)
);

-- Fact: AUM by Fund House
CREATE TABLE fact_aum (
    aum_id SERIAL PRIMARY KEY,          -- Changed from AUTOINCREMENT
    fund_house TEXT,
    date_id INTEGER,
    aum_crores REAL,
    FOREIGN KEY (date_id) REFERENCES dim_date(date_id)
);

-- Indexes for performance
CREATE INDEX idx_nav_scheme ON fact_nav(scheme_code);
CREATE INDEX idx_nav_date ON fact_nav(date_id);
CREATE INDEX idx_transactions_scheme ON fact_transactions(scheme_code);
CREATE INDEX idx_transactions_date ON fact_transactions(date_id);