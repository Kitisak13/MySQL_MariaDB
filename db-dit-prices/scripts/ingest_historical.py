import os
import sys
import time
from datetime import datetime
import pandas as pd

# Ensure UTF-8 output
sys.stdout.reconfigure(encoding="utf-8")

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config.db_config import get_connection
from database.init_db import init_database
from etl.transformers import transform_dim_products, transform_fact_prices_chunk
from etl.loaders import (
    upsert_dim_products,
    upsert_fact_prices,
    calculate_file_hash,
    log_ingestion
)

# Attempt to import tqdm
try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False

def ingest_historical_data():
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    master_product_path = os.path.join(base_dir, "master_data", "tbl_product&unit.csv")
    historical_csv_path = os.path.join(base_dir, "raw_data", "dit_price_database.csv")

    if not os.path.exists(historical_csv_path):
        # Check parent folder if not in raw_data
        historical_csv_path = os.path.join(base_dir, "dit_price_database.csv")
    if not os.path.exists(historical_csv_path):
        raise FileNotFoundError(f"Historical CSV file not found: {historical_csv_path}")

    start_time = time.time()
    print("=" * 80)
    print("DIT PRODUCT PRICES - HISTORICAL DATA INGESTION PIPELINE")
    print("=" * 80)

    # Step 1: Ensure Schema Initialized
    print("\n[Step 1/3] Ensuring Database Schema and Tables exist...")
    init_database()

    conn = get_connection()

    try:
        # Step 2: Load Dimension Products
        print(f"\n[Step 2/3] Loading Dimension Products from: {master_product_path}")
        if os.path.exists(master_product_path):
            df_products = pd.read_csv(master_product_path, encoding="utf-8")
            prod_records = transform_dim_products(df_products)
            loaded_prods = upsert_dim_products(conn, prod_records)
            print(f"  -> Successfully loaded/updated {loaded_prods} products in `dim_product`.")
        else:
            print("  -> Warning: Master product CSV not found. Will extract products from fact data.")

        # Step 3: Stream & Ingest Historical Fact Prices
        print(f"\n[Step 3/3] Streaming Historical Prices from: {historical_csv_path}")
        file_hash = calculate_file_hash(historical_csv_path)
        print(f"  -> File Checksum (SHA-256): {file_hash}")

        chunk_size = 50000
        total_rows_ingested = 0
        min_date = None
        max_date = None

        # Determine total lines for progress bar if possible
        print("  -> Reading and ingesting in streaming chunks (50,000 rows/chunk)...")
        chunk_iter = pd.read_csv(
            historical_csv_path,
            chunksize=chunk_size,
            encoding="utf-8",
            dtype={"product_id": str, "date": str}
        )

        chunk_idx = 0
        for chunk_df in chunk_iter:
            chunk_idx += 1
            # Backfill any missing products into dim_product
            if "product_name" in chunk_df.columns:
                extra_prods = transform_dim_products(chunk_df)
                if extra_prods:
                    upsert_dim_products(conn, extra_prods)

            # Transform Fact Records
            fact_records = transform_fact_prices_chunk(chunk_df)
            if fact_records:
                # Track min/max dates
                dates = [r[0] for r in fact_records if r[0]]
                if dates:
                    chunk_min = min(dates)
                    chunk_max = max(dates)
                    min_date = chunk_min if min_date is None else min(min_date, chunk_min)
                    max_date = chunk_max if max_date is None else max(max_date, chunk_max)

                loaded = upsert_fact_prices(conn, fact_records, chunk_size=10000)
                total_rows_ingested += loaded
                print(f"  -> Processed Chunk #{chunk_idx}: {loaded:,} rows (Cumulative: {total_rows_ingested:,} rows)")

        duration = round(time.time() - start_time, 2)

        # Record Ingestion Audit Log
        log_ingestion(
            conn=conn,
            dataset_name="dit_price_database",
            file_or_source=os.path.basename(historical_csv_path),
            period_start=min_date,
            period_end=max_date,
            total_rows=total_rows_ingested,
            file_hash=file_hash,
            status="SUCCESS",
            duration_seconds=duration
        )

        print("\n" + "=" * 80)
        print("HISTORICAL INGESTION COMPLETED SUCCESSFULLY!")
        print(f"Total Rows Ingested: {total_rows_ingested:,}")
        print(f"Date Range         : {min_date} to {max_date}")
        print(f"Total Time Taken   : {duration:.2f} seconds ({duration/60:.2f} mins)")
        print("=" * 80)

    finally:
        conn.close()

if __name__ == "__main__":
    ingest_historical_data()
