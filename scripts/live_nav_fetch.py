"""
live_nav_fetch.py
Fetch live NAV data from mfapi.in API
"""

import requests
import pandas as pd
import json
from pathlib import Path
from datetime import datetime
import time

# Set paths
raw_path = Path("d:/bluestock_mf_capstone/data/raw")
processed_path = Path("d:/bluestock_mf_capstone/data/processed")
db_path = Path("d:/bluestock_mf_capstone/data/db")

# Create directories
raw_path.mkdir(parents=True, exist_ok=True)
processed_path.mkdir(parents=True, exist_ok=True)
db_path.mkdir(parents=True, exist_ok=True)

# Scheme codes to fetch
schemes = {
    "HDFC_Top_100_Direct": "125497",
    "SBI_Bluechip": "119551",
    "ICICI_Bluechip": "120503",
    "Nippon_Large_Cap": "118632",
    "Axis_Bluechip": "119092",
    "Kotak_Bluechip": "120841"
}

def fetch_nav(scheme_code):
    """Fetch NAV data for a scheme code"""
    url = f"https://api.mfapi.in/mf/{scheme_code}"
    
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"❌ Error fetching {scheme_code}: {e}")
        return None

def parse_nav_data(data, scheme_name):
    """Parse JSON response into DataFrame"""
    if not data or "data" not in data:
        return None
    
    nav_data = data.get("data", [])
    if not nav_data:
        return None
    
    df = pd.DataFrame(nav_data)
    df['date'] = pd.to_datetime(df['date'], format='%d-%m-%Y')
    df['nav'] = pd.to_numeric(df['nav'], errors='coerce')
    df['scheme_name'] = scheme_name
    
    return df.sort_values('date')

print("="*60)
print("LIVE NAV FETCHING")
print("="*60)

all_data = []

for name, code in schemes.items():
    print(f"\n📡 Fetching {name} ({code})...")
    
    raw_data = fetch_nav(code)
    
    if raw_data:
        df = parse_nav_data(raw_data, name)
        if df is not None:
            all_data.append(df)
            print(f"   ✅ Got {len(df)} records, Latest NAV: {df['nav'].iloc[-1]:.4f}")
        else:
            print(f"   ❌ Parse failed")
    else:
        print(f"   ❌ Fetch failed")
    
    time.sleep(1)  # Be nice to API

if all_data:
    combined = pd.concat(all_data, ignore_index=True)
    
    # Save to CSV
    output_csv = raw_path / "live_nav_fetched.csv"
    combined.to_csv(output_csv, index=False)
    print(f"\n✅ Saved to: {output_csv}")
    
    # Also save to processed for backup
    output_processed = processed_path / "live_nav_fetched.csv"
    combined.to_csv(output_processed, index=False)
    print(f"✅ Backup saved to: {output_processed}")
    
    # Show latest NAVs
    print("\n📊 LATEST NAVs (as of today):")
    latest = combined.groupby('scheme_name').last().reset_index()
    for _, row in latest.iterrows():
        print(f"   {row['scheme_name']}: ₹{row['nav']:.4f} on {row['date'].date()}")
else:
    print("\n❌ No data fetched!")

print("\n" + "="*60)
print("FETCH COMPLETE")
print("="*60)