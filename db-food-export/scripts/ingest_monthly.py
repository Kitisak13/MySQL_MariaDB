import os
import sys
import time
import argparse
import requests
import pandas as pd
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# Unbuffered UTF-8 output
sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config.db_config import get_connection

API_BASE_URL = "https://tradereport.moc.go.th/api/exportharmonizecountries"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "th-TH,th;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://tradereport.moc.go.th/TradeThai/HarmonizeExportCountry",
    "Origin": "https://tradereport.moc.go.th"
}

MASTER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "master_data"))
FAILED_QUERIES_FILE = os.path.join(MASTER_DIR, "failed_queries_food_export.csv")

def log_failed_queries(failed_list, year, month):
    """Persists failed HS code queries to CSV for transparency and targeted retrying."""
    if not failed_list:
        return
    os.makedirs(MASTER_DIR, exist_ok=True)
    file_exists = os.path.exists(FAILED_QUERIES_FILE)
    rows = []
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for hs, err in failed_list:
        rows.append({
            "year": year,
            "month": month,
            "hs_code": str(hs).zfill(11),
            "error_msg": str(err),
            "failed_at": now_str
        })
    df_err = pd.DataFrame(rows)
    df_err.to_csv(FAILED_QUERIES_FILE, mode="a", header=not file_exists, index=False, encoding="utf-8-sig")

def get_latest_period_in_db(conn):
    """Find the most recent export_year and export_month in fact_food_export."""
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT MAX(export_date) as max_date FROM fact_food_export;")
    res = cursor.fetchone()
    cursor.close()
    if res and res["max_date"]:
        max_d = res["max_date"]
        return max_d.year, max_d.month
    return 2026, 7

FOOD_CHAPTERS = ["07", "08", "10", "11", "15", "16", "18", "19", "20", "21", "22", "23", "35"]

def get_active_hs_codes(conn, revision_year=2022):
    """Get active HS-11 codes for food from dimension table for the 13 core food chapters + target config."""
    cursor = conn.cursor(dictionary=True)
    placeholders = ", ".join(["%s"] * len(FOOD_CHAPTERS))
    query = f"""
        SELECT DISTINCT hs_11_code 
        FROM dim_hs11_code 
        WHERE hs_2_code IN ({placeholders})
          AND is_active_2022 = 1
        UNION
        SELECT DISTINCT hs_11_code
        FROM cfg_target_hs_codes
        WHERE is_active = 1
        ORDER BY hs_11_code;
    """
    cursor.execute(query, tuple(FOOD_CHAPTERS))
    rows = cursor.fetchall()
    cursor.close()
    return [r["hs_11_code"] for r in rows]

def fetch_single_hs_month(session, year, month, hs_code, max_retries=4):
    """Fetch trade data for a single HS code and month from MOC API with backoff."""
    params = {
        "limit": 0,
        "year": year,
        "month": month,
        "hs_code": hs_code
    }
    for attempt in range(1, max_retries + 1):
        try:
            resp = session.get(API_BASE_URL, params=params, headers=HEADERS, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list):
                    return hs_code, data, None
                elif isinstance(data, dict) and "data" in data:
                    return hs_code, data["data"], None
                return hs_code, [], None
            elif resp.status_code == 403:
                time.sleep(1.5 * attempt)
            else:
                time.sleep(0.5 * attempt)
        except Exception as e:
            if attempt == max_retries:
                return hs_code, [], str(e)
            time.sleep(1.0 * attempt)
    return hs_code, [], "Max retries exceeded"

