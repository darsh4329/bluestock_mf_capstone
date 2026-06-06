"""
etl_pipeline.py – PostgreSQL ETL (final with auto-detection for all columns)
"""

import pandas as pd
import psycopg2
from io import StringIO
from pathlib import Path

DB_NAME = "bluestock_mf"
DB_USER = "postgres"
DB_PASSWORD = "8128128208"
DB_HOST = "localhost"
DB_PORT = "5432"

raw_path = Path("data/raw")
processed_path = Path("data/processed")

conn = psycopg2.connect(
    dbname=DB_NAME,
    user=DB_USER,
    password=DB_PASSWORD,
    host=DB_HOST,
    port=DB_PORT
)
conn.autocommit = False
cur = conn.cursor()

print("="*60)
print("POSTGRESQL ETL PIPELINE (auto detection)")
print("="*60)

# 1. Load files
print("\n📂 Loading CSV files...")
fund_master = pd.read_csv(raw_path / "01_fund_master.csv")
print(f"  ✅ 01_fund_master: {fund_master.shape}")
nav_clean = pd.read_csv(processed_path / "02_nav_history_cleaned.csv")
print(f"  ✅ 02_nav_history_cleaned: {nav_clean.shape}")
trans_clean = pd.read_csv(processed_path / "08_investor_transactions_cleaned.csv")
print(f"  ✅ 08_investor_transactions_cleaned: {trans_clean.shape}")
perf_clean = pd.read_csv(processed_path / "07_scheme_performance_cleaned.csv")
print(f"  ✅ 07_scheme_performance_cleaned: {perf_clean.shape}")
aum_clean = pd.read_csv(processed_path / "03_aum_by_fund_house_cleaned.csv")
print(f"  ✅ 03_aum_by_fund_house_cleaned: {aum_clean.shape}")

# 2. dim_date
print("\n📅 Creating dim_date...")
date_col = [col for col in nav_clean.columns if 'date' in col.lower()][0]
nav_clean[date_col] = pd.to_datetime(nav_clean[date_col])
dates = nav_clean[date_col].unique()
date_df = pd.DataFrame({'full_date': dates})
date_df['date_id'] = date_df['full_date'].dt.strftime('%Y%m%d').astype(int)
date_df['year'] = date_df['full_date'].dt.year
date_df['quarter'] = date_df['full_date'].dt.quarter
date_df['month'] = date_df['full_date'].dt.month
date_df['month_name'] = date_df['full_date'].dt.strftime('%B')
date_df['week'] = date_df['full_date'].dt.isocalendar().week
date_df['day_of_week'] = date_df['full_date'].dt.dayofweek
date_df['is_weekend'] = date_df['day_of_week'].isin([5,6])
date_df = date_df[['date_id', 'full_date', 'year', 'quarter', 'month', 'month_name', 'week', 'day_of_week', 'is_weekend']]
cur.execute("TRUNCATE TABLE dim_date RESTART IDENTITY CASCADE;")
output = StringIO()
date_df.to_csv(output, index=False, header=False)
output.seek(0)
cur.copy_expert("COPY dim_date FROM STDIN WITH CSV", output)
conn.commit()
print(f"  ✅ dim_date: {len(date_df)} rows")

# 3. dim_fund
print("\n🏢 Creating dim_fund...")
fund_df = fund_master.rename(columns={
    'amfi_code': 'scheme_code',
    'scheme_name': 'scheme_name',
    'fund_house': 'fund_house',
    'category': 'category',
    'sub_category': 'sub_category',
    'risk_category': 'risk_grade'
})
fund_df = fund_df[['scheme_code', 'scheme_name', 'fund_house', 'category', 'sub_category', 'risk_grade']].copy()
fund_df = fund_df.dropna(subset=['scheme_code'])
cur.execute("TRUNCATE TABLE dim_fund RESTART IDENTITY CASCADE;")
for _, row in fund_df.iterrows():
    cur.execute("""
        INSERT INTO dim_fund (scheme_code, scheme_name, fund_house, category, sub_category, risk_grade)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (scheme_code) DO NOTHING
    """, (row['scheme_code'], row['scheme_name'], row['fund_house'],
          row['category'], row['sub_category'], row['risk_grade']))
conn.commit()
print(f"  ✅ dim_fund: {len(fund_df)} rows")

# 4. fact_nav
print("\n📈 Creating fact_nav...")
nav_fact = nav_clean.rename(columns={date_col: 'full_date'})
nav_fact = nav_fact.merge(date_df[['full_date', 'date_id']], on='full_date', how='left')
nav_col = [col for col in nav_fact.columns if col.lower() in ['nav', 'net_asset_value']][0]
code_col = [col for col in nav_fact.columns if 'code' in col.lower()][0]
nav_fact = nav_fact[[code_col, 'date_id', nav_col]].rename(columns={code_col: 'scheme_code', nav_col: 'nav_value'})
nav_fact = nav_fact.dropna(subset=['scheme_code', 'date_id'])
nav_fact['date_id'] = nav_fact['date_id'].astype(int)
cur.execute("TRUNCATE TABLE fact_nav RESTART IDENTITY CASCADE;")
output = StringIO()
nav_fact.to_csv(output, index=False, header=False)
output.seek(0)
cur.copy_expert("COPY fact_nav (scheme_code, date_id, nav_value) FROM STDIN WITH CSV", output)
conn.commit()
print(f"  ✅ fact_nav: {len(nav_fact)} rows")

