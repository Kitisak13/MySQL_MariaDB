import os
import sys
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from config.db_config import get_connection

def main():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT 
            export_year, 
            export_month, 
            COUNT(*) as rows_count,
            COUNT(DISTINCT hs_11_code) as hs_count,
            COUNT(DISTINCT country_code) as country_count
        FROM fact_food_export
        GROUP BY export_year, export_month
        ORDER BY export_year, export_month;
    """)
    df = pd.DataFrame(cursor.fetchall())
    print("=" * 80)
    print("FACT_FOOD_EXPORT MONTHLY INGESTION BREAKDOWN")
    print("=" * 80)
    if not df.empty:
        print(df.to_string(index=False))
    else:
        print("No facts found.")

    cursor.execute("SELECT COUNT(*) as total_facts FROM fact_food_export;")
    total = cursor.fetchone()["total_facts"]
    print("\n" + "=" * 80)
    print(f"Total Facts Ingested into MariaDB: {total:,}")
    print("=" * 80)

    failed_file = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "master_data", "failed_queries_food_export.csv"))
    if os.path.exists(failed_file):
        df_failed = pd.read_csv(failed_file)
        print(f"\nTotal Failed Queries in CSV: {len(df_failed):,}")
        print("\nTop Error Reasons:")
        print(df_failed["error_msg"].value_counts().head(10).to_string())
        print("\nFailed Queries Count by Year-Month:")
        print(df_failed.groupby(["year", "month"]).size().to_string())
    else:
        print("\nNo failed queries recorded in CSV!")

    cursor.close()
    conn.close()

if __name__ == "__main__":
    main()
