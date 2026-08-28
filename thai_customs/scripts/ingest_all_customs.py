import os
import sys
import glob
import time
import pandas as pd
from typing import List, Dict

# Reconfigure stdout for UTF-8
sys.stdout.reconfigure(encoding="utf-8")

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config.db_config import get_connection
from etl.loaders import calculate_file_hash, load_dimension_records, ingest_fact_partition
from etl.fact_transformers import (
    transform_country_chunk,
    transform_transport_chunk,
    transform_port_chunk,
    transform_office_chunk
)

DATASET_CONFIGS = [
    # 1. Country Datasets
    {
        "folder": "ctm_06_11_import_country",
        "dataset_id": "ctm_06_11",
        "table": "fact_trade_by_country",
        "trade_type": "IMPORT",
        "transformer": transform_country_chunk,
        "columns": ["period_date", "period_year", "period_month", "trade_type", "country_code", "hs_code", "stat_code", "unit_code", "quantity", "value_thb"]
    },
    {
        "folder": "ctm_06_12_export_country",
        "dataset_id": "ctm_06_12",
        "table": "fact_trade_by_country",
        "trade_type": "EXPORT",
        "transformer": transform_country_chunk,
        "columns": ["period_date", "period_year", "period_month", "trade_type", "country_code", "hs_code", "stat_code", "unit_code", "quantity", "value_thb"]
    },
    # 2. Transport Datasets
    {
        "folder": "ctm_06_17_import_transport",
        "dataset_id": "ctm_06_17",
        "table": "fact_trade_by_transport",
        "trade_type": "IMPORT",
        "transformer": transform_transport_chunk,
        "columns": ["period_date", "period_year", "period_month", "trade_type", "transport_code", "hs_code", "stat_code", "unit_code", "quantity", "value_thb"]
    },
    {
        "folder": "ctm_06_18_export_transport",
        "dataset_id": "ctm_06_18",
        "table": "fact_trade_by_transport",
        "trade_type": "EXPORT",
        "transformer": transform_transport_chunk,
        "columns": ["period_date", "period_year", "period_month", "trade_type", "transport_code", "hs_code", "stat_code", "unit_code", "quantity", "value_thb"]
    },
    # 3. Port Datasets
    {
        "folder": "ctm_06_15_import_port",
        "dataset_id": "ctm_06_15",
        "table": "fact_trade_by_port",
        "trade_type": "IMPORT",
        "transformer": transform_port_chunk,
        "columns": ["period_date", "period_year", "period_month", "trade_type", "port_name", "office_short_name", "hs_code", "stat_code", "unit_code", "quantity", "value_thb"]
    },
    {
        "folder": "ctm_06_16_export_port",
        "dataset_id": "ctm_06_16",
        "table": "fact_trade_by_port",
        "trade_type": "EXPORT",
        "transformer": transform_port_chunk,
        "columns": ["period_date", "period_year", "period_month", "trade_type", "port_name", "office_short_name", "hs_code", "stat_code", "unit_code", "quantity", "value_thb"]
    },
    # 4. Office Datasets
    {
        "folder": "ctm_06_13_import_office",
        "dataset_id": "ctm_06_13",
        "table": "fact_trade_by_office",
        "trade_type": "IMPORT",
        "transformer": transform_office_chunk,
        "columns": ["period_date", "period_year", "period_month", "trade_type", "office_name", "hs_code", "stat_code", "unit_code", "quantity", "value_thb"]
    },
    {
        "folder": "ctm_06_14_export_office",
        "dataset_id": "ctm_06_14",
        "table": "fact_trade_by_office",
        "trade_type": "EXPORT",
        "transformer": transform_office_chunk,
        "columns": ["period_date", "period_year", "period_month", "trade_type", "office_name", "hs_code", "stat_code", "unit_code", "quantity", "value_thb"]
    }
]

