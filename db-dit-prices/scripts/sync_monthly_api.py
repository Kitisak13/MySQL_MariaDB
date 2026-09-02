import os
import sys
import time
import argparse
from datetime import datetime, date, timedelta
import calendar
import pandas as pd

# Ensure UTF-8 output
sys.stdout.reconfigure(encoding="utf-8")

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config.db_config import get_connection
from scripts.fetch_dit_api import DITPriceDownloader
from etl.transformers import transform_dim_products, transform_fact_prices_chunk
from etl.loaders import upsert_dim_products, upsert_fact_prices, log_ingestion

def get_default_monthly_dates() -> tuple:
    """
    Returns (first_day_of_current_month, last_day_of_current_month) as (YYYY-MM-DD, YYYY-MM-DD).
    """
    today = date.today()
    first_day = today.replace(day=1)
    _, last_day_num = calendar.monthrange(today.year, today.month)
    last_day = today.replace(day=last_day_num)
    return first_day.strftime("%Y-%m-%d"), last_day.strftime("%Y-%m-%d")

def sync_monthly_prices(
    from_date: str,
    to_date: str,
    save_raw_csv: bool = True,
    max_workers: int = 3
):
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    master_product_path = os.path.join(base_dir, "master_data", "tbl_product&unit.csv")
    raw_dir = os.path.join(base_dir, "raw_data")
    os.makedirs(raw_dir, exist_ok=True)

    start_time = time.time()
    print("=" * 80)
    print("DIT PRODUCT PRICES - MONTHLY API SYNC PIPELINE (AIRFLOW-READY)")
    print(f"Target Date Range: {from_date} to {to_date}")
    print("=" * 80)

    # Step 1: Read Product Catalog
    conn = get_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT product_id FROM `dim_product` ORDER BY product_id;")
        db_products = [r["product_id"] for r in cursor.fetchall()]
        cursor.close()

        if db_products:
            product_ids = db_products
            print(f"\n[Step 1/3] Loaded {len(product_ids)} target products from `dim_product`.")
        elif os.path.exists(master_product_path):
            df_prods = pd.read_csv(master_product_path, encoding="utf-8")
            product_ids = df_prods["product_id"].dropna().unique().tolist()
            print(f"\n[Step 1/3] Loaded {len(product_ids)} target products from {master_product_path}.")
        else:
            downloader_temp = DITPriceDownloader(max_workers=max_workers)
            df_prods = downloader_temp.get_product_list()
            product_ids = df_prods["product_id"].dropna().unique().tolist()
            print(f"\n[Step 1/3] Loaded {len(product_ids)} target products dynamically from DIT API.")

        # Step 2: Fetch Prices from API
        print(f"\n[Step 2/3] Calling DIT API (3 parallel workers with auto-backoff)...")
        downloader = DITPriceDownloader(max_workers=max_workers, retry_count=5, rate_limit_delay=0.1)
        df_prices, df_errors = downloader.fetch_all_prices(
            product_ids=product_ids,
            from_date=from_date,
            to_date=to_date,
            max_passes=3
        )

        if df_prices.empty:
            print("\n[Warning] No price data returned from DIT API for this period.")
            return

        print(f"  -> Retrieved {len(df_prices):,} total price observations.")

        # Optionally save raw CSV
        if save_raw_csv:
            csv_name = f"dit_price_monthly_{from_date[:7].replace('-', '_')}.csv"
            raw_csv_path = os.path.join(raw_dir, csv_name)
            df_prices.to_csv(raw_csv_path, index=False, encoding="utf-8")
            print(f"  -> Raw CSV snapshot saved to: {raw_csv_path}")

        # Step 3: Transform & Bulk Upsert into MySQL
        print("\n[Step 3/3] Transforming and Upserting into `fact_daily_product_price`...")
        fact_records = transform_fact_prices_chunk(df_prices)
        total_upserted = upsert_fact_prices(conn, fact_records, chunk_size=10000)
        print(f"  -> Successfully upserted {total_upserted:,} records into database.")

        duration = round(time.time() - start_time, 2)

        # Audit Log
        log_ingestion(
            conn=conn,
            dataset_name="monthly_api_sync",
            file_or_source=f"DIT_API_{from_date}_to_{to_date}",
            period_start=from_date,
            period_end=to_date,
            total_rows=total_upserted,
            file_hash=None,
            status="SUCCESS",
            duration_seconds=duration
        )

        print("\n" + "=" * 80)
        print("MONTHLY SYNC COMPLETED SUCCESSFULLY!")
        print(f"Total Rows Ingested: {total_upserted:,}")
        print(f"Duration           : {duration:.2f} seconds ({duration/60:.2f} mins)")
        if not df_errors.empty:
            print(f"Errors             : {len(df_errors)} failed requests (see log)")
        print("=" * 80)

    finally:
        conn.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DIT Product Prices Monthly Sync Pipeline")
    parser.add_argument("--from-date", type=str, default=None, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--to-date", type=str, default=None, help="End date (YYYY-MM-DD)")
    parser.add_argument("--month", type=str, default=None, help="Month to sync (YYYY-MM)")
    parser.add_argument("--workers", type=int, default=3, help="Number of concurrent workers (default: 3)")
    args = parser.parse_args()

    if args.month:
        year, month = map(int, args.month.split("-"))
        f_date = f"{year:04d}-{month:02d}-01"
        _, last_day = calendar.monthrange(year, month)
        t_date = f"{year:04d}-{month:02d}-{last_day:02d}"
    elif args.from_date and args.to_date:
        f_date = args.from_date
        t_date = args.to_date
    else:
        f_date, t_date = get_default_monthly_dates()

    sync_monthly_prices(from_date=f_date, to_date=t_date, max_workers=args.workers)
