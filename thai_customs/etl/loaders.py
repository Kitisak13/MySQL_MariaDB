import math
import hashlib
import time
import pandas as pd
import numpy as np
from typing import List, Dict, Tuple, Optional
from config.db_config import get_connection

def calculate_file_hash(filepath: str) -> str:
    """Calculates MD5 hash of a file for change detection & audit logging."""
    hasher = hashlib.md5()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()

def load_dimension_records(table_name: str, records: List[tuple], columns: List[str], update_cols: List[str], conn=None) -> int:
    """
    Upserts dimension records using ON DUPLICATE KEY UPDATE.
    """
    if not records:
        return 0
    should_close = False
    if conn is None:
        conn = get_connection()
        should_close = True

    cursor = conn.cursor()
    col_str = ", ".join([f"`{c}`" for c in columns])
    val_placeholders = ", ".join(["%s"] * len(columns))
    
    if update_cols:
        update_str = ", ".join([f"`{c}` = VALUES(`{c}`)" for c in update_cols])
        sql = f"INSERT INTO `{table_name}` ({col_str}) VALUES ({val_placeholders}) ON DUPLICATE KEY UPDATE {update_str};"
    else:
        sql = f"INSERT IGNORE INTO `{table_name}` ({col_str}) VALUES ({val_placeholders});"

    batch_size = 2000
    total_recs = len(records)
    try:
        for i in range(0, total_recs, batch_size):
            batch = records[i : i + batch_size]
            cursor.executemany(sql, batch)
        conn.commit()
        return total_recs
    except Exception as e:
        conn.rollback()
        print(f"[ERROR] Failed to load dimension {table_name}: {e}")
        raise
    finally:
        cursor.close()
        if should_close:
            conn.close()

def ingest_fact_partition(
    table_name: str,
    dataset_id: str,
    period_year: int,
    period_month: Optional[int],
    trade_type: str,
    filename: str,
    file_hash: str,
    records: List[tuple],
    columns: List[str],
    total_value_thb: float,
    conn=None
) -> int:
    """
    Atomic Partition Overwrite:
    1. Deletes the existing partition (Year, Month, Trade Flow) to remove ghost/cancelled rows.
    2. Bulk inserts the latest refreshed data.
    3. Records ingestion audit log.
    All executed within a single transaction.
    """
    should_close = False
    if conn is None:
        conn = get_connection()
        should_close = True

    cursor = conn.cursor()
    
    col_str = ", ".join([f"`{c}`" for c in columns])
    val_placeholders = ", ".join(["%s"] * len(columns))
    insert_sql = f"INSERT INTO `{table_name}` ({col_str}) VALUES ({val_placeholders})"

    try:
        # Step 1: Atomic Delete for the target partition
        if period_month is not None:
            delete_sql = f"DELETE FROM `{table_name}` WHERE `period_year` = %s AND `period_month` = %s AND `trade_type` = %s;"
            cursor.execute(delete_sql, (period_year, period_month, trade_type))
        else:
            # Delete month by month (1 to 12) to keep lock buffer small
            for m in range(1, 13):
                delete_sql = f"DELETE FROM `{table_name}` WHERE `period_year` = %s AND `period_month` = %s AND `trade_type` = %s;"
                cursor.execute(delete_sql, (period_year, m, trade_type))
            
        deleted_count = cursor.rowcount

        # Step 2: High-throughput Bulk Insert in chunks of 15,000
        chunk_size = 15000
        total_rows = len(records)
        for i in range(0, total_rows, chunk_size):
            chunk = records[i : i + chunk_size]
            cursor.executemany(insert_sql, chunk)

        # Step 3: Record Ingestion Audit Log
        log_sql = """
            INSERT INTO `data_ingestion_log` (
                dataset_id, period_year, period_month, trade_type, filename, file_hash, rows_loaded, total_value_thb, status
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'SUCCESS');
        """
        cursor.execute(log_sql, (
            dataset_id, period_year, period_month, trade_type, filename, file_hash, total_rows, total_value_thb
        ))

        conn.commit()
        return total_rows
    except Exception as e:
        conn.rollback()
        print(f"[FATAL INGESTION ERROR] Failed on {table_name} ({filename}): {e}")
        # Log failure
        try:
            cursor.execute("""
                INSERT INTO `data_ingestion_log` (
                    dataset_id, period_year, period_month, trade_type, filename, file_hash, rows_loaded, total_value_thb, status, message
                ) VALUES (%s, %s, %s, %s, %s, %s, 0, 0, 'FAILED', %s);
            """, (dataset_id, period_year, period_month, trade_type, filename, file_hash, str(e)[:500]))
            conn.commit()
        except Exception:
            pass
        raise
    finally:
        cursor.close()
        if should_close:
            conn.close()
