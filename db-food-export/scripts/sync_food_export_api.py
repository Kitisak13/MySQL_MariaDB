import os
import sys
import time
import json
import argparse
import threading
import requests
import pandas as pd
from typing import List, Dict, Any, Tuple, Optional, Set
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

# Ensure UTF-8 output
sys.stdout.reconfigure(encoding="utf-8")

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config.db_config import get_connection
from etl.transformers import transform_api_export_rows
from etl.loaders import bulk_upsert_fact_food_export, log_ingestion

try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False

BASE_URL = "https://tradereport.moc.go.th/api/exportharmonizecountries"
HEALTH_CHECK_URL = "https://tradereport.moc.go.th/api/harmonizestructure?revision=2022&digits=2&limit=1"
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "th-TH,th;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://tradereport.moc.go.th/TradeThai/CustomsHarmonizeExportCountry",
    "Connection": "keep-alive"
}

FOOD_CHAPTERS = ["07", "08", "10", "11", "15", "16", "18", "19", "20", "21", "22", "23", "35"]
MASTER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "master_data"))
CHECKPOINT_FILE = os.path.join(MASTER_DIR, "checkpoint_completed_queries.json")
FAILED_QUERIES_FILE = os.path.join(MASTER_DIR, "failed_queries_food_export.csv")

# Thread-local session management for connection pooling
_thread_local = threading.local()

def get_thread_session() -> requests.Session:
    """Returns or creates a thread-local requests Session with retry adapter and connection pooling."""
    if not hasattr(_thread_local, "session"):
        session = requests.Session()
        session.headers.update(DEFAULT_HEADERS)
        retry_strat = Retry(
            total=2,
            backoff_factor=0.3,
            status_forcelist=[500, 502, 503, 504],
            raise_on_status=False
        )
        adapter = HTTPAdapter(max_retries=retry_strat, pool_connections=10, pool_maxsize=10)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        _thread_local.session = session
    return _thread_local.session