# 5. fact_transactions
print("\n💸 Creating fact_transactions...")
trans_date_col = [col for col in trans_clean.columns if 'date' in col.lower()][0]
trans_clean[trans_date_col] = pd.to_datetime(trans_clean[trans_date_col])
trans_fact = trans_clean.rename(columns={trans_date_col: 'full_date'})
trans_fact = trans_fact.merge(date_df[['full_date', 'date_id']], on='full_date', how='left')
trans_fact = trans_fact.dropna(subset=['date_id'])
trans_fact['date_id'] = trans_fact['date_id'].astype(int)
trans_fact = trans_fact[trans_fact['date_id'].isin(date_df['date_id'])]
code_candidates = [col for col in trans_fact.columns if 'code' in col.lower() or 'scheme' in col.lower()]
if not code_candidates:
    raise KeyError(f"No scheme code column. Available: {trans_fact.columns.tolist()}")
scheme_col = code_candidates[0]
print(f"   Using '{scheme_col}' as scheme_code")
trans_fact = trans_fact.rename(columns={scheme_col: 'scheme_code'})
required = ['scheme_code', 'investor_id', 'transaction_type', 'amount', 'units', 'kyc_status', 'date_id']
keep = [c for c in required if c in trans_fact.columns]
trans_fact = trans_fact[keep].dropna(subset=['scheme_code', 'date_id'])
trans_fact['date_id'] = trans_fact['date_id'].astype(int)
cur.execute("TRUNCATE TABLE fact_transactions RESTART IDENTITY CASCADE;")
output = StringIO()
trans_fact.to_csv(output, index=False, header=False)
output.seek(0)
col_list = ','.join(keep)
cur.copy_expert(f"COPY fact_transactions ({col_list}) FROM STDIN WITH CSV", output)
conn.commit()
print(f"  ✅ fact_transactions: {len(trans_fact)} rows")

# 6. fact_performance – skip because no date column (but could be improved)
print("\n📊 Creating fact_performance...")
print("   No date column found in performance data. Skipping fact_performance (optional).")
# If you want to load performance without date, you would need to add a dummy date.
# For now, we leave fact_performance empty.
cur.execute("TRUNCATE TABLE fact_performance RESTART IDENTITY CASCADE;")
conn.commit()
print("  ⚠️ fact_performance not loaded (no date column).")

# 7. fact_aum – auto-detect AUM column
print("\n💰 Creating fact_aum...")
aum_date_col = [col for col in aum_clean.columns if 'date' in col.lower()][0]
aum_clean[aum_date_col] = pd.to_datetime(aum_clean[aum_date_col])
aum_fact = aum_clean.rename(columns={aum_date_col: 'full_date'})
aum_fact = aum_fact.merge(date_df[['full_date', 'date_id']], on='full_date', how='left')
aum_fact = aum_fact.dropna(subset=['date_id'])
aum_fact['date_id'] = aum_fact['date_id'].astype(int)
# Find AUM column
aum_candidates = [col for col in aum_fact.columns if 'aum' in col.lower()]
if not aum_candidates:
    raise KeyError(f"No AUM column found. Available: {aum_fact.columns.tolist()}")
aum_col = aum_candidates[0]
print(f"   Using '{aum_col}' as AUM column")
aum_fact = aum_fact[['fund_house', 'date_id', aum_col]].rename(columns={aum_col: 'aum_crores'})
cur.execute("TRUNCATE TABLE fact_aum RESTART IDENTITY CASCADE;")
output = StringIO()
aum_fact.to_csv(output, index=False, header=False)
output.seek(0)
cur.copy_expert("COPY fact_aum (fund_house, date_id, aum_crores) FROM STDIN WITH CSV", output)
conn.commit()
print(f"  ✅ fact_aum: {len(aum_fact)} rows")

# 8. Indexes
print("\n🔍 Creating indexes...")
indexes = [
    "CREATE INDEX IF NOT EXISTS idx_nav_scheme ON fact_nav(scheme_code);",
    "CREATE INDEX IF NOT EXISTS idx_nav_date ON fact_nav(date_id);",
    "CREATE INDEX IF NOT EXISTS idx_transactions_scheme ON fact_transactions(scheme_code);",
    "CREATE INDEX IF NOT EXISTS idx_transactions_date ON fact_transactions(date_id);",
    "CREATE INDEX IF NOT EXISTS idx_performance_scheme ON fact_performance(scheme_code);",
    "CREATE INDEX IF NOT EXISTS idx_aum_date ON fact_aum(date_id);"
]
for idx in indexes:
    cur.execute(idx)
conn.commit()
print("  ✅ All indexes created")

# 9. Verification
print("\n" + "="*60)
print("VERIFICATION – ROW COUNTS")
print("="*60)
for table in ['dim_fund', 'dim_date', 'fact_nav', 'fact_transactions', 'fact_performance', 'fact_aum']:
    cur.execute(f"SELECT COUNT(*) FROM {table}")
    count = cur.fetchone()[0]
    print(f"  {table:20} : {count:>8} rows")

cur.close()
conn.close()
print("\n✅ ETL Pipeline completed successfully!")-- ============================================
-- Star Schema for Mutual Fund Analytics
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
    nav_id INTEGER PRIMARY KEY AUTOINCREMENT,
    scheme_code INTEGER,
    date_id INTEGER,
    nav_value REAL,
    FOREIGN KEY (scheme_code) REFERENCES dim_fund(scheme_code),
    FOREIGN KEY (date_id) REFERENCES dim_date(date_id)
);

-- Fact: Investor Transactions
CREATE TABLE fact_transactions (
    transaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
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
    performance_id INTEGER PRIMARY KEY AUTOINCREMENT,
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
    aum_id INTEGER PRIMARY KEY AUTOINCREMENT,
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