def process_file(cfg: dict, csv_file: str, conn):
    """
    Processes a single CSV file in streaming chunks.
    """
    filename = os.path.basename(csv_file)
    fsize_mb = os.path.getsize(csv_file) / (1024 * 1024)
    file_hash = calculate_file_hash(csv_file)
    t0 = time.time()

    # Check if already successfully ingested
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT rows_loaded FROM data_ingestion_log WHERE filename = %s AND file_hash = %s AND status = 'SUCCESS' AND rows_loaded > 0 ORDER BY id DESC LIMIT 1;", (filename, file_hash))
    existing = cursor.fetchone()
    cursor.close()
    if existing:
        print(f"  -> [ALREADY INGESTED] {filename} ({existing['rows_loaded']:,} rows - Skip)")
        return existing['rows_loaded']

    table_name = cfg["table"]
    dataset_id = cfg["dataset_id"]
    trade_type = cfg["trade_type"]
    transformer = cfg["transformer"]
    columns = cfg["columns"]

    all_fact_records = []
    dim_records = set()
    total_val = 0.0
    period_year = None
    period_month = None

    # Read in chunks of 50,000 to maintain minimal memory footprint
    chunksize = 50000
    for chunk in pd.read_csv(csv_file, chunksize=chunksize, low_memory=False, encoding="utf-8"):
        facts, dims, val = transformer(chunk, trade_type)
        all_fact_records.extend(facts)
        for d in dims:
            dim_records.add(d)
        total_val += val

    if not all_fact_records:
        print(f"  -> [SKIP] Empty file: {filename}")
        return 0

    # Detect period from first record
    # format: (period_date, ce_year, month, trade_type, ...)
    sample_rec = all_fact_records[0]
    period_year = sample_rec[1]
    
    # Check if single month or full year
    unique_months = set(r[2] for r in all_fact_records)
    target_month = sample_rec[2] if len(unique_months) == 1 else None

    # Step 1: Upsert Dimensions
    if dataset_id in ("ctm_06_11", "ctm_06_12") and dim_records:
        # HS Dimension
        load_dimension_records("dim_hs_code", list(dim_records), ["hs_code", "stat_code", "unit_code", "desc_th", "desc_en"], ["desc_th", "desc_en"], conn=conn)
    elif dataset_id in ("ctm_06_17", "ctm_06_18") and dim_records:
        load_dimension_records("dim_transport_type", list(dim_records), ["transport_code", "transport_name_th"], ["transport_name_th"], conn=conn)
    elif dataset_id in ("ctm_06_15", "ctm_06_16") and dim_records:
        load_dimension_records("dim_customs_port", list(dim_records), ["port_name", "office_short_name"], ["office_short_name"], conn=conn)
    elif dataset_id in ("ctm_06_13", "ctm_06_14") and dim_records:
        load_dimension_records("dim_customs_office", list(dim_records), ["office_name"], [], conn=conn)

    # Step 2: Atomic Partition Overwrite
    rows_loaded = ingest_fact_partition(
        table_name=table_name,
        dataset_id=dataset_id,
        period_year=period_year,
        period_month=target_month,
        trade_type=trade_type,
        filename=filename,
        file_hash=file_hash,
        records=all_fact_records,
        columns=columns,
        total_value_thb=total_val,
        conn=conn
    )

    elapsed = time.time() - t0
    print(f"  -> [INGESTED] {filename} ({fsize_mb:.1f} MB) -> {rows_loaded:,} rows in {elapsed:.2f}s ({total_val:,.2f} THB)")
    return rows_loaded

def main():
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    raw_dir = os.path.join(base_dir, "raw_data")

    conn = get_connection()
    t_start = time.time()
    total_all_rows = 0

    print("=" * 80)
    print("THAI CUSTOMS TRADE DATA - MASTER HISTORICAL INGESTION PIPELINE")
    print(f"Source Directory: {raw_dir}")
    print("=" * 80)

    try:
        for cfg in DATASET_CONFIGS:
            folder_path = os.path.join(raw_dir, cfg["folder"], "csv")
            csv_files = sorted(glob.glob(os.path.join(folder_path, "*.csv")))
            print(f"\n[{cfg['dataset_id']}] Processing {cfg['folder']} ({len(csv_files)} files)...")

            for csv_file in csv_files:
                rows = process_file(cfg, csv_file, conn)
                total_all_rows += rows

        total_elapsed = time.time() - t_start
        print("\n" + "=" * 80)
        print(f"HISTORICAL INGESTION COMPLETED SUCCESSFULLY!")
        print(f"Total Rows Ingested Across All 8 Datasets: {total_all_rows:,}")
        print(f"Total Time Taken: {total_elapsed:.2f} seconds ({total_elapsed/60:.2f} minutes)")
        print("=" * 80)

    finally:
        conn.close()

if __name__ == "__main__":
    main()
