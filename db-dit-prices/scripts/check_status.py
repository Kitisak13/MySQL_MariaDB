import os
import sys
import mysql.connector
import pandas as pd

# Ensure UTF-8 output
sys.stdout.reconfigure(encoding="utf-8")

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config.db_config import get_connection

def check_live_status():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        print("=" * 80)
        print("DIT PRODUCT PRICES - LIVE DATABASE STATUS")
        print("=" * 80)

        # 1. Total Counts
        cursor.execute("SELECT COUNT(*) AS total FROM `dim_product`;")
        prod_count = cursor.fetchone()["total"]

        cursor.execute("SELECT COUNT(*) AS total, MIN(price_date) AS min_d, MAX(price_date) AS max_d FROM `fact_daily_product_price`;")
        fact_info = cursor.fetchone()
        fact_count = fact_info["total"]
        min_date = fact_info["min_d"]
        max_date = fact_info["max_d"]

        print(f"\n1. Dimension Table (dim_product)           : {prod_count:,} products")
        print(f"2. Fact Table (fact_daily_product_price) : {fact_count:,} price records")
        print(f"3. Active Observation Date Range         : {min_date} to {max_date}")

        # 2. Product Groups Summary
        print("\n4. Product Count by Category & Group:")
        cursor.execute("""
            SELECT 
                COALESCE(category_name, 'Other') AS category,
                COALESCE(group_name, 'Other') AS `group`,
                COUNT(*) AS total_products
            FROM `dim_product`
            GROUP BY category_name, group_name
            ORDER BY total_products DESC
            LIMIT 10;
        """)
        groups_df = pd.DataFrame(cursor.fetchall())
        if not groups_df.empty:
            print(groups_df.to_string(index=False))

        # 3. Recent Ingestion Logs
        print("\n5. Recent Ingestion Logs (data_ingestion_log):")
        cursor.execute("""
            SELECT id, dataset_name, file_or_source, period_start, period_end, total_rows, status, duration_seconds, ingested_at
            FROM `data_ingestion_log`
            ORDER BY id DESC
            LIMIT 5;
        """)
        logs_df = pd.DataFrame(cursor.fetchall())
        if not logs_df.empty:
            print(logs_df.to_string(index=False))
        else:
            print("  (No logs recorded yet)")

        print("\n" + "=" * 80)

    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    check_live_status()
