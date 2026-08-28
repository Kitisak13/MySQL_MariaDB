import os
import sys
import re
import pandas as pd
import numpy as np

# Reconfigure stdout for UTF-8
sys.stdout.reconfigure(encoding="utf-8")

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config.db_config import get_connection
from etl.normalizers import clean_text

def pad_code(val, length):
    if pd.isna(val) or val is None:
        return "0" * length
    s = re.sub(r"\D", "", str(val).split(".")[0])
    return s.zfill(length)[:length]

def load_dim_hs_code():
    csv_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "raw_data", "Dim_HS Code.csv"))
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"File not found: {csv_path}")

    print(f"Reading Multi-Level HS Code Master from: {csv_path}")
    df = pd.read_csv(csv_path, encoding="utf-8")
    print(f"Total rows in Dim_HS Code.csv: {len(df):,}")

    conn = get_connection()
    cursor = conn.cursor()

    try:
        # Step 1: Drop & Recreate dim_hs_code with comprehensive 4-level hierarchy
        print("Recreating `dim_hs_code` table structure...")
        cursor.execute("DROP TABLE IF EXISTS `dim_hs_code`;")
        cursor.execute("""
            CREATE TABLE `dim_hs_code` (
                `hs_11_code` CHAR(11) NOT NULL COMMENT 'Level 4: 11-digit Full Tariff Line (hs_8 + stat_code)',
                `hs_8_code` CHAR(8) NOT NULL COMMENT 'Level 3: 8-digit Harmonized System Sub-heading',
                `stat_code` CHAR(3) NOT NULL DEFAULT '000' COMMENT 'Statistical Code',
                `hs_4_code` CHAR(4) NOT NULL COMMENT 'Level 2: 4-digit HS Heading',
                `hs_2_code` CHAR(2) NOT NULL COMMENT 'Level 1: 2-digit HS Chapter',
                `desc_11_th` VARCHAR(500) NULL COMMENT 'Commodity Description 11-digit (Thai)',
                `desc_11_en` VARCHAR(500) NULL COMMENT 'Commodity Description 11-digit (English)',
                `desc_8_th` VARCHAR(500) NULL COMMENT 'Commodity Description 8-digit (Thai)',
                `desc_8_en` VARCHAR(500) NULL COMMENT 'Commodity Description 8-digit (English)',
                `desc_4_en` VARCHAR(500) NULL COMMENT 'Group Description 4-digit Heading (English)',
                `desc_2_en` VARCHAR(500) NULL COMMENT 'Broad Category 2-digit Chapter (English)',
                `unit_code` VARCHAR(10) NULL COMMENT 'Statistical Measurement Unit (e.g. KGM, C62, TNE)',
                `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                PRIMARY KEY (`hs_11_code`),
                INDEX `idx_hs8` (`hs_8_code`),
                INDEX `idx_hs4` (`hs_4_code`),
                INDEX `idx_hs2` (`hs_2_code`),
                INDEX `idx_hs8_stat` (`hs_8_code`, `stat_code`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Dimension: 4-Level HS Code & Statistical Commodity Hierarchy (2, 4, 8, 11 Digits)';
        """)

        # Step 2: Prepare records from CSV
        records = []
        seen_11 = set()

        for _, row in df.iterrows():
            hs11 = pad_code(row.get("HS_11 Digit"), 11)
            hs8 = pad_code(row.get("HS_8 Digit"), 8)
            hs4 = pad_code(row.get("HS_4 Digit"), 4)
            hs2 = pad_code(row.get("HS_2 Digit"), 2)
            stat = hs11[8:11] if len(hs11) == 11 else "000"

            if hs11 in seen_11:
                continue
            seen_11.add(hs11)

            desc_11_en = clean_text(row.get("HS 11 Digit EN_Des"), max_len=500)
            desc_11_th = clean_text(row.get("HS 11 Digit TH_Des"), max_len=500)
            desc_8_th = clean_text(row.get("HS 8 Digit TH_Des"), max_len=500)
            desc_8_en = clean_text(row.get("HS 8 Digit EN_Des"), max_len=500)
            desc_4_en = clean_text(row.get("HS 4 Digit EN_Des"), max_len=500)
            desc_2_en = clean_text(row.get("HS 2 Digit EN_Des"), max_len=500)

            records.append((
                hs11, hs8, stat, hs4, hs2,
                desc_11_th, desc_11_en, desc_8_th, desc_8_en, desc_4_en, desc_2_en, None
            ))

        # Step 3: Check distinct hs_code & stat_code from fact tables to backfill any missing items
        print("Checking for existing commodities across fact tables to ensure 100% coverage...")
        cursor.execute("""
            SELECT DISTINCT hs_code, stat_code, unit_code 
            FROM fact_trade_by_country;
        """)
        fact_commodities = cursor.fetchall()
        print(f"Total distinct (hs_code, stat_code) in fact_trade_by_country: {len(fact_commodities):,}")

        backfill_count = 0
        for r in fact_commodities:
            hs8 = pad_code(r[0], 8)
            stat = pad_code(r[1], 3)
            unit = clean_text(r[2], max_len=10)
            hs11 = hs8 + stat
            hs4 = hs8[:4]
            hs2 = hs8[:2]

            if hs11 not in seen_11:
                seen_11.add(hs11)
                records.append((
                    hs11, hs8, stat, hs4, hs2,
                    None, None, None, None, None, None, unit
                ))
                backfill_count += 1

        print(f"Backfilled {backfill_count} additional commodity codes from fact tables.")

        # Step 4: Bulk Insert into dim_hs_code
        print(f"Inserting total {len(records):,} records into `dim_hs_code`...")
        insert_sql = """
            INSERT INTO `dim_hs_code` (
                hs_11_code, hs_8_code, stat_code, hs_4_code, hs_2_code,
                desc_11_th, desc_11_en, desc_8_th, desc_8_en, desc_4_en, desc_2_en, unit_code
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                desc_11_th = COALESCE(VALUES(desc_11_th), desc_11_th),
                desc_11_en = COALESCE(VALUES(desc_11_en), desc_11_en),
                desc_8_th = COALESCE(VALUES(desc_8_th), desc_8_th),
                desc_8_en = COALESCE(VALUES(desc_8_en), desc_8_en),
                desc_4_en = COALESCE(VALUES(desc_4_en), desc_4_en),
                desc_2_en = COALESCE(VALUES(desc_2_en), desc_2_en),
                unit_code = COALESCE(VALUES(unit_code), unit_code);
        """

        chunk_size = 2000
        for i in range(0, len(records), chunk_size):
            batch = records[i : i + chunk_size]
            cursor.executemany(insert_sql, batch)

        conn.commit()
        print(f"Successfully loaded {len(records):,} multi-level HS Code records into `dim_hs_code`!")

        # Step 5: Verification
        cursor.execute("SELECT hs_11_code, hs_8_code, hs_4_code, hs_2_code, desc_11_th, desc_2_en FROM dim_hs_code ORDER BY hs_11_code LIMIT 5;")
        sample_rows = cursor.fetchall()
        df_sample = pd.DataFrame(sample_rows, columns=["hs_11_code", "hs_8_code", "hs_4_code", "hs_2_code", "desc_11_th", "desc_2_en"])
        print("\nSample records in upgraded dim_hs_code:")
        print(df_sample.to_string(index=False))

    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    load_dim_hs_code()
