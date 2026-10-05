"""
Export Specific Food/Agricultural Chapter Datasets directly from MariaDB with full Dimension enrichment.
Author: Lead Data Engineer
Usage:
    python db-food-export/scripts/export_chapter_dataset.py --chapters 07 08 20 --output master_data/food_07_08_20_export.csv
"""

import os
import sys
import time
import argparse
import pandas as pd

# Unbuffered UTF-8 output
sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config.db_config import get_connection

def export_chapters(chapters, output_path):
    start_time = time.time()
    print("=" * 80, flush=True)
    print(f"EXPORTING ENRICHED CHAPTER DATASET: Chapters {chapters}", flush=True)
    print("=" * 80, flush=True)

    conn = get_connection()

    # Format chapter string list for SQL IN clause
    formatted_chaps = [str(c).strip().zfill(2) for c in chapters]
    in_clause = ", ".join([f"'{c}'" for c in formatted_chaps])

    query = f"""
        SELECT 
            f.export_date as `Date`,
            f.export_year,
            f.export_month,
            f.country_code,
            c.country_name,
            c.country_name_th,
            c.country_name_en,
            c.iso_region,
            c.iso_sub_region,
            c.region_cia,
            f.hs_11_code,
            h.hs_11_description_th,
            h.hs_11_description_en,
            h.hs_8_code,
            h.hs_8_description_th,
            h.hs_8_description_en,
            h.hs_4_code,
            h.hs_4_description_th,
            h.hs_4_description_en,
            h.hs_2_code,
            h.hs_2_description_th,
            h.hs_2_description_en,
            h.unit_code,
            h.unit_name,
            f.quantity,
            f.value_usd,
            f.value_thb
        FROM fact_food_export f
        INNER JOIN dim_country c ON f.country_code = c.country_code
        INNER JOIN dim_hs11_code h ON f.hs_11_code = h.hs_11_code
        WHERE h.hs_2_code IN ({in_clause})
          AND (f.quantity > 0 OR f.value_usd > 0 OR f.value_thb > 0)
        ORDER BY f.export_date, f.country_code, f.hs_11_code;
    """

    print("Querying and streaming enriched trade data from MariaDB...", flush=True)
    df = pd.read_sql(query, conn)
    conn.close()

    total_rows = len(df)
    print(f"Total Enriched Fact Records matched: {total_rows:,} rows", flush=True)

    # Ensure output directory exists
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    print(f"Writing to CSV: {output_path}...", flush=True)
    df.to_csv(output_path, index=False, encoding="utf-8")

    file_size_mb = os.path.getsize(output_path) / (1024 * 1024)
    duration = round(time.time() - start_time, 2)

    print("-" * 80, flush=True)
    print(f"🎉 Export Completed in {duration:.2f}s | Output Size: {file_size_mb:.2f} MB | Rows: {total_rows:,}")
    print("=" * 80, flush=True)

def main():
    parser = argparse.ArgumentParser(description="Export Enriched Food Chapters from MariaDB")
    parser.add_argument("--chapters", nargs="+", default=["07", "08", "20"], help="List of 2-digit HS chapters (e.g. 07 08 20)")
    parser.add_argument("--output", type=str, default="db-food-export/master_data/food_07_08_20_export.csv", help="Target output CSV path")

    args = parser.parse_args()
    export_chapters(args.chapters, args.output)

if __name__ == "__main__":
    main()
