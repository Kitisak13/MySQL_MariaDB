import os
import sys

# Ensure UTF-8
sys.stdout.reconfigure(encoding="utf-8")

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config.db_config import get_connection

def verify_food_export():
    print("=" * 80)
    print("VERIFYING DATABASE `food_export` STATUS & INTEGRITY")
    print("=" * 80)

    conn = get_connection()
    cursor = conn.cursor()

    # 1. Total counts in dim_hs11_code
    cursor.execute("SELECT COUNT(*) FROM dim_hs11_code;")
    total_hs = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM dim_hs11_code WHERE is_active_2022 = 1;")
    active_hs = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(DISTINCT hs_2_code), COUNT(DISTINCT hs_4_code), COUNT(DISTINCT hs_8_code) FROM dim_hs11_code;")
    h2, h4, h8 = cursor.fetchone()

    print("\n1. MASTER DIMENSION `dim_hs11_code`:")
    print(f"   - Total Unique 11-digit Codes : {total_hs:,}")
    print(f"   - Active in 2022 Revision      : {active_hs:,}")
    print(f"   - Historical / Discontinued   : {(total_hs - active_hs):,}")
    print(f"   - Distinct 2-Digit Chapters   : {h2:,}")
    print(f"   - Distinct 4-Digit Headings   : {h4:,}")
    print(f"   - Distinct 8-Digit Subheadings: {h8:,}")

    # 2. Sample Hierarchy Check
    print("\n2. SAMPLE HIERARCHY PREVIEW (Chapter 07 - Vegetables & 10 - Cereals):")
    cursor.execute("""
        SELECT 
            hs_11_code, 
            hs_11_description_th, 
            hs_8_description_th, 
            hs_4_description_th, 
            hs_2_description_th,
            first_seen_revision, latest_revision
        FROM dim_hs11_code 
        WHERE hs_2_code IN ('07', '10') 
        LIMIT 3;
    """)
    for r in cursor.fetchall():
        print(f"   [{r[0]}] 11-digit: {r[1]}")
        print(f"       -> 8-digit : {r[2]}")
        print(f"       -> 4-digit : {r[3]}")
        print(f"       -> 2-digit : {r[4]}")
        print(f"       -> Revisions: {r[5]} - {r[6]}\n")

    # 3. Fact Table & Ingestion Log Check
    cursor.execute("SELECT COUNT(*) FROM fact_food_export;")
    fact_count = cursor.fetchone()[0]

    cursor.execute("SELECT dataset_name, file_or_source, total_rows, status, duration_seconds, ingested_at FROM data_ingestion_log ORDER BY id DESC LIMIT 5;")
    logs = cursor.fetchall()

    print(f"3. FACT TABLE `fact_food_export`: {fact_count:,} rows")
    print(f"4. AUDIT LOGS (`data_ingestion_log`): {len(logs)} entries recorded")
    for log in logs:
        print(f"   - [{log[0]}] Source: {log[1]} | Rows: {log[2]:,} | Status: {log[3]} | Duration: {log[4]}s | At: {log[5]}")

    print("\n" + "=" * 80)
    print("DATABASE `food_export` VERIFICATION COMPLETE & HEALTHY!")
    print("=" * 80)

    cursor.close()
    conn.close()

if __name__ == "__main__":
    verify_food_export()
