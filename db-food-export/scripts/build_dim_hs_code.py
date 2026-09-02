import os
import sys
import time
import requests
import pandas as pd
from typing import Dict, Any, List

# Ensure UTF-8
sys.stdout.reconfigure(encoding="utf-8")

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config.db_config import get_connection

BASE_URL = "https://tradereport.moc.go.th/api/harmonizestructure"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*"
}
REVISIONS = [2007, 2012, 2017, 2022]

def clean_text(val) -> str:
    """Strips whitespace and nullifies empty strings."""
    if val is None or pd.isna(val):
        return None
    s = str(val).strip()
    return s if s else None

def fetch_structure_level(digits: int) -> Dict[str, Dict[str, str]]:
    """
    Fetches codes and descriptions for a given digit level (2, 4, 8) across all revisions.
    Prioritizes newer revisions (2022 > 2017 > 2012 > 2007).
    """
    print(f"\n[1/3] Fetching description catalog for Digits={digits} across revisions {REVISIONS}...")
    desc_map = {} # code -> {'th': ..., 'en': ...}

    for rev in REVISIONS:
        try:
            r = requests.get(BASE_URL, params={"revision": rev, "digits": digits, "limit": 0}, headers=HEADERS, timeout=40)
            if r.status_code == 200:
                data = r.json()
                for item in data:
                    code = str(item.get("hs_code", "")).strip().zfill(digits)
                    th_desc = clean_text(item.get("hs_description_th"))
                    en_desc = clean_text(item.get("hs_description_en"))

                    if code:
                        if code not in desc_map:
                            desc_map[code] = {"th": th_desc, "en": en_desc}
                        else:
                            # Update with newer revision description if available
                            if th_desc:
                                desc_map[code]["th"] = th_desc
                            if en_desc:
                                desc_map[code]["en"] = en_desc
                print(f"  -> Revision {rev}: Processed {len(data):,} entries.")
            else:
                print(f"  -> [Warning] Revision {rev} returned HTTP {r.status_code}")
        except Exception as e:
            print(f"  -> [Error] Revision {rev} error: {e}")

    print(f"  Total unique codes mapped for Digits={digits}: {len(desc_map):,}")
    return desc_map

def fetch_all_hs11_codes() -> pd.DataFrame:
    """
    Fetches all 11-digit HS codes across all 4 revisions and aggregates metadata.
    """
    print(f"\n[2/3] Fetching all 11-digit HS statistical codes across revisions {REVISIONS}...")
    all_records = []
    active_2022_codes = set()

    for rev in REVISIONS:
        try:
            r = requests.get(BASE_URL, params={"revision": rev, "digits": 11, "limit": 0}, headers=HEADERS, timeout=60)
            if r.status_code == 200:
                data = r.json()
                print(f"  -> Revision {rev}: Retrieved {len(data):,} items.")
                for item in data:
                    code = str(item.get("hs_code", "")).strip().zfill(11)
                    if code:
                        if rev == 2022:
                            active_2022_codes.add(code)

                        all_records.append({
                            "revision": rev,
                            "hs_code": code,
                            "parent_hs_code": str(item.get("parent_hs_code", "")).strip() if item.get("parent_hs_code") else code[:8],
                            "hs_description_th": clean_text(item.get("hs_description_th")),
                            "hs_description_en": clean_text(item.get("hs_description_en")),
                            "unit_code": clean_text(item.get("unit_code")),
                            "unit_name": clean_text(item.get("unit"))
                        })
            else:
                print(f"  -> [Warning] Revision {rev} returned HTTP {r.status_code}")
        except Exception as e:
            print(f"  -> [Error] Revision {rev} error: {e}")

    raw_df = pd.DataFrame(all_records)
    print(f"Total raw 11-digit records collected: {len(raw_df):,}")

    # Deduplicate & consolidate metadata per hs_code
    print("Consolidating unique 11-digit codes across revisions...")
    consolidated = []
    grouped = raw_df.groupby("hs_code")

    for hs_code, group in grouped:
        first_rev = int(group["revision"].min())
        latest_rev = int(group["revision"].max())
        is_active = 1 if hs_code in active_2022_codes else 0

        # Sort by revision descending to pick latest description
        sorted_group = group.sort_values(by="revision", ascending=False)
        latest_row = sorted_group.iloc[0]

        th_desc = None
        en_desc = None
        unit_code = None
        unit_name = None

        for _, r in sorted_group.iterrows():
            if not th_desc and pd.notna(r["hs_description_th"]):
                th_desc = r["hs_description_th"]
            if not en_desc and pd.notna(r["hs_description_en"]):
                en_desc = r["hs_description_en"]
            if not unit_code and pd.notna(r["unit_code"]):
                unit_code = r["unit_code"]
            if not unit_name and pd.notna(r["unit_name"]):
                unit_name = r["unit_name"]

        parent_code = str(latest_row["parent_hs_code"]).zfill(8) if latest_row["parent_hs_code"] else hs_code[:8]

        consolidated.append({
            "hs_11_code": hs_code,
            "hs_11_description_th": th_desc,
            "hs_11_description_en": en_desc,
            "hs_8_code": parent_code[:8],
            "hs_4_code": hs_code[:4],
            "hs_2_code": hs_code[:2],
            "unit_code": unit_code,
            "unit_name": unit_name,
            "first_seen_revision": first_rev,
            "latest_revision": latest_rev,
            "is_active_2022": is_active
        })

    final_df = pd.DataFrame(consolidated)
    print(f"Consolidated into {len(final_df):,} unique 11-digit HS codes.")
    return final_df

