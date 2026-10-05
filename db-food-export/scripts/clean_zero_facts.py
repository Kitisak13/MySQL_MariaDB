import os
import sys
import time
import pandas as pd

# Unbuffered UTF-8 output
sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config.db_config import get_connection

def main():
    start_time = time.time()
    print("=" * 80, flush=True)
    print("CLEANING ZERO/MISSING TRADE RECORDS FROM fact_food_export", flush=True)
    print("=" * 80, flush=True)

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    # 1. Check rows before cleanup
    cursor.execute("SELECT COUNT(*) as total_before FROM fact_food_export;")
    total_before = cursor.fetchone()["total_before"]

    cursor.execute("""
        SELECT COUNT(*) as zero_count 
        FROM fact_food_export 
        WHERE (quantity = 0 AND value_usd = 0 AND value_thb = 0)
           OR (quantity IS NULL AND value_usd IS NULL AND value_thb IS NULL);
    """)
    zero_count = cursor.fetchone()["zero_count"]
    print(f"Total Fact Rows before cleanup: {total_before:,}", flush=True)
    print(f"Zero/Empty Trade Rows to delete: {zero_count:,}", flush=True)

    # 2. Execute deletion
    print("\nExecuting DELETE of zero/empty trade records...", flush=True)
    delete_sql = """
        DELETE FROM fact_food_export 
        WHERE (quantity = 0 AND value_usd = 0 AND value_thb = 0)
           OR (quantity IS NULL AND value_usd IS NULL AND value_thb IS NULL);
    """
    cursor.execute(delete_sql)
    conn.commit()
    deleted_rows = cursor.rowcount
    print(f"  ✅ Successfully deleted {deleted_rows:,} zero/empty trade records.", flush=True)

    # 3. Optimize table
    print("\nOptimizing fact_food_export table storage...", flush=True)
    cursor.execute("OPTIMIZE TABLE fact_food_export;")
    cursor.fetchall()
    print("  ✅ Table optimization completed.", flush=True)

    # 4. Ingestion Log Audit
    duration = round(time.time() - start_time, 2)
    log_sql = """
        INSERT INTO data_ingestion_log (
            dataset_name, file_or_source, period_start, period_end,
            total_rows, status, duration_seconds
        ) VALUES (%s, %s, %s, %s, %s, %s, %s);
    """
    cursor.execute(log_sql, (
        "clean_zero_facts_2016_2017",
        "fact_food_export",
        "2016-01-01",
        "2017-12-31",
        deleted_rows,
        "SUCCESS",
        duration
    ))
    conn.commit()

    # 5. Final State Verification
    print("\n" + "=" * 80, flush=True)
    print("FINAL FACT_FOOD_EXPORT VERIFIED SUMMARY (2016 - 2026)", flush=True)
    print("=" * 80, flush=True)

    cursor.execute("""
        SELECT 
            export_year,
            COUNT(*) as clean_fact_rows,
            COUNT(DISTINCT hs_11_code) as distinct_hs,
            COUNT(DISTINCT country_code) as distinct_countries,
            SUM(value_thb) / 1000000000 as total_export_billion_thb,
            SUM(value_usd) / 1000000000 as total_export_billion_usd
        FROM fact_food_export
        GROUP BY export_year
        ORDER BY export_year;
    """)
    summary = cursor.fetchall()
    df_sum = pd.DataFrame(summary)
    print(df_sum.to_string(index=False), flush=True)

    cursor.execute("SELECT COUNT(*) as grand_total FROM fact_food_export;")
    grand_total = cursor.fetchone()["grand_total"]
    cursor.close()
    conn.close()

    print("-" * 80, flush=True)
    print(f"Grand Total Verified Clean Fact Records: {grand_total:,} rows", flush=True)
    print(f"Cleanup Completed in: {duration:.2f} seconds", flush=True)
    print("=" * 80, flush=True)

if __name__ == "__main__":
    main()
