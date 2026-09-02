import os
import sys
import argparse
import time

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config.db_config import get_connection
from etl.transformers import transform_monthly_pivoted
from etl.loaders import load_fact_exchange_rates, log_ingestion, calculate_file_hash

def ingest_monthly_file(file_path: str):
    """
    Ingests a single monthly update CSV file into fact_daily_exchange_rate.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Monthly CSV file not found: {file_path}")

    print(f"[MONTHLY PIPELINE] Processing file: {file_path}")
    t0 = time.time()

    # Transform
    df = transform_monthly_pivoted(file_path)
    print(f"[MONTHLY PIPELINE] Transformed {len(df):,} records in {time.time() - t0:.2f}s.")

    # Validate foreign keys
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT currency_code FROM dim_currency;")
        valid_currencies = {row[0] for row in cursor.fetchall()}
        file_currencies = set(df["currency_code"].unique())
        unknown = file_currencies - valid_currencies
        if unknown:
            print(f"[WARNING] Unknown currencies found in file: {unknown}. Please add them to dim_currency first.")
            df = df[df["currency_code"].isin(valid_currencies)]

        # Load
        rows_loaded = load_fact_exchange_rates(df, chunk_size=5000, conn=conn)
        
        # Log Ingestion
        min_date = str(df["rate_date"].min()) if not df.empty else None
        max_date = str(df["rate_date"].max()) if not df.empty else None
        file_hash = calculate_file_hash(file_path)
        duration = round(time.time() - t0, 2)
        
        log_ingestion(
            dataset_name="monthly_batch",
            file_or_source=os.path.basename(file_path),
            period_start=min_date,
            period_end=max_date,
            total_rows=rows_loaded,
            file_hash=file_hash,
            status="SUCCESS",
            duration_seconds=duration,
            conn=conn
        )
        print(f"[MONTHLY PIPELINE] Ingestion completed & logged: {rows_loaded:,} records processed.")
        return rows_loaded
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest monthly Bank of Thailand exchange rate CSV file.")
    parser.add_argument("--file", "-f", required=True, help="Path to monthly CSV file")
    args = parser.parse_args()

    ingest_monthly_file(args.file)
