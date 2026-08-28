import os
import sys
import pandas as pd
import numpy as np

# Reconfigure stdout for UTF-8
sys.stdout.reconfigure(encoding="utf-8")

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config.db_config import get_connection
from etl.normalizers import clean_text

def clean_val(v):
    if pd.isna(v) or v is None:
        return None
    s = str(v).strip()
    return s if s and s.lower() not in ("nan", "none", "null") else None

def load_dim_country():
    excel_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "raw_data", "Dim_COUNTRY_REGION_CIA.xlsx"))
    if not os.path.exists(excel_path):
        raise FileNotFoundError(f"File not found: {excel_path}")

    print(f"Reading Country Master from: {excel_path}")
    df = pd.read_excel(excel_path, sheet_name="Dim_Country")
    print(f"Total rows in Excel sheet: {len(df)}")

    # Prepare connection
    conn = get_connection()
    cursor = conn.cursor()

    try:
        # Step 1: Ensure dim_country schema has all enriched columns
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS `dim_country` (
                `country_code` VARCHAR(10) NOT NULL COMMENT 'ISO 2-letter Alpha-2 Country Code (e.g. US, CN, JP)',
                `alpha_3` VARCHAR(10) NULL COMMENT 'ISO 3-letter Alpha-3 Code (e.g. USA, CHN, JPN)',
                `numeric_code` INT NULL COMMENT 'Numeric Country Code (e.g. 840, 156, 392)',
                `country_name` VARCHAR(150) NOT NULL COMMENT 'Standard Country Name (ISO 3166)',
                `country_name_cia` VARCHAR(150) NULL COMMENT 'Country Name (CIA)',
                `region_cia` VARCHAR(100) NULL COMMENT 'Region Code (CIA, e.g. ASEAN, OTHER ASIA, EUROPE)',
                `iso_region` VARCHAR(100) NULL COMMENT 'ISO Region (e.g. Asia, Europe, Americas, Africa, Oceania)',
                `iso_sub_region` VARCHAR(100) NULL COMMENT 'ISO Sub Region (e.g. South-eastern Asia, Eastern Asia)',
                `iso_intermediate_region` VARCHAR(100) NULL COMMENT 'ISO Intermediate Region',
                `iso_3166_2` VARCHAR(50) NULL COMMENT 'ISO 3166-2 Reference Code',
                `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                PRIMARY KEY (`country_code`),
                INDEX `idx_alpha3` (`alpha_3`),
                INDEX `idx_iso_region` (`iso_region`),
                INDEX `idx_region_cia` (`region_cia`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Dimension: Comprehensive Country, CIA and ISO Regional Hierarchy';
        """)

        # If table existed with old schema, alter columns
        cursor.execute("SHOW COLUMNS FROM `dim_country`;")
        existing_cols = [r[0] for r in cursor.fetchall()]

        column_defs = [
            ("alpha_3", "VARCHAR(10) NULL AFTER `country_code`"),
            ("numeric_code", "INT NULL AFTER `alpha_3`"),
            ("country_name", "VARCHAR(150) NOT NULL AFTER `numeric_code`"),
            ("country_name_cia", "VARCHAR(150) NULL AFTER `country_name`"),
            ("region_cia", "VARCHAR(100) NULL AFTER `country_name_cia`"),
            ("iso_region", "VARCHAR(100) NULL AFTER `region_cia`"),
            ("iso_sub_region", "VARCHAR(100) NULL AFTER `iso_region`"),
            ("iso_intermediate_region", "VARCHAR(100) NULL AFTER `iso_sub_region`"),
            ("iso_3166_2", "VARCHAR(50) NULL AFTER `iso_intermediate_region`")
        ]
        for col, col_def in column_defs:
            if col not in existing_cols:
                try:
                    cursor.execute(f"ALTER TABLE `dim_country` ADD COLUMN `{col}` {col_def};")
                except Exception as e:
                    print(f"Note on adding {col}: {e}")

        # Step 2: Prepare Records
        records = []
        seen_codes = set()

        for _, row in df.iterrows():
            alpha2 = clean_val(row.get("Alpha-2"))
            if not alpha2:
                continue
            alpha2 = alpha2.upper()
            if alpha2 in seen_codes:
                continue
            seen_codes.add(alpha2)

            alpha3 = clean_val(row.get("Alpha-3"))
            if alpha3:
                alpha3 = alpha3.upper()
            
            num_code = row.get("Country Code")
            numeric_code = int(float(num_code)) if pd.notna(num_code) else None

            country_name = clean_val(row.get("ISO 3166 NAME")) or clean_val(row.get("COUNTRY_NAME CIA")) or alpha2
            country_name_cia = clean_val(row.get("COUNTRY_NAME CIA"))
            region_cia = clean_val(row.get("REGION_CODE CIA"))
            iso_region = clean_val(row.get("ISO 3166 Region"))
            iso_sub_region = clean_val(row.get("ISO 3166 Sub Region"))
            iso_intermediate = clean_val(row.get("ISO 3166 Intermediate Region"))
            iso_3166_2 = clean_val(row.get("ISO 3166"))

            records.append((
                alpha2, alpha3, numeric_code, country_name, country_name_cia, region_cia,
                iso_region, iso_sub_region, iso_intermediate, iso_3166_2
            ))

        # Add default UNKNOWN record for unclassified trade records
        if "UNKNOWN" not in seen_codes:
            records.append((
                "UNKNOWN", "UNK", None, "Unknown Country / Region", "Unknown Country", "OTHER",
                "Other / Unspecified", "Other / Unspecified", None, None
            ))

        # Step 3: Upsert into dim_country
        insert_sql = """
            INSERT INTO `dim_country` (
                country_code, alpha_3, numeric_code, country_name, country_name_cia, region_cia,
                iso_region, iso_sub_region, iso_intermediate_region, iso_3166_2
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                alpha_3 = VALUES(alpha_3),
                numeric_code = VALUES(numeric_code),
                country_name = VALUES(country_name),
                country_name_cia = VALUES(country_name_cia),
                region_cia = VALUES(region_cia),
                iso_region = VALUES(iso_region),
                iso_sub_region = VALUES(iso_sub_region),
                iso_intermediate_region = VALUES(iso_intermediate_region),
                iso_3166_2 = VALUES(iso_3166_2);
        """

        cursor.executemany(insert_sql, records)
        conn.commit()

        print(f"Successfully loaded {len(records)} country records into `dim_country`!")

        # Step 4: Verification sample
        cursor.execute("SELECT country_code, alpha_3, country_name, region_cia, iso_region, iso_sub_region FROM dim_country ORDER BY country_code LIMIT 10;")
        sample_rows = cursor.fetchall()
        print("\nSample records in dim_country:")
        df_sample = pd.DataFrame(sample_rows, columns=["country_code", "alpha_3", "country_name", "region_cia", "iso_region", "iso_sub_region"])
        print(df_sample.to_string(index=False))

    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    load_dim_country()