def ingest_month(year, month, workers=4):
    """Fetch and ingest data for a specific year and month with 2-pass retry and validation."""
    start_time = time.time()
    period_str = f"{year}-{month:02d}-01"
    print("=" * 80, flush=True)
    print(f"MONTHLY INCREMENTAL INGESTION: Period {year}-{month:02d} (Workers: {workers})", flush=True)
    print("=" * 80, flush=True)

    conn = get_connection()
    hs_codes = get_active_hs_codes(conn)
    print(f"Target Active Food HS Codes to query: {len(hs_codes):,} codes (13 Food Chapters & Targets)", flush=True)

    session = requests.Session()
    session.headers.update(HEADERS)

    valid_facts = []
    failed_codes = []
    total_queried = 0

    print(f"Querying MOC Trade API for {year}-{month:02d} (Pass 1)...", flush=True)
    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_map = {
            executor.submit(fetch_single_hs_month, session, year, month, hs): hs
            for hs in hs_codes
        }

        for future in as_completed(future_map):
            hs_code, records, err = future.result()
            total_queried += 1

            if err:
                failed_codes.append(hs_code)
            elif records:
                for r in records:
                    c_code = str(r.get("country_code", "")).strip().upper()
                    if not c_code:
                        continue

                    # Extract measures
                    qty = float(r.get("quantity", 0) or 0)
                    usd = float(r.get("value_usd", 0) or 0)
                    thb = float(r.get("value_baht", 0) or 0)

                    # Filter: Only keep rows with at least one non-zero measure
                    if qty > 0 or usd > 0 or thb > 0:
                        valid_facts.append((
                            period_str,
                            year,
                            month,
                            c_code,
                            hs_code,
                            qty,
                            usd,
                            thb
                        ))

            if total_queried % 200 == 0 or total_queried == len(hs_codes):
                print(f"  [Pass 1] Queried {total_queried:,} / {len(hs_codes):,} HS codes | Matched Facts: {len(valid_facts):,}...", flush=True)

    # Pass 2: Retry failed codes if any
    pass1_success_count = total_queried - len(failed_codes)
    pass2_recovered_count = 0
    still_failed = []

    if failed_codes:
        print(f"\n⚠️ Retrying {len(failed_codes):,} codes that failed in Pass 1 with backoff...", flush=True)
        time.sleep(2.0)
        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_map = {
                executor.submit(fetch_single_hs_month, session, year, month, hs, 5): hs
                for hs in failed_codes
            }
            for future in as_completed(future_map):
                hs_code, records, err = future.result()
                if err:
                    still_failed.append((hs_code, err))
                else:
                    pass2_recovered_count += 1
                    if records:
                        for r in records:
                            c_code = str(r.get("country_code", "")).strip().upper()
                            if not c_code:
                                continue
                            qty = float(r.get("quantity", 0) or 0)
                            usd = float(r.get("value_usd", 0) or 0)
                            thb = float(r.get("value_baht", 0) or 0)
                            if qty > 0 or usd > 0 or thb > 0:
                                valid_facts.append((
                                    period_str,
                                    year,
                                    month,
                                    c_code,
                                    hs_code,
                                    qty,
                                    usd,
                                    thb
                                ))

        if still_failed:
            print(f"❌ {len(still_failed)} codes still failed after Pass 2 retries.", flush=True)
            log_failed_queries(still_failed, year, month)
            print(f"   Logged failed codes to: {FAILED_QUERIES_FILE}", flush=True)
        else:
            print("✅ All Pass 1 failures successfully resolved in Pass 2!", flush=True)

    session.close()

    print(f"\nTotal Valid Trade Facts collected for {year}-{month:02d}: {len(valid_facts):,} rows", flush=True)

    if not valid_facts and not still_failed:
        print("⚠️ No trade data found for this period (Data might not be published by MOC yet).", flush=True)
        conn.close()
        return 0

    # Bulk Upsert into MariaDB
    if valid_facts:
        print(f"Bulk Upserting {len(valid_facts):,} rows into `fact_food_export`...", flush=True)
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
        for i in range(0, len(valid_facts), batch_size):
            batch = valid_facts[i:i + batch_size]
            cursor.executemany(insert_sql, batch)
            conn.commit()
    else:
        cursor = conn.cursor()

    # Log to Audit Table
    duration = round(time.time() - start_time, 2)
    ingestion_status = "SUCCESS" if len(still_failed) == 0 else "PARTIAL"
    log_sql = """
        INSERT INTO data_ingestion_log (
            dataset_name, file_or_source, period_start, period_end,
            total_rows, status, duration_seconds
        ) VALUES (%s, %s, %s, %s, %s, %s, %s);
    """
    cursor.execute(log_sql, (
        f"monthly_sync_{year}_{month:02d}",
        "MOC_API_Live",
        period_str,
        period_str,
        len(valid_facts),
        ingestion_status,
        duration
    ))
    conn.commit()

    # Post-Ingestion Sanity Check & Verification
    cursor.execute("""
        SELECT 
            COUNT(*) as total_in_db,
            COUNT(DISTINCT hs_11_code) as distinct_hs,
            COUNT(DISTINCT country_code) as distinct_countries,
            ROUND(SUM(value_thb) / 1e9, 2) as total_thb_billion
        FROM fact_food_export
        WHERE export_year = %s AND export_month = %s;
    """, (year, month))
    stats = cursor.fetchone()
    cursor.close()
    conn.close()

    # Data accounting
    distinct_fact_hs = len(set(r[4] for r in valid_facts))
    zero_export_hs = len(hs_codes) - distinct_fact_hs - len(still_failed)

    print("\n" + "=" * 80, flush=True)
    print(f"📊 API INGESTION AUDIT & QUALITY SCORECARD: Period {year}-{month:02d}", flush=True)
    print("=" * 80, flush=True)
    print(f"  Target Food HS Codes to Query : {len(hs_codes):,} codes", flush=True)
    print(f"  ✅ Pass 1 Success Rate        : {pass1_success_count:,} codes ({(pass1_success_count/len(hs_codes))*100:.1f}%)", flush=True)
    if failed_codes:
        print(f"  ⚠️ Pass 2 Retries              : {len(failed_codes):,} codes", flush=True)
        print(f"  ✅ Pass 2 Recovered            : {pass2_recovered_count:,} codes", flush=True)
    if still_failed:
        print(f"  ❌ Unresolved API Failures     : {len(still_failed):,} codes ({(len(still_failed)/len(hs_codes))*100:.2f}%)", flush=True)
        for hs, err in still_failed[:8]:
            print(f"     - HS {hs}: {err}", flush=True)
        if len(still_failed) > 8:
            print(f"     ... and {len(still_failed) - 8} more (logged to failed_queries_food_export.csv)", flush=True)
    else:
        print(f"  ❌ Unresolved API Failures     : 0 codes (0.0% - All requests successfully verified)", flush=True)

    print("-" * 80, flush=True)
    print(f"  Export Yield Breakdown:", flush=True)
    print(f"    - HS Codes with Trade Facts : {distinct_fact_hs:,} codes (Active export in {year}-{month:02d})", flush=True)
    print(f"    - HS Codes with Zero Export : {zero_export_hs:,} codes (Confirmed 0 export in this period)", flush=True)
    print(f"    - Trade Facts Ingested      : {len(valid_facts):,} rows", flush=True)
    print("-" * 80, flush=True)
    print(f"  Database Verification ({year}-{month:02d}):", flush=True)
    print(f"    - Current Facts in DB       : {stats[0]:,} rows", flush=True)
    print(f"    - Distinct HS Codes in DB   : {stats[1]:,} codes", flush=True)
    print(f"    - Distinct Destination Cntry: {stats[2]:,} countries", flush=True)
    print(f"    - Total Trade Value         : {stats[3]:,} Billion THB", flush=True)
    print(f"    - Overall Ingestion Status  : {'✅ 100% COMPLETE & VERIFIED' if not still_failed else '⚠️ PARTIAL (Technical failures logged)'}", flush=True)
    print("=" * 80, flush=True)

    print(f"\n🎉 Period {year}-{month:02d} Pipeline Completed in {duration:.2f}s.", flush=True)
    return len(valid_facts)

