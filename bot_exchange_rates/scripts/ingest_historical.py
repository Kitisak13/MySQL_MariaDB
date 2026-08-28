import os
import sys
import time

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config.db_config import get_connection
from etl.transformers import (
    extract_currency_dimension,
    transform_historical_unpivoted,
    transform_monthly_pivoted
)
from etl.loaders import load_dim_currency, load_fact_exchange_rates

def main():
    t_start = time.time()
    print("=" * 70)
    print("BOT FOREIGN EXCHANGE RATE - HISTORICAL INGESTION PIPELINE")
    print("=" * 70)

    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    path1 = os.path.join(base_dir, "BOT_csv_raw_data", "BOT Exchange Rate 02-24 Raw(Exchange Rate 02-24).csv")
    path2 = os.path.join(base_dir, "BOT_csv_raw_data", "EX_BOT_EX_Raw.csv")

    if not os.path.exists(path1):
        raise FileNotFoundError(f"File 1 not found: {path1}")
    if not os.path.exists(path2):
        raise FileNotFoundError(f"File 2 not found: {path2}")

    conn = get_connection()

    try:
        # Step 1: Ingest Dimension Table (dim_currency)
        print("\n[STEP 1/3] Extracting and loading Currency Dimension (dim_currency)...")
        dim_df = extract_currency_dimension(path1)
        load_dim_currency(dim_df, conn=conn)

        # Step 2: Transform & Ingest File 1 (2002 - 2024 Oct)
        print("\n[STEP 2/3] Processing Historical File 1 (2002 - 2024 Oct)...")
        t0 = time.time()
        fact1_df = transform_historical_unpivoted(path1)
        print(f"-> File 1 transformed into {len(fact1_df):,} daily records in {time.time() - t0:.2f}s.")
        load_fact_exchange_rates(fact1_df, chunk_size=15000, conn=conn)

        # Step 3: Transform & Ingest File 2 (2024 Nov - 2026 Jul)
        print("\n[STEP 3/3] Processing Recent File 2 (2024 Nov - 2026 Jul)...")
        t0 = time.time()
        fact2_df = transform_monthly_pivoted(path2)
        print(f"-> File 2 transformed into {len(fact2_df):,} daily records in {time.time() - t0:.2f}s.")
        load_fact_exchange_rates(fact2_df, chunk_size=15000, conn=conn)

        total_time = time.time() - t_start
        print("\n" + "=" * 70)
        print(f"HISTORICAL INGESTION COMPLETED SUCCESSFULLY in {total_time:.2f} seconds!")
        print("=" * 70)

    except Exception as e:
        print(f"\n[FATAL ERROR] Ingestion failed: {e}")
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    main()
