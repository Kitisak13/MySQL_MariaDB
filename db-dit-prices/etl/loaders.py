import hashlib
import time
from typing import List, Tuple, Optional
import mysql.connector

def calculate_file_hash(file_path: str) -> str:
    """Calculates SHA-256 hash of a file for audit and idempotent change detection."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha256.update(chunk)
    return sha256.hexdigest()

def upsert_dim_products(conn, records: List[Tuple]) -> int:
    """
    Bulk upserts products into `dim_product`.
    Records format: (product_id, product_name, category_name, group_name, unit)
    """
    if not records:
        return 0

    sql = """
        INSERT INTO `dim_product` (
            product_id, product_name, category_name, group_name, unit
        ) VALUES (%s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            product_name = COALESCE(VALUES(product_name), product_name),
            category_name = COALESCE(VALUES(category_name), category_name),
            group_name = COALESCE(VALUES(group_name), group_name),
            unit = COALESCE(VALUES(unit), unit);
    """
    cursor = conn.cursor()
    try:
        cursor.executemany(sql, records)
        conn.commit()
        return len(records)
    finally:
        cursor.close()

def upsert_fact_prices(conn, records: List[Tuple], chunk_size: int = 10000) -> int:
    """
    Bulk upserts price records into `fact_daily_product_price` in chunks.
    Records format: (price_date, product_id, price_min, price_max, price_avg)
    """
    if not records:
        return 0

    sql = """
        INSERT INTO `fact_daily_product_price` (
            price_date, product_id, price_min, price_max, price_avg
        ) VALUES (%s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            price_min = VALUES(price_min),
            price_max = VALUES(price_max),
            price_avg = VALUES(price_avg);
    """
    cursor = conn.cursor()
    total_loaded = 0

    try:
        for i in range(0, len(records), chunk_size):
            batch = records[i : i + chunk_size]
            cursor.executemany(sql, batch)
            conn.commit()
            total_loaded += len(batch)
        return total_loaded
    finally:
        cursor.close()

def log_ingestion(
    conn,
    dataset_name: str,
    file_or_source: str,
    period_start: Optional[str],
    period_end: Optional[str],
    total_rows: int,
    file_hash: Optional[str],
    status: str = "SUCCESS",
    duration_seconds: Optional[float] = None
):
    """Records entry into `data_ingestion_log`."""
    sql = """
        INSERT INTO `data_ingestion_log` (
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
