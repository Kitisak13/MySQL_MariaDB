import os
import sys
import mysql.connector
import pandas as pd

# Ensure UTF-8 output
sys.stdout.reconfigure(encoding="utf-8")

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config.db_config import get_connection

def verify_database():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        print("=" * 80)
        print("DATABASE DATA QUALITY & INTEGRITY VERIFICATION REPORT")
        print("Target Database: dit_product_prices")
        print("=" * 80)

        # 1. Total Metrics
        cursor.execute("SELECT COUNT(*) AS total FROM `dim_product`;")
        prod_count = cursor.fetchone()["total"]

        cursor.execute("""
            SELECT 
                COUNT(*) AS total_records,
                COUNT(DISTINCT price_date) AS total_dates,
                COUNT(DISTINCT product_id) AS active_products,
                MIN(price_date) AS earliest_date,
                MAX(price_date) AS latest_date
            FROM `fact_daily_product_price`;
        """)
        fact_summary = cursor.fetchone()

        print(f"\n1. Dimension Table (dim_product)          : {prod_count:,} products")
        print(f"2. Fact Table (fact_daily_product_price): {fact_summary['total_records']:,} price records")
        print(f"3. Total Distinct Dates                 : {fact_summary['total_dates']:,} days")
        print(f"4. Date Coverage Range                  : {fact_summary['earliest_date']} to {fact_summary['latest_date']}")
        print(f"5. Products with Price Observations     : {fact_summary['active_products']:,} products")

        # 2. Relational Integrity (Orphan check)
        cursor.execute("""
            SELECT COUNT(*) AS orphan_count
            FROM `fact_daily_product_price` f
            LEFT JOIN `dim_product` d ON f.product_id = d.product_id
            WHERE d.product_id IS NULL;
        """)
        orphan_count = cursor.fetchone()["orphan_count"]
        print(f"\n6. Referential Integrity (Unmatched Foreign Keys): {orphan_count} (Expected: 0)")

        # 3. Data Sanity Check (price_min > price_max anomaly)
        cursor.execute("""
            SELECT COUNT(*) AS anomaly_count
            FROM `fact_daily_product_price`
            WHERE price_min IS NOT NULL AND price_max IS NOT NULL AND price_min > price_max;
        """)
        anomaly_count = cursor.fetchone()["anomaly_count"]
        print(f"7. Price Logic Sanity Check (price_min > price_max): {anomaly_count} (Expected: 0)")

        # 4. Spot Check Across Sample Commodities (e.g. Pork, Chicken, Egg, Jasmine Rice)
        print("\n8. Spot Check Across Key Economic Commodities (Latest 5 Observations):")
        cursor.execute("""
            SELECT 
                f.price_date,
                f.product_id,
                d.product_name,
                d.category_name,
                d.group_name,
                d.unit,
                f.price_min,
                f.price_max,
                f.price_avg
            FROM `fact_daily_product_price` f
            JOIN `dim_product` d ON f.product_id = d.product_id
            WHERE f.product_id IN ('P11001', 'P11009', 'P11020', 'P11025', 'P12001')
            ORDER BY f.price_date DESC, f.product_id ASC
            LIMIT 10;
        """)
        spot_check_df = pd.DataFrame(cursor.fetchall())
        if not spot_check_df.empty:
            print(spot_check_df.to_string(index=False))

        print("\n" + "=" * 80)
        if orphan_count == 0 and anomaly_count == 0:
            print("VERIFICATION COMPLETED: ALL DATA INTEGRITY CHECKS PASSED (100% OK)!")
        else:
            print("VERIFICATION WARNING: Some integrity anomalies detected.")
        print("=" * 80)

    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    verify_database()
