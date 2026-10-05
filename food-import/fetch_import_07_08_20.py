import os
import sys
import time
import json
import threading
import argparse
import requests
import pandas as pd
from datetime import datetime
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from concurrent.futures import ThreadPoolExecutor, as_completed

# Unbuffered UTF-8 output
sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

API_BASE_URL = "https://tradereport.moc.go.th/api/importharmonizecountries"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "th-TH,th;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://tradereport.moc.go.th/TradeThai/HarmonizeImportCountry",
    "Origin": "https://tradereport.moc.go.th"
}

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MASTER_DATA_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "db-food-export", "master_data"))

COUNTRY_MASTER_PATH = os.path.join(MASTER_DATA_DIR, "dim_country_master.csv")
HS_MASTER_PATH = os.path.join(MASTER_DATA_DIR, "dim_hs11_code_master.csv")

CHECKPOINT_FILE = os.path.join(SCRIPT_DIR, "checkpoint_import.json")
OUTPUT_CSV = os.path.join(SCRIPT_DIR, "food_07_08_20_import.csv")
FAILED_QUERIES_FILE = os.path.join(SCRIPT_DIR, "failed_import_queries.json")

thread_local = threading.local()

def get_session():
    if not hasattr(thread_local, "session"):
        session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"]
        )
        adapter = HTTPAdapter(pool_connections=20, pool_maxsize=20, max_retries=retry_strategy)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        session.headers.update(HEADERS)
        thread_local.session = session
    return thread_local.session

def load_checkpoint():
    if os.path.exists(CHECKPOINT_FILE):
        try:
            with open(CHECKPOINT_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()

def save_checkpoint(completed_set):
    with open(CHECKPOINT_FILE, "w", encoding="utf-8") as f:
        json.dump(list(completed_set), f)

def get_dimension_data():
    """Load dim_country and dim_hs11_code from Master CSV files."""
    # 1. Countries
    df_c = pd.read_csv(COUNTRY_MASTER_PATH, dtype=str)
    countries = {}
    for _, r in df_c.iterrows():
        c_code = str(r["country_code"]).strip().upper()
        countries[c_code] = {
            "country_name": str(r.get("country_name", "")),
            "country_name_th": str(r.get("country_name_th", "")),
            "country_name_en": str(r.get("country_name_en", "")),
            "iso_region": str(r.get("iso_region", "")),
            "iso_sub_region": str(r.get("iso_sub_region", "")),
            "region_cia": str(r.get("region_cia", ""))
        }

    # 2. HS Codes (Chapters 07, 08, 20)
    df_hs = pd.read_csv(HS_MASTER_PATH, dtype=str)
    df_target = df_hs[df_hs["hs_2_code"].isin(["07", "08", "20"])]
    hs_dict = {}
    for _, r in df_target.iterrows():
        code_11 = str(r["hs_11_code"]).strip().zfill(11)
        hs_dict[code_11] = {
            "hs_11_description_th": str(r.get("hs_11_description_th", "")),
            "hs_11_description_en": str(r.get("hs_11_description_en", "")),
            "hs_8_code": str(r.get("hs_8_code", code_11[:8])),
            "hs_8_description_th": str(r.get("hs_8_description_th", "")),
            "hs_8_description_en": str(r.get("hs_8_description_en", "")),
            "hs_4_code": str(r.get("hs_4_code", code_11[:4])),
            "hs_4_description_th": str(r.get("hs_4_description_th", "")),
            "hs_4_description_en": str(r.get("hs_4_description_en", "")),
            "hs_2_code": str(r.get("hs_2_code", code_11[:2])),
            "hs_2_description_th": str(r.get("hs_2_description_th", "")),
            "hs_2_description_en": str(r.get("hs_2_description_en", "")),
            "unit_code": str(r.get("unit_code", "")),
            "unit_name": str(r.get("unit_name", ""))
        }

    return countries, hs_dict

def fetch_single_query(year, month, hs_code, max_retries=5):
    session = get_session()
    params = {
        "limit": 0,
        "year": year,
        "month": month,
        "hs_code": hs_code
    }
    for attempt in range(1, max_retries + 1):
        try:
            resp = session.get(API_BASE_URL, params=params, timeout=12)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list):
                    return year, month, hs_code, data, None
                elif isinstance(data, dict) and "data" in data:
                    return year, month, hs_code, data["data"], None
                return year, month, hs_code, [], None
            elif resp.status_code == 403:
                time.sleep(1.2 * attempt)
            else:
                time.sleep(0.5 * attempt)
        except Exception as e:
            if attempt == max_retries:
                return year, month, hs_code, [], str(e)
            time.sleep(0.5 * attempt)
    return year, month, hs_code, [], "Max retries exceeded"

