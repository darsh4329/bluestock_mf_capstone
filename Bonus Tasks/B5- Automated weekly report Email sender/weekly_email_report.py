#!/usr/bin/env python3
"""
Weekly Performance Email Report Generator
Generates HTML summary and sends via SMTP.
"""

import sqlite3
import pandas as pd
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
import os

# ------------------------------
# CONFIGURATION (Update these)
# ------------------------------
SMTP_SERVER = "smtp.gmail.com"      # or your company SMTP
SMTP_PORT = 587
SENDER_EMAIL = "your_email@bluestock.com"
SENDER_PASSWORD = os.getenv("EMAIL_PASSWORD")  # Use env variable for security
RECIPIENT_EMAILS = ["team@bluestock.com", "manager@bluestock.com"]  # list

DB_PATH = "D:\bluestock_mf_capstone\data\db\bluestock_mf.db"  #change location

def fetch_weekly_data():
    """Query key metrics for the past week."""
    conn = sqlite3.connect(DB_PATH)
    
    # Last 7 days date range
    end_date = datetime.now()
    start_date = end_date - timedelta(days=7)
    
    # 1. Top 5 funds by weekly return
    weekly_returns = pd.read_sql(f"""
        SELECT scheme_name, weekly_return
        FROM (
            SELECT s.scheme_name, 
                   (last_nav / first_nav - 1) * 100 AS weekly_return
            FROM (
                SELECT scheme_code,
                       MAX(CASE WHEN date = '{end_date.strftime('%Y-%m-%d')}' THEN nav END) AS last_nav,
                       MAX(CASE WHEN date = '{start_date.strftime('%Y-%m-%d')}' THEN nav END) AS first_nav
                FROM nav_history
                WHERE date >= '{start_date.strftime('%Y-%m-%d')}'
                GROUP BY scheme_code
            ) AS weekly
            JOIN scheme_metadata s ON weekly.scheme_code = s.scheme_code
        )
        ORDER BY weekly_return DESC
        LIMIT 5
    """, conn)
    
    # 2. Bottom 5 funds by weekly return
    bottom_returns = pd.read_sql(f"""
        SELECT scheme_name, weekly_return
        FROM (
            SELECT s.scheme_name, 
                   (last_nav / first_nav - 1) * 100 AS weekly_return
            FROM (
                SELECT scheme_code,
                       MAX(CASE WHEN date = '{end_date.strftime('%Y-%m-%d')}' THEN nav END) AS last_nav,
                       MAX(CASE WHEN date = '{start_date.strftime('%Y-%m-%d')}' THEN nav END) AS first_nav
                FROM nav_history
                WHERE date >= '{start_date.strftime('%Y-%m-%d')}'
                GROUP BY scheme_code
            ) AS weekly
            JOIN scheme_metadata s ON weekly.scheme_code = s.scheme_code
        )
        ORDER BY weekly_return ASC
        LIMIT 5
    """, conn)
    
    # 3. New at-risk SIP investors (gap > 35 days in last week)
    at_risk = pd.read_sql("""
        SELECT investor_id, MAX(gap_days) AS max_gap
        FROM (
            SELECT investor_id, 
                   julianday(transaction_date) - julianday(LAG(transaction_date) 
                   OVER (PARTITION BY investor_id ORDER BY transaction_date)) AS gap_days
            FROM transactions
            WHERE transaction_type = 'SIP'
        )
        WHERE gap_days > 35
        GROUP BY investor_id
    """, conn)
    
    # 4. Current top 3 funds by Sharpe (all-time)
    top_sharpe = pd.read_sql("""
        SELECT scheme_name, sharpe_ratio
        FROM fund_metrics
        ORDER BY sharpe_ratio DESC
        LIMIT 3
    """, conn)
    
    conn.close()
    
    return {
        "top_weekly": weekly_returns,
        "bottom_weekly": bottom_returns,
        "at_risk_count": len(at_risk),
        "top_sharpe": top_sharpe,
        "week_start": start_date.strftime("%d %b %Y"),
        "week_end": end_date.strftime("%d %b %Y")
    }

def generate_html_report(data):
    """Create beautiful HTML email body."""
    html = f"""
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; }}
            .header {{ background-color: #1e3a8a; color: white; padding: 20px; text-align: center; }}
            .section {{ margin: 20px; padding: 15px; border: 1px solid #ddd; border-radius: 5px; }}
            .positive {{ color: green; font-weight: bold; }}
            .negative {{ color: red; font-weight: bold; }}
            table {{ width: 100%; border-collapse: collapse; }}
            th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
            th {{ background-color: #f2f2f2; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>📈 Bluestock MF Weekly Performance Summary</h1>
            <p>Week: {data['week_start']} – {data['week_end']}</p>
        </div>
        
        <div class="section">
            <h2>🏆 Top 5 Performing Funds (Weekly Return)</h2>
            {data['top_weekly'].to_html(index=False, classes='table', escape=False)}
        </div>
        
        <div class="section">
            <h2>⚠️ Bottom 5 Funds (Weekly Return)</h2>
            {data['bottom_weekly'].to_html(index=False, classes='table', escape=False)}
        </div>
        
        <div class="section">
            <h2>🚨 SIP Investor Alerts</h2>
            <p><strong>{data['at_risk_count']}</strong> investors flagged as "at-risk" (SIP gap > 35 days).</p>
            <p><em>Action: Send reminder notifications.</em></p>
        </div>
        
        <div class="section">
            <h2>⭐ All-Time Top Sharpe Ratio Funds (Recommend)</h2>
            {data['top_sharpe'].to_html(index=False, classes='table', escape=False)}
        </div>
        
        <div class="section">
            <p style="font-size: small; color: gray;">Generated automatically by Bluestock Capstone Pipeline. For queries, contact data team.</p>
        </div>
    </body>
    </html>
    """
    return html

def send_email(html_content):
    """Send email via SMTP."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Weekly MF Report – {datetime.now().strftime('%Y-%m-%d')}"
    msg["From"] = SENDER_EMAIL
    msg["To"] = ", ".join(RECIPIENT_EMAILS)
    
    part = MIMEText(html_content, "html")
    msg.attach(part)
    
    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.sendmail(SENDER_EMAIL, RECIPIENT_EMAILS, msg.as_string())
    
    print("Email sent successfully.")

if __name__ == "__main__":
    print("Fetching weekly data...")
    data = fetch_weekly_data()
    print("Generating HTML...")
    html = generate_html_report(data)
    print("Sending email...")
    send_email(html)
    print("Done.")