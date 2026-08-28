import os
import sys
import pandas as pd

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config.db_config import get_connection

def verify():
    # Set stdout encoding
    sys.stdout.reconfigure(encoding="utf-8")

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    print("=" * 80)
    print("DATABASE DATA QUALITY & INTEGRITY VERIFICATION REPORT")
    print("=" * 80)

    try:
        # 1. Dimension Check
        cursor.execute("SELECT COUNT(*) AS total_dim FROM dim_currency;")
        total_dim = cursor.fetchone()["total_dim"]
        print(f"\n1. Dimension Table (dim_currency): {total_dim} unique currencies")

        # 2. Fact Count Check
        cursor.execute("SELECT COUNT(*) AS total_fact FROM fact_daily_exchange_rate;")
        total_fact = cursor.fetchone()["total_fact"]
        print(f"2. Fact Table (fact_daily_exchange_rate): {total_fact:,} total records")

        # 3. Date Range Check
        cursor.execute("""
            SELECT 
                MIN(rate_date) AS min_date,
                MAX(rate_date) AS max_date,
                COUNT(DISTINCT rate_date) AS distinct_dates
            FROM fact_daily_exchange_rate;
        """)
        date_stats = cursor.fetchone()
        print(f"3. Date Range: From {date_stats['min_date']} to {date_stats['max_date']} ({date_stats['distinct_dates']:,} trading days)")

        # 4. Spot Check Across Currencies (Major & Minor)
        print("\n4. Spot Check Across Sample Currencies:")
        cursor.execute("""
            SELECT 
                d.currency_code,
                d.country_name,
                d.currency_name,
                d.unit_multiplier,
                COUNT(f.id) AS total_records,
                MIN(f.rate_date) AS first_date,
                MAX(f.rate_date) AS last_date,
                AVG(f.buying_transfer) AS avg_transfer_rate,
                AVG(f.selling) AS avg_selling_rate
            FROM dim_currency d
            LEFT JOIN fact_daily_exchange_rate f ON d.currency_code = f.currency_code
            WHERE d.currency_code IN ('USD', 'EUR', 'JPY', 'GBP', 'AED', 'PKR', 'KRW')
            GROUP BY d.currency_code, d.country_name, d.currency_name, d.unit_multiplier
            ORDER BY d.currency_code;
        """)
        spots = cursor.fetchall()
        df_spots = pd.DataFrame(spots)
        print(df_spots.to_string(index=False))

        # 5. Latest 5 Records Sample
        print("\n5. Latest Ingested Exchange Rates Sample (Top 5):")
        cursor.execute("""
            SELECT 
                f.rate_date,
                f.currency_code,
                d.country_name,
                d.currency_name,
                f.buying_sight_bill,
                f.buying_transfer,
                f.selling
            FROM fact_daily_exchange_rate f
            JOIN dim_currency d ON f.currency_code = d.currency_code
            ORDER BY f.rate_date DESC, f.currency_code ASC
            LIMIT 5;
        """)
        latest = cursor.fetchall()
        df_latest = pd.DataFrame(latest)
        print(df_latest.to_string(index=False))

        # 6. Null rate check
        cursor.execute("""
            SELECT 
                COUNT(*) AS all_null_count
            FROM fact_daily_exchange_rate
            WHERE buying_sight_bill IS NULL 
              AND buying_transfer IS NULL 
              AND selling IS NULL;
        """)
        all_null = cursor.fetchone()["all_null_count"]
        print(f"\n6. Data Sanity Check: Rows where ALL rates are NULL = {all_null} (Expected: 0)")

        print("\n" + "=" * 80)
        print("VERIFICATION COMPLETED SUCCESSFULLY!")
        print("=" * 80)

    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    verify()
