"""
etl_pipeline_sqlite.py – Load cleaned CSVs into SQLite database
"""

import pandas as pd
import sqlite3
from pathlib import Path

# ==============================================
# CONFIGURATION
# ==============================================
DB_PATH = Path("data/db/bluestock_mf.db")
RAW_PATH = Path("data/raw")
PROCESSED_PATH = Path("data/processed")

# Ensure the database directory exists
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

# Connect to SQLite (creates file if not exists)
conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

print("="*60)
print("SQLITE ETL PIPELINE")
print("="*60)

# ==============================================
# 1. Load cleaned CSV files
# ==============================================
print("\n📂 Loading CSV files...")

fund_master = pd.read_csv(RAW_PATH / "01_fund_master.csv")
print(f"  ✅ 01_fund_master: {fund_master.shape}")

nav_clean = pd.read_csv(PROCESSED_PATH / "02_nav_history_cleaned.csv")
print(f"  ✅ 02_nav_history_cleaned: {nav_clean.shape}")

trans_clean = pd.read_csv(PROCESSED_PATH / "08_investor_transactions_cleaned.csv")
print(f"  ✅ 08_investor_transactions_cleaned: {trans_clean.shape}")

perf_clean = pd.read_csv(PROCESSED_PATH / "07_scheme_performance_cleaned.csv")
print(f"  ✅ 07_scheme_performance_cleaned: {perf_clean.shape}")

aum_clean = pd.read_csv(PROCESSED_PATH / "03_aum_by_fund_house_cleaned.csv")
print(f"  ✅ 03_aum_by_fund_house_cleaned: {aum_clean.shape}")

# ==============================================
# 2. Create dim_date
# ==============================================
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

cur.execute("DROP TABLE IF EXISTS dim_date")
date_df.to_sql('dim_date', conn, if_exists='replace', index=False)
print(f"  ✅ dim_date: {len(date_df)} rows")

# ==============================================
# 3. dim_fund
# ==============================================
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
cur.execute("DROP TABLE IF EXISTS dim_fund")
fund_df.to_sql('dim_fund', conn, if_exists='replace', index=False)
print(f"  ✅ dim_fund: {len(fund_df)} rows")

# ==============================================
# 4. fact_nav
# ==============================================
print("\n📈 Creating fact_nav...")
nav_fact = nav_clean.rename(columns={date_col: 'full_date'})
nav_fact = nav_fact.merge(date_df[['full_date', 'date_id']], on='full_date', how='left')
nav_col = [col for col in nav_fact.columns if col.lower() in ['nav', 'net_asset_value']][0]
code_col = [col for col in nav_fact.columns if 'code' in col.lower()][0]
nav_fact = nav_fact[[code_col, 'date_id', nav_col]].rename(columns={code_col: 'scheme_code', nav_col: 'nav_value'})
nav_fact = nav_fact.dropna(subset=['scheme_code', 'date_id'])
nav_fact['date_id'] = nav_fact['date_id'].astype(int)
cur.execute("DROP TABLE IF EXISTS fact_nav")
nav_fact.to_sql('fact_nav', conn, if_exists='replace', index=False)
print(f"  ✅ fact_nav: {len(nav_fact)} rows")

# ==============================================
# 5. fact_transactions
# ==============================================
print("\n💸 Creating fact_transactions...")
trans_date_col = [col for col in trans_clean.columns if 'date' in col.lower()][0]
trans_clean[trans_date_col] = pd.to_datetime(trans_clean[trans_date_col])
trans_fact = trans_clean.rename(columns={trans_date_col: 'full_date'})
trans_fact = trans_fact.merge(date_df[['full_date', 'date_id']], on='full_date', how='left')
trans_fact = trans_fact.dropna(subset=['date_id'])
trans_fact['date_id'] = trans_fact['date_id'].astype(int)
trans_fact = trans_fact[trans_fact['date_id'].isin(date_df['date_id'])]
# Find scheme code column
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
cur.execute("DROP TABLE IF EXISTS fact_transactions")
trans_fact.to_sql('fact_transactions', conn, if_exists='replace', index=False)
print(f"  ✅ fact_transactions: {len(trans_fact)} rows")

# ==============================================
# 6. fact_performance – skip if no date column
# ==============================================
print("\n📊 Creating fact_performance...")
# Check if a date column exists in perf_clean (e.g., 'date')
perf_date_candidates = [col for col in perf_clean.columns if 'date' in col.lower()]
if perf_date_candidates:
    perf_date_col = perf_date_candidates[0]
    perf_clean[perf_date_col] = pd.to_datetime(perf_clean[perf_date_col])
    perf_fact = perf_clean.rename(columns={perf_date_col: 'full_date'})
    perf_fact = perf_fact.merge(date_df[['full_date', 'date_id']], on='full_date', how='left')
    perf_fact = perf_fact.rename(columns={'date_id': 'as_of_date_id'})
    # Keep only columns that exist in schema (adjust as needed)
    table_cols = ['scheme_code', 'as_of_date_id', 'return_1m', 'return_3m', 'return_6m', 'return_1y',
                  'return_3y', 'return_5y', 'expense_ratio', 'sharpe_ratio', 'alpha', 'beta']
    # Map scheme code column (might be 'amfi_code')
    if 'amfi_code' in perf_fact.columns:
        perf_fact = perf_fact.rename(columns={'amfi_code': 'scheme_code'})
    perf_fact = perf_fact[[c for c in table_cols if c in perf_fact.columns]]
    cur.execute("DROP TABLE IF EXISTS fact_performance")
    perf_fact.to_sql('fact_performance', conn, if_exists='replace', index=False)
    print(f"  ✅ fact_performance: {len(perf_fact)} rows")
else:
    print("  ⚠️ No date column found in performance data. Skipping fact_performance.")
    cur.execute("DROP TABLE IF EXISTS fact_performance")
    # Create empty table with correct schema (optional)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS fact_performance (
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
            beta REAL
        )
    """)
    print("  ⚠️ fact_performance table created but left empty.")

# ==============================================
# 7. fact_aum
# ==============================================
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
cur.execute("DROP TABLE IF EXISTS fact_aum")
aum_fact.to_sql('fact_aum', conn, if_exists='replace', index=False)
print(f"  ✅ fact_aum: {len(aum_fact)} rows")

# ==============================================
# 8. Create indexes
# ==============================================
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
    conn.execute(idx)
conn.commit()
print("  ✅ All indexes created")

# ==============================================
# 9. Verification
# ==============================================
print("\n" + "="*60)
print("VERIFICATION – ROW COUNTS")
print("="*60)
tables = ['dim_fund', 'dim_date', 'fact_nav', 'fact_transactions', 'fact_performance', 'fact_aum']
for table in tables:
    cur.execute(f"SELECT COUNT(*) FROM {table}")
    count = cur.fetchone()[0]
    print(f"  {table:20} : {count:>8} rows")

cur.close()
conn.close()
print("\n✅ ETL Pipeline (SQLite) completed successfully!")