import os
import sys
import time
import pandas as pd

# Ensure UTF-8 output
sys.stdout.reconfigure(encoding="utf-8")

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config.db_config import get_connection

def sync_country_dimension():
    start_time = time.time()
    print("=" * 80)
    print("SYNCHRONIZING `dim_country` FROM `thai_customs` DATABASE")
    print("=" * 80)

    conn = get_connection(include_db=False)
    cursor = conn.cursor()

    # 1. Perform atomic Cross-Database INSERT / UPDATE
    print("\n[1/3] Executing Atomic Cross-Database Synchronization (thai_customs -> food_export)...")
    sync_sql = """
        INSERT INTO food_export.dim_country
        SELECT * FROM thai_customs.dim_country
        ON DUPLICATE KEY UPDATE
            country_name = VALUES(country_name),
            country_name_th = VALUES(country_name_th),
            country_name_en = VALUES(country_name_en),
            country_name_cia = VALUES(country_name_cia),
            region_cia = VALUES(region_cia),
            iso_region = VALUES(iso_region),
            iso_sub_region = VALUES(iso_sub_region),
            iso_intermediate_region = VALUES(iso_intermediate_region),
            iso_3166_2 = VALUES(iso_3166_2);
    """
    cursor.execute(sync_sql)
    conn.commit()
    print("  -> Cross-Database Sync Complete!")

    # 2. Verify and Export Master Backup CSV
    print("\n[2/3] Exporting Standalone Master Data CSV...")
    cursor.execute("SELECT * FROM food_export.dim_country ORDER BY country_code;")
    cols = [desc[0] for desc in cursor.description]
    rows = cursor.fetchall()
    df_country = pd.DataFrame(rows, columns=cols)

    master_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "master_data"))
    os.makedirs(master_dir, exist_ok=True)
    csv_path = os.path.join(master_dir, "dim_country_master.csv")
    df_country.to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"  -> Saved master country CSV to: {csv_path} ({len(df_country)} countries)")

    # 3. Log Ingestion
    print("\n[3/3] Recording audit log into `data_ingestion_log`...")
    duration = round(time.time() - start_time, 2)
    cursor.execute("""
        INSERT INTO food_export.data_ingestion_log (
            dataset_name, file_or_source, period_start, period_end,
            total_rows, file_hash, status, duration_seconds
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
    """, (
        "dim_country_cross_sync",
        "thai_customs.dim_country",
        None, None,
        len(df_country),
        None,
        "SUCCESS",
        duration
    ))
    conn.commit()

    cursor.close()
    conn.close()

    print("\n" + "=" * 80)
    print(f"COUNTRY DIMENSION `dim_country` SYNCHRONIZED SUCCESSFULLY ({len(df_country)} COUNTRIES)!")
    print(f"Execution Duration: {duration:.2f} seconds")
    print("=" * 80)

if __name__ == "__main__":
    sync_country_dimension()
