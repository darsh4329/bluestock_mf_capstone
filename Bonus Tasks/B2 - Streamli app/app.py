# dashboard/app.py (FULLY CORRECTED)
import streamlit as st
import pandas as pd
import numpy as np
import sqlite3
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import os

# ------------------------------
# PAGE CONFIG
# ------------------------------
st.set_page_config(page_title="Bluestock MF Analytics", layout="wide")
st.title("📈 Bluestock Mutual Fund Analytics Dashboard")
st.markdown("---")

# ------------------------------
# DATABASE CONNECTION (NEVER CLOSE)
# ------------------------------
DB_PATH = r"D:\bluestock_mf_capstone\data\db\bluestock_mf.db"

@st.cache_resource
def get_connection():
    return sqlite3.connect(DB_PATH)

@st.cache_data(ttl=3600)
def load_funds():
    conn = get_connection()
    df = pd.read_sql("SELECT scheme_code, scheme_name, category, sub_category, risk_grade FROM dim_fund", conn)
    return df

@st.cache_data(ttl=3600)
def load_nav(scheme_code):
    conn = get_connection()
    query = """
        SELECT d.full_date AS date, n.nav_value AS nav
        FROM fact_nav n
        JOIN dim_date d ON n.date_id = d.date_id
        WHERE n.scheme_code = ?
        ORDER BY d.full_date ASC
    """
    df = pd.read_sql(query, conn, params=(scheme_code,), parse_dates=['date'])
    return df

@st.cache_data(ttl=3600)
def load_metrics():
    """Load precomputed metrics or compute on the fly."""
    metrics_path = r"D:\bluestock_mf_capstone\data\processed\fund_metrics.csv"
    if os.path.exists(metrics_path):
        return pd.read_csv(metrics_path)
    else:
        funds = load_funds()
        metrics = []
        for _, row in funds.iterrows():
            nav_df = load_nav(row['scheme_code'])
            if len(nav_df) > 5:
                returns = nav_df['nav'].pct_change().dropna()
                sharpe = returns.mean() / returns.std() * np.sqrt(252) if returns.std() != 0 else 0
                var_95 = returns.quantile(0.05)
                metrics.append({
                    'scheme_code': row['scheme_code'],
                    'scheme_name': row['scheme_name'],
                    'sharpe_ratio': sharpe,
                    'var_95': var_95,
                    'risk_grade': row['risk_grade']
                })
        return pd.DataFrame(metrics)

@st.cache_data(ttl=3600)
def load_investor_summary():
    conn = get_connection()
    try:
        df = pd.read_sql("""
            SELECT 
                investor_id,
                COUNT(*) as txns,
                MIN(transaction_date) as first_investment,
                AVG(amount) as avg_sip
            FROM fact_transactions
            WHERE transaction_type = 'SIP'
            GROUP BY investor_id
        """, conn, parse_dates=['first_investment'])
    except:
        df = pd.DataFrame()
    return df

# ------------------------------
# SIDEBAR FILTERS
# ------------------------------
st.sidebar.header("Filters")
funds_df = load_funds()
fund_names = funds_df['scheme_name'].tolist()
selected_fund_names = st.sidebar.multiselect("Select Funds to Compare", fund_names, default=fund_names[:3])
selected_funds = funds_df[funds_df['scheme_name'].isin(selected_fund_names)]

category_filter = st.sidebar.multiselect("Category", options=funds_df['category'].unique(), default=funds_df['category'].unique())
risk_filter = st.sidebar.multiselect("Risk Grade", options=funds_df['risk_grade'].unique(), default=funds_df['risk_grade'].unique())

filtered_funds = funds_df[(funds_df['category'].isin(category_filter)) & (funds_df['risk_grade'].isin(risk_filter))]

# ------------------------------
# TAB LAYOUT
# ------------------------------
tab1, tab2, tab3, tab4, tab5 = st.tabs(["📊 NAV Comparison", "📉 Risk Metrics", "⭐ Fund Recommender", "👥 Investor Insights", "🔮 Monte Carlo"])