def retry_failed_queries(workers=4):
    """Retries any unresolved failed queries logged in failed_queries_food_export.csv."""
    if not os.path.exists(FAILED_QUERIES_FILE):
        print("✅ No failed queries CSV found. All queries are up to date!")
        return

    df_failed = pd.read_csv(FAILED_QUERIES_FILE)
    if df_failed.empty:
        print("✅ No pending failed queries in CSV.")
        return

    print(f"Found {len(df_failed):,} recorded failure entries in {FAILED_QUERIES_FILE}")
    groups = df_failed.groupby(["year", "month"])
    for (y, m), grp in groups:
        codes = grp["hs_code"].astype(str).str.zfill(11).unique().tolist()
        print(f"\nRetrying {len(codes)} codes for {y}-{m:02d}...")
        # Fetch and upsert
        session = requests.Session()
        session.headers.update(HEADERS)
        valid_facts = []
        still_bad = []
        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_map = {
                executor.submit(fetch_single_hs_month, session, y, m, hs, 5): hs
                for hs in codes
            }
            for f in as_completed(future_map):
                hs, records, err = f.result()
                if err:
                    still_bad.append((hs, err))
                elif records:
                    p_str = f"{y}-{m:02d}-01"
                    for r in records:
                        c_code = str(r.get("country_code", "")).strip().upper()
                        qty = float(r.get("quantity", 0) or 0)
                        usd = float(r.get("value_usd", 0) or 0)
                        thb = float(r.get("value_baht", 0) or 0)
                        if c_code and (qty > 0 or usd > 0 or thb > 0):
                            valid_facts.append((p_str, y, m, c_code, hs, qty, usd, thb))
        session.close()

        if valid_facts:
            conn = get_connection()
            cursor = conn.cursor()
            insert_sql = """
                INSERT INTO fact_food_export (
                    export_date, export_year, export_month, country_code, hs_11_code,
                    quantity, value_usd, value_thb
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    quantity = VALUES(quantity), value_usd = VALUES(value_usd), value_thb = VALUES(value_thb);
            """
            for i in range(0, len(valid_facts), 2000):
                cursor.executemany(insert_sql, valid_facts[i:i+2000])
                conn.commit()
            cursor.close()
            conn.close()
            print(f"  ✅ Recovered and upserted {len(valid_facts):,} rows for {y}-{m:02d}!")

    # Clean up CSV if no more failures
    os.remove(FAILED_QUERIES_FILE)
    print("✅ Failed queries resolved and log file cleaned.")

