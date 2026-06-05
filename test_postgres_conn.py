from sqlalchemy import create_engine

DB_NAME = "bluestock_mf"
DB_USER = "postgres"
DB_PASSWORD = "8128128208"   # change this
DB_HOST = "localhost"
DB_PORT = "5432"

engine = create_engine(f'postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}')

# Test connection
with engine.connect() as conn:
    result = conn.execute("SELECT 1")
    print("Connection successful:", result.fetchone())