# ----- TAB 1: NAV COMPARISON -----
with tab1:
    st.subheader("NAV Trends")
    fig = go.Figure()
    for _, fund in selected_funds.iterrows():
        nav_df = load_nav(fund['scheme_code'])
        if not nav_df.empty:
            fig.add_trace(go.Scatter(x=nav_df['date'], y=nav_df['nav'], mode='lines', name=fund['scheme_name']))
    fig.update_layout(height=500, xaxis_title="Date", yaxis_title="NAV (₹)")
    st.plotly_chart(fig, use_container_width=True)
    
    st.subheader("Recent Returns (Annualized)")
    returns_data = []
    for _, fund in selected_funds.iterrows():
        nav_df = load_nav(fund['scheme_code'])
        if len(nav_df) > 20:
            returns = nav_df['nav'].pct_change().dropna()
            ann_ret = returns.mean() * 252
            returns_data.append({"Fund": fund['scheme_name'], "Annualized Return": f"{ann_ret:.2%}"})
    st.dataframe(pd.DataFrame(returns_data))

# ----- TAB 2: RISK METRICS (FIXED MERGE) -----
with tab2:
    st.subheader("Risk vs. Return")
    metrics_df = load_metrics()
    # Merge and keep only one scheme_name column
    merged = filtered_funds.merge(metrics_df, on='scheme_code', suffixes=('', '_y'))
    # Drop duplicate scheme_name_y if exists
    if 'scheme_name_y' in merged.columns:
        merged = merged.drop(columns=['scheme_name_y'])
    # Ensure we have scheme_name
    if 'scheme_name' not in merged.columns and 'scheme_name_x' in merged.columns:
        merged = merged.rename(columns={'scheme_name_x': 'scheme_name'})
    
    # Now plot with correct column names
    fig = px.scatter(merged, x='var_95', y='sharpe_ratio', text='scheme_name', color='risk_grade',
                     title="Sharpe Ratio vs. VaR (95%)", 
                     labels={'var_95': "Value at Risk (95%)", 'sharpe_ratio': "Sharpe Ratio"})
    fig.update_traces(textposition='top center')
    st.plotly_chart(fig, use_container_width=True)
    
    st.subheader("Fund Metrics Table")
    st.dataframe(merged[['scheme_name', 'sharpe_ratio', 'var_95', 'risk_grade']].round(4))

# ----- TAB 3: FUND RECOMMENDER (FIXED) -----
with tab3:
    st.subheader("Simple Fund Recommender")
    risk_input = st.selectbox("Your Risk Appetite", ["Low", "Moderate", "High", "Very High"])
    metrics_df = load_metrics()
    funds_all = load_funds()
    merged_all = funds_all.merge(metrics_df, on='scheme_code', suffixes=('', '_y'))
    if 'scheme_name_y' in merged_all.columns:
        merged_all = merged_all.drop(columns=['scheme_name_y'])
    rec_df = merged_all[merged_all['risk_grade'] == risk_input].nlargest(3, 'sharpe_ratio')
    if rec_df.empty:
        st.warning("No funds found for this risk grade.")
    else:
        st.write(f"**Top 3 funds for {risk_input} risk appetite:**")
        st.dataframe(rec_df[['scheme_name', 'sharpe_ratio', 'var_95']])
        st.markdown("""
        **How it works:**  
        - The recommender filters funds by your selected risk grade.  
        - It then sorts by Sharpe ratio (higher is better risk-adjusted return).  
        - VaR (Value at Risk) shows the potential daily loss at 95% confidence.
        """)

# ----- TAB 4: INVESTOR INSIGHTS -----
with tab4:
    st.subheader("SIP Investor Continuity")
    inv_df = load_investor_summary()
    if not inv_df.empty:
        inv_df['cohort'] = inv_df['first_investment'].dt.year
        cohort_summary = inv_df.groupby('cohort').agg(
            investors=('investor_id', 'count'),
            avg_sip=('avg_sip', 'mean')
        ).reset_index()
        st.dataframe(cohort_summary)
        
        st.subheader("At-Risk SIP Investors")
        st.info("Investors with SIP gap >35 days are flagged 'at-risk'. In production, this would trigger reminders.")
        st.metric("Investors with 6+ SIPs", len(inv_df[inv_df['txns'] >= 6]))
    else:
        st.warning("Investor transaction data not available in database.")