def main():
    parser = argparse.ArgumentParser(description="Fetch Thailand Food Import Data (07, 08, 20)")
    parser.add_argument("--workers", type=int, default=4, help="Concurrent workers (default: 4)")
    args = parser.parse_args()

    start_time = time.time()
    print("=" * 80, flush=True)
    print(f"MOC FOOD IMPORT EXTRACTION (Chapters 07, 08, 20 | 2016-01 to 2026-07) [Workers: {args.workers}]", flush=True)
    print("=" * 80, flush=True)

    # 1. Load Dimensions
    print("Loading Master Dimensions from catalog...", flush=True)
    dim_country, dim_hs = get_dimension_data()
    print(f"Loaded {len(dim_country):,} countries and {len(dim_hs):,} target HS codes.", flush=True)

    # 2. Build Query Matrix
    months_list = []
    for y in range(2016, 2027):
        max_m = 7 if y == 2026 else 12
        for m in range(1, max_m + 1):
            months_list.append((y, m))

    all_queries = []
    for y, m in months_list:
        for hs_code in dim_hs.keys():
            all_queries.append((y, m, hs_code))

    completed_keys = load_checkpoint()
    pending_queries = [
        q for q in all_queries
        if f"{q[0]}-{q[1]:02d}_{q[2]}" not in completed_keys
    ]

    print(f"Total Period Months: {len(months_list):,} (2016-01 to 2026-07)", flush=True)
    print(f"Total Query Tasks: {len(all_queries):,} | Completed: {len(completed_keys):,} | Remaining: {len(pending_queries):,}", flush=True)

    if not pending_queries:
        print("🎉 All queries already completed in checkpoint!", flush=True)
        return

    csv_exists = os.path.exists(OUTPUT_CSV) and os.path.getsize(OUTPUT_CSV) > 0

    workers = args.workers
    buffer_records = []
    buffer_checkpoint = set(completed_keys)
    total_extracted_records = 0
    total_processed_queries = len(completed_keys)
    initial_completed = len(completed_keys)
    failed_queries = []

    print(f"\nStarting Multithreaded Import Extraction (Workers: {workers})...\n", flush=True)

    max_in_flight = workers * 10
    query_iter = iter(pending_queries)
    futures = {}

    with ThreadPoolExecutor(max_workers=workers) as executor:
        for _ in range(min(max_in_flight, len(pending_queries))):
            try:
                q = next(query_iter)
                f = executor.submit(fetch_single_query, q[0], q[1], q[2])
                futures[f] = q
            except StopIteration:
                break

        while futures:
            done = []
            for f in list(futures.keys()):
                if f.done():
                    done.append(f)

            if not done:
                time.sleep(0.05)
                continue

            for f in done:
                q = futures.pop(f)
                year, month, hs_code, records, err = f.result()
                q_key = f"{year}-{month:02d}_{hs_code}"
                total_processed_queries += 1

                if err:
                    failed_queries.append({"year": year, "month": month, "hs_code": hs_code, "error": err})
                else:
                    buffer_checkpoint.add(q_key)

                if records:
                    date_str = f"{year}-{month:02d}-01"
                    hs_info = dim_hs.get(hs_code, {})

                    for r in records:
                        c_code = str(r.get("country_code", "")).strip().upper()
                        if not c_code:
                            continue

                        qty = float(r.get("quantity", 0) or 0)
                        usd = float(r.get("value_usd", 0) or 0)
                        thb = float(r.get("value_baht", 0) or 0)

                        if qty > 0 or usd > 0 or thb > 0:
                            c_info = dim_country.get(c_code, {})

                            buffer_records.append({
                                "Date": date_str,
                                "year": year,
                                "month": month,
                                "country_code": c_code,
                                "country_name": c_info.get("country_name", ""),
                                "country_name_th": c_info.get("country_name_th", ""),
                                "country_name_en": c_info.get("country_name_en", ""),
                                "iso_region": c_info.get("iso_region", ""),
                                "iso_sub_region": c_info.get("iso_sub_region", ""),
                                "region_cia": c_info.get("region_cia", ""),
                                "hs_11_code": hs_code,
                                "hs_11_description_th": hs_info.get("hs_11_description_th", ""),
                                "hs_11_description_en": hs_info.get("hs_11_description_en", ""),
                                "hs_8_code": hs_info.get("hs_8_code", hs_code[:8]),
                                "hs_8_description_th": hs_info.get("hs_8_description_th", ""),
                                "hs_8_description_en": hs_info.get("hs_8_description_en", ""),
                                "hs_4_code": hs_info.get("hs_4_code", hs_code[:4]),
                                "hs_4_description_th": hs_info.get("hs_4_description_th", ""),
                                "hs_4_description_en": hs_info.get("hs_4_description_en", ""),
                                "hs_2_code": hs_info.get("hs_2_code", hs_code[:2]),
                                "hs_2_description_th": hs_info.get("hs_2_description_th", ""),
                                "hs_2_description_en": hs_info.get("hs_2_description_en", ""),
                                "unit_code": hs_info.get("unit_code", ""),
                                "unit_name": hs_info.get("unit_name", ""),
                                "quantity": qty,
                                "value_usd": usd,
                                "value_baht": thb
                            })

                try:
                    next_q = next(query_iter)
                    new_f = executor.submit(fetch_single_query, next_q[0], next_q[1], next_q[2])
                    futures[new_f] = next_q
                except StopIteration:
                    pass

                if total_processed_queries % 200 == 0:
                    if buffer_records:
                        df_chunk = pd.DataFrame(buffer_records)
                        df_chunk.to_csv(OUTPUT_CSV, mode="a", index=False, header=not csv_exists, encoding="utf-8")
                        csv_exists = True
                        total_extracted_records += len(buffer_records)
                        buffer_records = []

                    save_checkpoint(buffer_checkpoint)

                    pct = (total_processed_queries / len(all_queries)) * 100
                    elapsed = time.time() - start_time
                    speed = (total_processed_queries - initial_completed) / max(elapsed, 0.1)
                    print(f"  Processed {total_processed_queries:,} / {len(all_queries):,} queries ({pct:.1f}%) | Matched Facts: {total_extracted_records:,} | Speed: {speed:.1f} req/s", flush=True)

    if buffer_records:
        df_chunk = pd.DataFrame(buffer_records)
        df_chunk.to_csv(OUTPUT_CSV, mode="a", index=False, header=not csv_exists, encoding="utf-8")
        total_extracted_records += len(buffer_records)
        save_checkpoint(buffer_checkpoint)

    if failed_queries:
        with open(FAILED_QUERIES_FILE, "w", encoding="utf-8") as f:
            json.dump(failed_queries, f, indent=2)
        print(f"⚠️ {len(failed_queries):,} queries logged to {FAILED_QUERIES_FILE} for retry.", flush=True)

    duration = round(time.time() - start_time, 2)
    file_size_mb = os.path.getsize(OUTPUT_CSV) / (1024 * 1024) if os.path.exists(OUTPUT_CSV) else 0

    print("\n" + "=" * 80, flush=True)
    print("🎉 FOOD IMPORT DATASET (07, 08, 20) COMPLETED SUCCESSFULLY!", flush=True)
    print(f"Output File: {OUTPUT_CSV}")
    print(f"Total Enriched Import Facts: {total_extracted_records:,} rows")
    print(f"Output File Size: {file_size_mb:.2f} MB")
    print(f"Total Duration: {duration:.2f}s ({duration/60:.2f} mins)")
    print("=" * 80, flush=True)

if __name__ == "__main__":
    main()