def load_checkpoint() -> Set[str]:
    """Loads set of completed query keys (e.g. '2016-05_10063040001')."""
    if os.path.exists(CHECKPOINT_FILE):
        try:
            with open(CHECKPOINT_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return set(data)
        except Exception:
            pass
    return set()

def save_checkpoint(completed_set: Set[str]):
    """Persists completed query keys to JSON."""
    os.makedirs(MASTER_DIR, exist_ok=True)
    with open(CHECKPOINT_FILE, "w", encoding="utf-8") as f:
        json.dump(list(completed_set), f)

def log_failed_query(year: int, month: int, hs_code: str, error_msg: str):
    """Appends true technical failure to CSV for audit and targeted retrying."""
    os.makedirs(MASTER_DIR, exist_ok=True)
    file_exists = os.path.exists(FAILED_QUERIES_FILE)
    df_err = pd.DataFrame([{
        "year": year,
        "month": month,
        "hs_code": str(hs_code).zfill(11),
        "error_msg": str(error_msg),
        "failed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }])
    df_err.to_csv(FAILED_QUERIES_FILE, mode="a", header=not file_exists, index=False, encoding="utf-8-sig")

def check_internet_health() -> bool:
    """Verifies connection to MOC server."""
    try:
        r = requests.get(HEALTH_CHECK_URL, headers=DEFAULT_HEADERS, timeout=8)
        return r.status_code == 200
    except Exception:
        return False

def wait_for_connection_recovery(max_wait_seconds: int = 600):
    """Pauses pipeline and polls until network connection is restored."""
    print("\n⚠️ [Network Alert] Connection dropped or server unreachable. Pausing pipeline...")
    waited = 0
    while waited < max_wait_seconds:
        time.sleep(5)
        waited += 5
        if check_internet_health():
            print(f"✅ [Network Restored] Connection re-established after {waited}s! Resuming pipeline...\n")
            return True
        print(f"   Waiting for connection to recover... ({waited}s elapsed)")
    print("❌ [Fatal Error] Network did not recover within timeout period.")
    return False

def get_applicable_hs_codes_for_year(year: int, chapters: List[str] = FOOD_CHAPTERS) -> List[str]:
    """
    Queries dim_hs11_code and applies Smart Revision Filtering:
    - Year <= 2016: Revision 2012 era (first_seen_revision <= 2012)
    - Year 2017 to 2021: Revision 2017 era (first_seen_revision <= 2017 AND latest_revision >= 2017)
    - Year >= 2022: Revision 2022 era (latest_revision >= 2022)
    """
    conn = get_connection()
    cursor = conn.cursor()
    placeholders = ", ".join(["%s"] * len(chapters))

    if year <= 2016:
        query = f"""
            SELECT hs_11_code 
            FROM dim_hs11_code 
            WHERE hs_2_code IN ({placeholders}) 
              AND first_seen_revision <= 2012
            ORDER BY hs_11_code;
        """
    elif 2017 <= year <= 2021:
        query = f"""
            SELECT hs_11_code 
            FROM dim_hs11_code 
            WHERE hs_2_code IN ({placeholders}) 
              AND first_seen_revision <= 2017 
              AND latest_revision >= 2017
            ORDER BY hs_11_code;
        """
    else: # 2022+
        query = f"""
            SELECT hs_11_code 
            FROM dim_hs11_code 
            WHERE hs_2_code IN ({placeholders}) 
              AND latest_revision >= 2022
            ORDER BY hs_11_code;
        """

    cursor.execute(query, tuple(chapters))
    codes = [row[0] for row in cursor.fetchall()]
    cursor.close()
    conn.close()
    return codes

def fetch_single_hs_code(year: int, month: int, hs_code: str, max_retries: int = 3) -> Tuple[str, List[Dict[str, Any]], Optional[str]]:
    """
    Fetches export trade data for a single HS code.
    Distinguishes clearly between 'No Trade Data' (HTTP 200 Empty) vs 'Technical Failure' (HTTP 500 / Timeout).
    """
    params = {
        "limit": 0,
        "year": year,
        "month": month,
        "hs_code": hs_code
    }
    session = get_thread_session()
    last_err = None

    for attempt in range(1, max_retries + 1):
        try:
            r = session.get(BASE_URL, params=params, timeout=25)
            if r.status_code == 200:
                if not r.text or not r.text.strip():
                    # Valid Empty: Server responded successfully, no trade data for this code
                    return hs_code, [], None
                try:
                    data = r.json()
                    if isinstance(data, list) and len(data) > 0:
                        return hs_code, data, None
                    # Valid Empty: Empty JSON array []
                    return hs_code, [], None
                except Exception as e:
                    last_err = f"JSONDecodeError: {e}"
            elif r.status_code in (500, 502, 503, 504, 429):
                last_err = f"HTTP {r.status_code}"
            else:
                return hs_code, [], f"HTTP {r.status_code}"
        except Exception as e:
            last_err = str(e)

        time.sleep(0.2 * attempt)

    # Technical failure after all retries exhausted
    return hs_code, [], last_err

def sync_monthly_food_export(year: int, month: int, hs_codes: List[str], 
                              completed_checkpoint: Set[str], max_workers: int = 8) -> Tuple[int, int, int]:
    """
    Pulls target HS codes for a single month concurrently, loads in batches, and updates checkpoints.
    """
    period_str = f"{year}-{month:02d}"
    
    # Filter out already completed HS codes for this month
    pending_codes = [code for code in hs_codes if f"{period_str}_{code}" not in completed_checkpoint]
    
    if not pending_codes:
        print(f"⚡ Period {period_str}: All {len(hs_codes):,} applicable HS codes already synced in checkpoint. Skipping!")
        return 0, 0, 0

    print(f"\n--- Processing Period: {period_str} ({len(pending_codes):,} pending / {len(hs_codes):,} applicable HS codes) ---")
    
    month_start_time = time.time()
    collected_facts = []
    data_count = 0
    empty_count = 0
    err_count = 0
    total_loaded_for_month = 0
    consecutive_errors = 0

    pbar = tqdm(total=len(pending_codes), desc=f"[{period_str}]", unit="code") if HAS_TQDM else None

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {
            executor.submit(fetch_single_hs_code, year, month, hs_code): hs_code
            for hs_code in pending_codes
        }

        for future in as_completed(future_map):
            hs_code, raw_rows, err = future.result()
            query_key = f"{period_str}_{hs_code}"

            if err:
                err_count += 1
                consecutive_errors += 1
                log_failed_query(year, month, hs_code, err)

                # Check if entire network dropped
                if consecutive_errors >= 6:
                    if not check_internet_health():
                        wait_for_connection_recovery()
                    consecutive_errors = 0
            else:
                consecutive_errors = 0
                completed_checkpoint.add(query_key)

                if raw_rows:
                    data_count += 1
                    facts = transform_api_export_rows(raw_rows, year, month, hs_code)
                    collected_facts.extend(facts)
                else:
                    empty_count += 1

                # In-flight flush every 100 data records
                if len(collected_facts) >= 100:
                    loaded = bulk_upsert_fact_food_export(collected_facts)
                    total_loaded_for_month += loaded
                    collected_facts.clear()
                    save_checkpoint(completed_checkpoint)

            if pbar:
                pbar.update(1)
                pbar.set_postfix({"Data": data_count, "Empty": empty_count, "Err": err_count})

    if pbar:
        pbar.close()

    # Final flush remaining facts for this month
    if collected_facts:
        loaded = bulk_upsert_fact_food_export(collected_facts)
        total_loaded_for_month += loaded
        collected_facts.clear()

    save_checkpoint(completed_checkpoint)

    duration = round(time.time() - month_start_time, 2)
    print(f"Completed {period_str} in {duration:.1f}s | Fact Rows Ingested: {total_loaded_for_month:,} | HS with Data: {data_count} | Empty: {empty_count} | Errors: {err_count}")

    # Audit logging
    log_ingestion(
        dataset_name="monthly_food_export_api",
        file_or_source=f"MOC_API_{period_str}",
        period_start=date(year, month, 1),
        period_end=date(year, month, 1),
        total_rows=total_loaded_for_month,
        status="SUCCESS" if err_count == 0 else "PARTIAL",
        duration_seconds=duration
    )

    return total_loaded_for_month, data_count, err_count

def retry_failed_queries(max_workers: int = 4):
    """Reads failed_queries_food_export.csv and retries only those queries."""
    if not os.path.exists(FAILED_QUERIES_FILE):
        print("No failed queries CSV found. All queries healthy!")
        return

    df_failed = pd.read_csv(FAILED_QUERIES_FILE)
    if len(df_failed) == 0:
        print("Failed queries list is empty!")
        return

    print("=" * 80)
    print(f"TARGETED RETRY OF {len(df_failed):,} FAILED QUERIES")
    print("=" * 80)

    completed_checkpoint = load_checkpoint()
    collected_facts = []
    success_count = 0
    still_failed = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {}
        for _, row in df_failed.iterrows():
            y = int(row["year"])
            m = int(row["month"])
            hs = str(row["hs_code"]).zfill(11)
            future = executor.submit(fetch_single_hs_code, y, m, hs, max_retries=4)
            future_map[future] = (y, m, hs)

        for future in as_completed(future_map):
            y, m, hs = future_map[future]
            hs_code, raw_rows, err = future.result()
            query_key = f"{y}-{m:02d}_{hs}"

            if err:
                still_failed.append({"year": y, "month": m, "hs_code": hs, "error_msg": err, "failed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
            else:
                success_count += 1
                completed_checkpoint.add(query_key)
                if raw_rows:
                    facts = transform_api_export_rows(raw_rows, y, m, hs)
                    collected_facts.extend(facts)

    if collected_facts:
        loaded = bulk_upsert_fact_food_export(collected_facts)
        print(f"Upserted {loaded:,} fact records from resolved queries into MariaDB!")

    save_checkpoint(completed_checkpoint)

    # Update failed queries file
    if still_failed:
        pd.DataFrame(still_failed).to_csv(FAILED_QUERIES_FILE, index=False, encoding="utf-8-sig")
        print(f"⚠️ {len(still_failed)} queries still unresolved. Saved to {FAILED_QUERIES_FILE}")
    else:
        if os.path.exists(FAILED_QUERIES_FILE):
            os.remove(FAILED_QUERIES_FILE)
        print("🎉 ALL previously failed queries successfully resolved and cleared!")

def run_sync_pipeline(years: List[int], months: List[int], chapters: List[str], max_workers: int = 8):
    pipeline_start = time.time()
    print("=" * 80)
    print("THAILAND FOOD EXPORT DATA WAREHOUSE - SMART MOC API INGESTION PIPELINE")
    print("=" * 80)
    print(f"Target Years    : {years}")
    print(f"Target Months   : {months}")
    print(f"Target Chapters : {chapters} (13 Food & Agricultural Chapters)")
    print(f"Concurrency     : {max_workers} parallel workers with HTTP Connection Pooling")

    # Load Checkpoint
    completed_checkpoint = load_checkpoint()
    print(f"Loaded Checkpoint: {len(completed_checkpoint):,} previously completed query tasks.")

    total_periods = len(years) * len(months)
    current_period = 0
    grand_total_facts = 0
    grand_total_errors = 0

    for y in sorted(years):
        # Dynamically retrieve applicable HS codes for this specific year (Smart Revision Filtering)
        applicable_hs_codes = get_applicable_hs_codes_for_year(y, chapters)
        print(f"\n[Year {y}] Smart Revision Filter: {len(applicable_hs_codes):,} applicable HS codes for year {y}.")

        for m in sorted(months):
            current_period += 1
            print(f"\n[Period {current_period}/{total_periods}]")
            facts_loaded, data_codes, errors = sync_monthly_food_export(
                year=y, month=m, hs_codes=applicable_hs_codes,
                completed_checkpoint=completed_checkpoint,
                max_workers=max_workers
            )
            grand_total_facts += facts_loaded
            grand_total_errors += errors

    total_duration = round(time.time() - pipeline_start, 2)
    print("\n" + "=" * 80)
    print("SMART INGESTION PIPELINE EXECUTION SUMMARY")
    print(f"Total Fact Rows Ingested : {grand_total_facts:,}")
    print(f"Total Errors Recorded    : {grand_total_errors:,}")
    print(f"Total Processing Time    : {total_duration:.2f} seconds ({total_duration/60:.2f} mins)")
    print("=" * 80)

def main():
    parser = argparse.ArgumentParser(description="Synchronize Food Export Data from MOC API into MariaDB")
    parser.add_argument("--years", nargs="+", type=int, default=[2016, 2017], help="Target observation years (default: 2016 2017)")
    parser.add_argument("--months", nargs="+", type=int, default=list(range(1, 13)), help="Target observation months (1 to 12)")
    parser.add_argument("--chapters", nargs="+", type=str, default=FOOD_CHAPTERS, help="Target 2-digit HS chapters")
    parser.add_argument("--workers", type=int, default=8, help="Concurrent worker threads (default: 8)")
    parser.add_argument("--retry-failed", action="store_true", help="Retry all failed queries recorded in CSV")

    args = parser.parse_args()

    if args.retry_failed:
        retry_failed_queries(max_workers=args.workers)
    else:
        run_sync_pipeline(years=args.years, months=args.months, chapters=args.chapters, max_workers=args.workers)

if __name__ == "__main__":
    main()
