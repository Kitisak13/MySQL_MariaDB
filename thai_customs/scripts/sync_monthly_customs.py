import os
import sys
import time
import requests
import pandas as pd
from datetime import datetime
from typing import Dict, List

# Reconfigure stdout for UTF-8
sys.stdout.reconfigure(encoding="utf-8")

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config.db_config import get_connection
from scripts.download_customs_data import DATASETS, get_resilient_session, sanitize_filename, download_file
from scripts.ingest_all_customs import DATASET_CONFIGS, process_file

def get_logged_hashes(conn) -> Dict[str, str]:
    """Retrieves existing file hashes and statuses from data_ingestion_log."""
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT filename, file_hash, MAX(ingested_at) 
        FROM data_ingestion_log 
        WHERE status = 'SUCCESS'
        GROUP BY filename, file_hash;
    """)
    rows = cursor.fetchall()
    cursor.close()
    return {r["filename"]: r["file_hash"] for r in rows}

def sync_customs_data(rolling_years: int = 2):
    """
    Automated Rolling-Window Synchronization:
    1. Checks CKAN API for updated files in the past N years.
    2. Downloads updated/new files.
    3. Re-ingests modified partitions using Atomic Overwrite.
    """
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    raw_dir = os.path.join(base_dir, "raw_data")
    session = get_resilient_session()
    conn = get_connection()

    current_year_be = datetime.now().year + 543
    min_year_be = current_year_be - rolling_years

    print("=" * 80)
    print(f"THAI CUSTOMS ROLLING {rolling_years}-YEAR RESTOCK & RESTATEMENT SYNC")
    print(f"Active Monitoring Window: BE {min_year_be} - {current_year_be} (CE {min_year_be-543} - {current_year_be-543})")
    print("=" * 80)

    cfg_map = {cfg["dataset_id"]: cfg for cfg in DATASET_CONFIGS}
    total_updated_files = 0
    total_updated_rows = 0

    try:
        logged_hashes = get_logged_hashes(conn)

        for ds in DATASETS:
            ds_id = ds["id"]
            ds_title = ds["name_th"]
            cfg = cfg_map.get(ds_id)
            if not cfg:
                continue

            csv_dir = os.path.join(raw_dir, ds["folder"], "csv")
            os.makedirs(csv_dir, exist_ok=True)

            print(f"\n[CHECKING] {ds_id} - {ds_title}...")
            api_url = f"https://catalog.customs.go.th/api/3/action/package_show?id={ds_id}"
            try:
                resp = session.get(api_url, timeout=15)
                resources = resp.json().get("result", {}).get("resources", [])
            except Exception as e:
                print(f"  [ERROR] Failed to query CKAN API for {ds_id}: {e}")
                continue

            for r in resources:
                name = r.get("name", "").strip()
                fmt = r.get("format", "").upper().strip()
                url = r.get("url", "").strip()

                if fmt != "CSV" and not url.lower().endswith(".csv"):
                    continue

                # Filter by rolling years window if year in title
                is_in_window = False
                for y in range(min_year_be, current_year_be + 2):
                    if str(y) in name or str(y)[-2:] in name:
                        is_in_window = True
                        break
                
                # If cannot determine year from name, include it
                if not is_in_window:
                    continue

                clean_name = sanitize_filename(name)
                if not clean_name.lower().endswith(".csv"):
                    clean_name += ".csv"
                file_path = os.path.join(csv_dir, clean_name)

                # Download file if modified
                if download_file(session, url, file_path, name):
                    # Check if newly downloaded / modified
                    from etl.loaders import calculate_file_hash
                    current_hash = calculate_file_hash(file_path)
                    
                    if logged_hashes.get(clean_name) != current_hash:
                        print(f"  -> [RESTATEMENT DETECTED] Ingesting updated partition: {clean_name}")
                        rows = process_file(cfg, file_path, conn)
                        total_updated_files += 1
                        total_updated_rows += rows
                    else:
                        print(f"  -> [UP-TO-DATE] No data change detected: {clean_name}")

        print("\n" + "=" * 80)
        print("SYNC & RESTATEMENT COMPLETED!")
        print(f"Total Updated Partitions/Files: {total_updated_files}")
        print(f"Total Refreshed Rows: {total_updated_rows:,}")
        print("=" * 80)

    finally:
        conn.close()

if __name__ == "__main__":
    sync_customs_data(rolling_years=2)