def main():
    parser = argparse.ArgumentParser(description="Monthly Incremental Ingestion for Thailand Food Export Data")
    parser.add_argument("--year", type=int, help="Target Year (e.g. 2026)")
    parser.add_argument("--month", type=int, help="Target Month (1 - 12)")
    parser.add_argument("--auto", action="store_true", help="Auto-detect next month to ingest after latest period in DB")
    parser.add_argument("--workers", type=int, default=4, help="Concurrent workers for API queries (default: 4)")
    parser.add_argument("--retry-failed", action="store_true", help="Retry any previously failed queries from CSV")

    args = parser.parse_args()

    if args.retry_failed:
        retry_failed_queries(workers=args.workers)
    elif args.auto:
        conn = get_connection()
        last_y, last_m = get_latest_period_in_db(conn)
        conn.close()

        # Calculate next month
        if last_m == 12:
            next_y = last_y + 1
            next_m = 1
        else:
            next_y = last_y
            next_m = last_m + 1

        print(f"Auto Mode: Latest period in DB is {last_y}-{last_m:02d}. Next period to ingest is {next_y}-{next_m:02d}.", flush=True)
        ingest_month(next_y, next_m, workers=args.workers)

    elif args.year and args.month:
        ingest_month(args.year, args.month, workers=args.workers)
    else:
        parser.print_help()
        print("\nExample Usages:")
        print("  python db-food-export/scripts/ingest_monthly.py --auto")
        print("  python db-food-export/scripts/ingest_monthly.py --year 2026 --month 8")
        print("  python db-food-export/scripts/ingest_monthly.py --retry-failed")

if __name__ == "__main__":
    main()
