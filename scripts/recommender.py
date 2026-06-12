
import pandas as pd
from pathlib import Path

def load_data():
    processed_path = Path("data/processed")
    raw_path = Path("data/raw")
    fund_master = pd.read_csv(raw_path / "01_fund_master.csv")
    scorecard = pd.read_csv(processed_path / "fund_scorecard.csv")
    risk_map = fund_master[['amfi_code', 'risk_category']].rename(columns={'risk_category': 'risk_grade'})
    sharpe_data = scorecard[['scheme_name', 'sharpe_ratio']]
    sharpe_data = sharpe_data.merge(fund_master[['scheme_name', 'amfi_code']], on='scheme_name')
    sharpe_data = sharpe_data.merge(risk_map, on='amfi_code')
    risk_mapping = {'Low': 'Low', 'Moderate': 'Moderate', 'High': 'High',
                    'Low Risk': 'Low', 'Medium': 'Moderate', 'High Risk': 'High'}
    sharpe_data['risk_grade_clean'] = sharpe_data['risk_grade'].map(risk_mapping).fillna('Moderate')
    return sharpe_data

def recommend_funds(risk_appetite, top_n=3):
    data = load_data()
    filtered = data[data['risk_grade_clean'] == risk_appetite]
    recommended = filtered.sort_values('sharpe_ratio', ascending=False).head(top_n)
    return recommended[['scheme_name', 'sharpe_ratio', 'risk_grade_clean']]

if __name__ == "__main__":
    print("Fund Recommender")
    print("Available risk appetites: Low, Moderate, High")
    appetite = input("Enter risk appetite: ")
    print(recommend_funds(appetite))
