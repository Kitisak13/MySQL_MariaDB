import os
import sys
from typing import List, Dict, Any, Optional
from datetime import date

# Add parent path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from config.db_config import get_connection

def ensure_countries_exist(cursor, records: List[Dict[str, Any]]):
    """Ensures all foreign-key country codes exist in dim_country to prevent FK constraint failures."""
    unique_countries = {}
    for r in records:
        cc = r["country_code"]
        if cc not in unique_countries:
            unique_countries[cc] = {
                "name_th": r.get("country_name_th") or cc,
                "name_en": r.get("country_name_en") or cc
            }

    if not unique_countries:
        return

    country_insert_sql = """
        INSERT INTO dim_country (country_code, country_name, country_name_th, country_name_en)
        VALUES (%s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE country_code = country_code;
    """
    country_tuples = [
        (cc, info["name_en"] or cc, info["name_th"] or cc, info["name_en"] or cc)
        for cc, info in unique_countries.items()
    ]
    cursor.executemany(country_insert_sql, country_tuples)

def bulk_upsert_fact_food_export(records: List[Dict[str, Any]], conn=None) -> int:
    """
    Bulk upserts transformed records into `fact_food_export` with idempotency.
    """
    if not records:
        return 0

    should_close = False
    if conn is None:
        conn = get_connection()
        should_close = True

    cursor = conn.cursor()

    try:
        # 1. Ensure foreign key countries exist
        ensure_countries_exist(cursor, records)

        # 2. Bulk upsert facts
        sql = """
            INSERT INTO fact_food_export (
                export_date, export_year, export_month, country_code, hs_11_code,
                quantity, acc_quantity, value_usd, acc_value_usd, value_thb, acc_value_thb, unit_code
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                quantity = VALUES(quantity),
                acc_quantity = VALUES(acc_quantity),
                value_usd = VALUES(value_usd),
                acc_value_usd = VALUES(acc_value_usd),
                value_thb = VALUES(value_thb),
                acc_value_thb = VALUES(acc_value_thb),
                unit_code = VALUES(unit_code);
        """

        tuples = [
            (
                r["export_date"],
                int(r["export_year"]),
                int(r["export_month"]),
                str(r["country_code"]),
                str(r["hs_11_code"]),
                r["quantity"],
                r["acc_quantity"],
                r["value_usd"],
                r["acc_value_usd"],
                r["value_thb"],
                r["acc_value_thb"],
                r["unit_code"]
            )
            for r in records
        ]

        chunk_size = 2000
        for i in range(0, len(tuples), chunk_size):
            chunk = tuples[i:i+chunk_size]
            cursor.executemany(sql, chunk)

        conn.commit()
        return len(records)

    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cursor.close()
        if should_close:
            conn.close()

def log_ingestion(dataset_name: str, file_or_source: str, period_start: Optional[date],
                  period_end: Optional[date], total_rows: int, status: str, duration_seconds: float):
    """Records audit trail in data_ingestion_log."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        sql = """
            INSERT INTO data_ingestion_log (
                dataset_name, file_or_source, period_start, period_end,
                total_rows, file_hash, status, duration_seconds
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
        """
        cursor.execute(sql, (
            dataset_name,
            file_or_source,
            period_start,
            period_end,
            total_rows,
            None,
            status,
            round(duration_seconds, 2)
        ))
        conn.commit()
    finally:
        cursor.close()
        conn.close()
