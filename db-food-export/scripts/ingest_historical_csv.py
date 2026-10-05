import os
import sys
import time
import pandas as pd
from datetime import datetime

# Unbuffered output
sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config.db_config import get_connection

def ensure_missing_hs_codes(conn):
    """Ensure any missing HS codes in historical CSV exist in dim_hs11_code."""
    cursor = conn.cursor(dictionary=True)
    # Check 15162053090
    cursor.execute("SELECT hs_11_code FROM dim_hs11_code WHERE hs_11_code = '15162053090';")
    if not cursor.fetchone():
        print("Adding missing HS code 15162053090 to dim_hs11_code...", flush=True)
        cursor.execute("""
            INSERT INTO dim_hs11_code (
                hs_11_code, hs_11_description_th, hs_11_description_en,
                hs_8_code, hs_8_description_th, hs_8_description_en,
                hs_4_code, hs_4_description_th, hs_4_description_en,
                hs_2_code, hs_2_description_th, hs_2_description_en,
                unit_code, unit_name, first_seen_revision, latest_revision, is_active_2022
            ) VALUES (
                '15162053090', 'ไขมันและน้ำมันจากพืชและส่วนย่อยของไขมันและน้ำมันดังกล่าว', 'Vegetable fats and oils and their fractions',
                '15162053', 'ไขมันและน้ำมันจากพืชและส่วนย่อยของไขมันและน้ำมันดังกล่าว', 'Vegetable fats and oils and their fractions',
                '1516', 'ไขมันและน้ำมันจากสัตว์หรือพืช', 'Animal or vegetable fats and oils',
                '15', 'ไขมันและน้ำมันที่ได้จากสัตว์หรือพืช', 'Animal or vegetable fats and oils',
                'KGM', 'KG', 2017, 2022, 1
            ) ON DUPLICATE KEY UPDATE hs_11_code = VALUES(hs_11_code);
        """)
        conn.commit()
    cursor.close()

def main():
    start_time = time.time()
    print("=" * 80, flush=True)
    print("FAST VECTORIZED INGESTION (2018 - 2026) INTO fact_food_export", flush=True)
    print("=" * 80, flush=True)

    csv_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "master_data", "food_hs_ex_database_updated.csv"))
    if not os.path.exists(csv_path):
        print(f"Error: Target CSV file not found: {csv_path}", flush=True)
        return

    conn = get_connection()

    # Step 1: Ensure Foreign Key Integrity
    print("[1/3] Ensuring Dimension Foreign Keys Integrity...", flush=True)
    ensure_missing_hs_codes(conn)

    # Step 2: Read and Pivot Fast Vectorized
    print("\n[2/3] Vectorized Processing of CSV (2018 - 2026)...", flush=True)
    
    # We load columns: ['country_code', 'HS_11 Digit', 'Type', 'Value', 'Date']
    chunks = []
    total_raw_rows = 0
    
    for chunk in pd.read_csv(csv_path, chunksize=1_000_000, dtype={"country_code": str, "HS_11 Digit": str, "Type": str, "Value": float, "Date": str}):
        total_raw_rows += len(chunk)
        # Filter for Date >= 2018-01-01 and Value.notna() and Value > 0
        filtered = chunk[(chunk["Date"] >= "2018-01-01") & (chunk["Value"].notna()) & (chunk["Value"] > 0)].copy()
        if len(filtered) > 0:
            filtered["country_code"] = filtered["country_code"].str.strip().str.upper()
            filtered["HS_11 Digit"] = filtered["HS_11 Digit"].str.strip().str.zfill(11)
            filtered["Date"] = filtered["Date"].str.strip()
            filtered["Type"] = filtered["Type"].str.strip().str.lower()
            # Standardize Type name
            filtered["Type"] = filtered["Type"].replace({"value_baht": "value_thb"})
            chunks.append(filtered)
        print(f"  Scanned {total_raw_rows:,} raw rows from CSV...", flush=True)

    print(f"\nConcatenating {len(chunks)} filtered chunks...", flush=True)
    df_all = pd.concat(chunks, ignore_index=True)
    del chunks
    print(f"Total non-zero measure rows (2018-2026): {len(df_all):,}", flush=True)

    print("Pivoting Long-format to Star Schema Fact table...", flush=True)
    pivoted = df_all.pivot_table(
        index=["Date", "country_code", "HS_11 Digit"],
        columns="Type",
        values="Value",
        aggfunc="sum",
        fill_value=0.0
    ).reset_index()
    del df_all

    # Ensure all required measure columns exist
    for col in ["quantity", "value_usd", "value_thb"]:
        if col not in pivoted.columns:
            pivoted[col] = 0.0

    pivoted["export_year"] = pivoted["Date"].str[:4].astype(int)
    pivoted["export_month"] = pivoted["Date"].str[5:7].astype(int)

    total_facts = len(pivoted)
    print(f"\n[3/3] Total Unique Facts to Ingest: {total_facts:,} rows", flush=True)

    # Step 3: Fast Bulk Upsert
    insert_sql = """
        INSERT INTO fact_food_export (
            export_date, export_year, export_month, country_code, hs_11_code,
            quantity, value_usd, value_thb
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s
        ) ON DUPLICATE KEY UPDATE
            quantity = VALUES(quantity),
            value_usd = VALUES(value_usd),
            value_thb = VALUES(value_thb);
    """

    cursor = conn.cursor()
    batch_size = 2_000
    upserted_count = 0

    rows_to_insert = [
        (
            row.Date,
            row.export_year,
            row.export_month,
            row.country_code,
            getattr(row, "_3"), # HS_11 Digit
            float(row.quantity),
            float(row.value_usd),
            float(row.value_thb)
        )
        for row in pivoted.itertuples()
    ]
    del pivoted

    print(f"Beginning Bulk Upsert in batches of {batch_size:,}...", flush=True)
    for i in range(0, len(rows_to_insert), batch_size):
        batch = rows_to_insert[i:i + batch_size]
        cursor.executemany(insert_sql, batch)
        conn.commit()
        upserted_count += len(batch)
        print(f"  Upserted {upserted_count:,} / {total_facts:,} facts ({upserted_count/total_facts*100:.1f}%)...", flush=True)

    del rows_to_insert

    # Step 4: Audit Log
    duration = round(time.time() - start_time, 2)
    log_sql = """
        INSERT INTO data_ingestion_log (
            dataset_name, file_or_source, period_start, period_end,
            total_rows, status, duration_seconds
        ) VALUES (%s, %s, %s, %s, %s, %s, %s);
    """
    cursor.execute(log_sql, (
        "historical_csv_sync_2018_2026",
        os.path.basename(csv_path),
        "2018-01-01",
        "2026-07-01",
        upserted_count,
        "SUCCESS",
        duration
    ))
    conn.commit()
    cursor.close()

    # Step 5: Complete Database Summary
    print("\n" + "=" * 80, flush=True)
    print("FACT_FOOD_EXPORT FULL DATABASE SUMMARY (2016 - 2026)", flush=True)
    print("=" * 80, flush=True)

    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT 
            export_year,
            COUNT(*) as fact_rows,
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
    print(f"Grand Total Fact Transactions in MariaDB: {grand_total:,} rows", flush=True)
    print(f"Ingestion Completed in: {duration:.2f} seconds ({duration/60:.2f} mins)", flush=True)
    print("=" * 80, flush=True)

if __name__ == "__main__":
    main()
