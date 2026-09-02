import math
import numpy as np
import pandas as pd
from typing import Optional
from config.db_config import get_connection

def load_dim_currency(dim_df: pd.DataFrame, conn=None) -> int:
    """
    Inserts or updates currency dimension records into dim_currency.
    """
    should_close = False
    if conn is None:
        conn = get_connection()
        should_close = True

    cursor = conn.cursor()
    sql = """
        INSERT INTO dim_currency (currency_code, country_name, currency_name, unit_multiplier)
        VALUES (%s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            country_name = VALUES(country_name),
            currency_name = VALUES(currency_name),
            unit_multiplier = VALUES(unit_multiplier);
    """
    records = []
    for _, row in dim_df.iterrows():
        records.append((
            str(row["currency_code"]),
            str(row["country_name"]),
            str(row["currency_name"]),
            int(row["unit_multiplier"])
        ))

    try:
        cursor.executemany(sql, records)
        conn.commit()
        count = len(records)
        print(f"[LOADER] Loaded {count} currency dimension records into dim_currency.")
        return count
    except Exception as e:
        conn.rollback()
        print(f"[LOADER ERROR] Failed to load dim_currency: {e}")
        raise
    finally:
        cursor.close()
        if should_close:
            conn.close()

def load_fact_exchange_rates(fact_df: pd.DataFrame, chunk_size: int = 10000, conn=None) -> int:
    """
    Bulk inserts fact records into fact_daily_exchange_rate using executemany in chunks.
    Ensures NaN values become true SQL NULLs.
    """
    should_close = False
    if conn is None:
        conn = get_connection()
        should_close = True

    cursor = conn.cursor()
    sql = """
        INSERT INTO fact_daily_exchange_rate (
            rate_date, currency_code, buying_sight_bill, buying_transfer, selling
        )
        VALUES (%s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            buying_sight_bill = VALUES(buying_sight_bill),
            buying_transfer = VALUES(buying_transfer),
            selling = VALUES(selling);
    """

    # Helper function to sanitize floats to None if NaN
    def sanitize(val):
        if pd.isna(val) or val is None:
            return None
        return float(val)

    total_rows = len(fact_df)
    total_chunks = math.ceil(total_rows / chunk_size)
    processed = 0

    try:
        for i in range(0, total_rows, chunk_size):
            chunk = fact_df.iloc[i : i + chunk_size]
            records = []
            for _, row in chunk.iterrows():
                records.append((
                    str(row["rate_date"]),
                    str(row["currency_code"]),
                    sanitize(row["buying_sight_bill"]),
                    sanitize(row["buying_transfer"]),
                    sanitize(row["selling"])
                ))
            cursor.executemany(sql, records)
            conn.commit()
            processed += len(records)
            chunk_num = (i // chunk_size) + 1
            print(f"[LOADER] Inserted chunk {chunk_num}/{total_chunks} ({processed:,}/{total_rows:,} rows)...")

        print(f"[LOADER] Successfully ingested {processed:,} exchange rate records into fact_daily_exchange_rate.")
        return processed
    except Exception as e:
        conn.rollback()
        print(f"[LOADER ERROR] Ingestion failed at row {processed}: {e}")
        raise
    finally:
        cursor.close()
        if should_close:
            conn.close()

def calculate_file_hash(file_path: str) -> str:
    """Calculates SHA-256 hash of a file."""
    import hashlib
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha256.update(chunk)
    return sha256.hexdigest()

def log_ingestion(
    dataset_name: str,
    file_or_source: str,
    period_start: Optional[str],
    period_end: Optional[str],
    total_rows: int,
    file_hash: Optional[str] = None,
    status: str = "SUCCESS",
    duration_seconds: Optional[float] = None,
    conn = None
):
    """Records entry into data_ingestion_log."""
    should_close = False
    if conn is None:
        conn = get_connection()
        should_close = True

    sql = """
        INSERT INTO data_ingestion_log (
            dataset_name, file_or_source, period_start, period_end,
            total_rows, file_hash, status, duration_seconds
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
    """
    cursor = conn.cursor()
    try:
        cursor.execute(sql, (
            dataset_name, file_or_source, period_start, period_end,
            total_rows, file_hash, status, duration_seconds
        ))
        conn.commit()
    finally:
        cursor.close()
        if should_close:
            conn.close()