# ----- TAB 5: MONTE CARLO -----
with tab5:
    st.subheader("Monte Carlo NAV Projection (5 Years)")
    funds_df = load_funds()
    fund_names = funds_df['scheme_name'].tolist()
    mc_fund_name = st.selectbox("Select a fund for simulation", fund_names, index=0)
    mc_fund = funds_df[funds_df['scheme_name'] == mc_fund_name].iloc[0]
    if st.button("Run Simulation"):
        with st.spinner("Running 10,000 simulations..."):
            try:
                TRADING_DAYS_PER_YEAR = 252
                YEARS = 5
                TOTAL_DAYS = YEARS * TRADING_DAYS_PER_YEAR
                N_SIMULATIONS = 10000
                
                nav_df = load_nav(mc_fund['scheme_code'])
                if len(nav_df) < 10:
                    st.error("Not enough NAV data for this fund.")
                else:
                    nav_df['log_return'] = np.log(nav_df['nav'] / nav_df['nav'].shift(1))
                    df_clean = nav_df.dropna()
                    daily_mu = df_clean['log_return'].mean()
                    daily_sigma = df_clean['log_return'].std()
                    mu = daily_mu * TRADING_DAYS_PER_YEAR
                    sigma = daily_sigma * np.sqrt(TRADING_DAYS_PER_YEAR)
                    start_nav = nav_df['nav'].iloc[-1]
                    
                    dt = 1 / TRADING_DAYS_PER_YEAR
                    daily_mu_sim = mu * dt
                    daily_sigma_sim = sigma * np.sqrt(dt)
                    paths = np.zeros((N_SIMULATIONS, TOTAL_DAYS + 1))
                    for i in range(N_SIMULATIONS):
                        shocks = np.random.normal(0, 1, TOTAL_DAYS)
                        log_returns = (daily_mu_sim - 0.5 * daily_sigma_sim**2) + daily_sigma_sim * shocks
                        log_price = np.log(start_nav) + np.cumsum(log_returns)
                        price = np.exp(log_price)
                        paths[i] = np.insert(price, 0, start_nav)
                    
                    median = np.percentile(paths, 50, axis=0)
                    lower = np.percentile(paths, 2.5, axis=0)
                    upper = np.percentile(paths, 97.5, axis=0)
                    
                    last_date = nav_df['date'].iloc[-1]
                    future_dates = [last_date + timedelta(days=i) for i in range(TOTAL_DAYS+1)]
                    
                    fig = go.Figure()
                    fig.add_trace(go.Scatter(x=nav_df['date'], y=nav_df['nav'], mode='lines', name='Historical', line=dict(color='blue')))
                    fig.add_trace(go.Scatter(x=future_dates, y=median, mode='lines', name='Median Projection', line=dict(color='green', dash='dash')))
                    fig.add_trace(go.Scatter(x=future_dates, y=upper, fill=None, mode='lines', line=dict(width=0), showlegend=False))
                    fig.add_trace(go.Scatter(x=future_dates, y=lower, fill='tonexty', mode='lines', name='95% Confidence Band', line=dict(width=0), fillcolor='rgba(128,128,128,0.3)'))
                    fig.update_layout(title=f"{mc_fund_name} – 5-Year NAV Projection", xaxis_title="Date", yaxis_title="NAV (₹)")
                    st.plotly_chart(fig, use_container_width=True)
                    
                    col1, col2, col3 = st.columns(3)
                    col1.metric("Median Final NAV", f"₹{median[-1]:.2f}")
                    col2.metric("Lower Band (2.5%)", f"₹{lower[-1]:.2f}")
                    col3.metric("Upper Band (97.5%)", f"₹{upper[-1]:.2f}")
            except Exception as e:
                st.error(f"Error in simulation: {e}")
    else:
        st.info("Click 'Run Simulation' to generate a 5-year projection with uncertainty bands.")

# ------------------------------
# FOOTER
# ------------------------------
st.markdown("---")
st.caption("Bluestock Fintech Capstone Project – Built with Streamlit")