def build_and_load_dim_hs_code():
    start_time = time.time()
    print("=" * 80)
    print("MOC TRADE REPORT - BUILDING MASTER DIMENSION TABLE (`dim_hs11_code`)")
    print("=" * 80)

    master_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "master_data"))
    os.makedirs(master_dir, exist_ok=True)
    csv_path = os.path.join(master_dir, "dim_hs11_code_master.csv")

    if os.path.exists(csv_path) and os.path.getsize(csv_path) > 0:
        print(f"\nFound existing consolidated master dataset at: {csv_path}")
        print("Loading directly into memory...")
        dim_df = pd.read_csv(csv_path, dtype={"hs_11_code": str, "hs_8_code": str, "hs_4_code": str, "hs_2_code": str})
        dim_df["hs_11_code"] = dim_df["hs_11_code"].astype(str).str.zfill(11)
        dim_df["hs_8_code"] = dim_df["hs_8_code"].astype(str).str.zfill(8)
        dim_df["hs_4_code"] = dim_df["hs_4_code"].astype(str).str.zfill(4)
        dim_df["hs_2_code"] = dim_df["hs_2_code"].astype(str).str.zfill(2)
    else:
        # 1. Fetch description catalogs for 2, 4, 8 digits
        hs2_map = fetch_structure_level(digits=2)
        hs4_map = fetch_structure_level(digits=4)
        hs8_map = fetch_structure_level(digits=8)

        # 2. Fetch and consolidate 11-digit records
        dim_df = fetch_all_hs11_codes()

        # 3. Enrich with descriptions at levels 2, 4, 8
        print("\n[3/3] Enriching 11-digit records with 2, 4, and 8-digit Thai/English descriptions...")
        dim_df["hs_2_description_th"] = dim_df["hs_2_code"].map(lambda c: hs2_map.get(c, {}).get("th"))
        dim_df["hs_2_description_en"] = dim_df["hs_2_code"].map(lambda c: hs2_map.get(c, {}).get("en"))

        dim_df["hs_4_description_th"] = dim_df["hs_4_code"].map(lambda c: hs4_map.get(c, {}).get("th"))
        dim_df["hs_4_description_en"] = dim_df["hs_4_code"].map(lambda c: hs4_map.get(c, {}).get("en"))

        dim_df["hs_8_description_th"] = dim_df["hs_8_code"].map(lambda c: hs8_map.get(c, {}).get("th"))
        dim_df["hs_8_description_en"] = dim_df["hs_8_code"].map(lambda c: hs8_map.get(c, {}).get("en"))

        dim_df.to_csv(csv_path, index=False, encoding="utf-8-sig")
        print(f"Saved master dimension backup CSV to: {csv_path}")

    # 4. Ingest into MariaDB `food_export.dim_hs11_code`
    print("\nConnecting to MariaDB `food_export` to upsert records...")
    conn = get_connection()
    cursor = conn.cursor()

    sql = """
        INSERT INTO dim_hs11_code (
            hs_11_code, hs_11_description_th, hs_11_description_en,
            hs_8_code, hs_8_description_th, hs_8_description_en,
            hs_4_code, hs_4_description_th, hs_4_description_en,
            hs_2_code, hs_2_description_th, hs_2_description_en,
            unit_code, unit_name, first_seen_revision, latest_revision, is_active_2022
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            hs_11_description_th = VALUES(hs_11_description_th),
            hs_11_description_en = VALUES(hs_11_description_en),
            hs_8_code = VALUES(hs_8_code),
            hs_8_description_th = VALUES(hs_8_description_th),
            hs_8_description_en = VALUES(hs_8_description_en),
            hs_4_code = VALUES(hs_4_code),
            hs_4_description_th = VALUES(hs_4_description_th),
            hs_4_description_en = VALUES(hs_4_description_en),
            hs_2_code = VALUES(hs_2_code),
            hs_2_description_th = VALUES(hs_2_description_th),
            hs_2_description_en = VALUES(hs_2_description_en),
            unit_code = VALUES(unit_code),
            unit_name = VALUES(unit_name),
            first_seen_revision = VALUES(first_seen_revision),
            latest_revision = VALUES(latest_revision),
            is_active_2022 = VALUES(is_active_2022);
    """

    records = []
    for _, r in dim_df.iterrows():
        records.append((
            str(r["hs_11_code"]),
            clean_text(r["hs_11_description_th"]),
            clean_text(r["hs_11_description_en"]),
            str(r["hs_8_code"]),
            clean_text(r["hs_8_description_th"]),
            clean_text(r["hs_8_description_en"]),
            str(r["hs_4_code"]),
            clean_text(r["hs_4_description_th"]),
            clean_text(r["hs_4_description_en"]),
            str(r["hs_2_code"]),
            clean_text(r["hs_2_description_th"]),
            clean_text(r["hs_2_description_en"]),
            clean_text(r["unit_code"]),
            clean_text(r["unit_name"]),
            int(r["first_seen_revision"]),
            int(r["latest_revision"]),
            int(r["is_active_2022"])
        ))

    chunk_size = 100
    total_loaded = 0
    for i in range(0, len(records), chunk_size):
        chunk = records[i:i+chunk_size]
        cursor.executemany(sql, chunk)
        conn.commit()
        total_loaded += len(chunk)
        if total_loaded % 2500 == 0 or total_loaded == len(records):
            print(f"  -> Upserted {total_loaded:,} / {len(records):,} records into `dim_hs11_code`...")

    duration = round(time.time() - start_time, 2)

    # Ingest into data_ingestion_log
    cursor.execute("""
        INSERT INTO data_ingestion_log (
            dataset_name, file_or_source, period_start, period_end,
            total_rows, file_hash, status, duration_seconds
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
    """, (
        "dim_hs11_code_sync",
        "MOC_API_harmonizestructure_all_revisions",
        None, None,
        total_loaded,
        None,
        "SUCCESS",
        duration
    ))
    conn.commit()

    cursor.close()
    conn.close()

    print("\n" + "=" * 80)
    print("MASTER DIMENSION `dim_hs11_code` BUILT & LOADED SUCCESSFULLY!")
    print(f"Total Unique 11-Digit HS Codes : {total_loaded:,}")
    print(f"Active in 2022 Revision         : {dim_df['is_active_2022'].sum():,}")
    print(f"Historical / Discontinued Codes : {(dim_df['is_active_2022'] == 0).sum():,}")
    print(f"Total Processing Time           : {duration:.2f} seconds ({duration/60:.2f} mins)")
    print("=" * 80)

if __name__ == "__main__":
    build_and_load_dim_hs_code()
