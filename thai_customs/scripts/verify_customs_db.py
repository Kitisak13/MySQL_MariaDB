import os
import sys
import pandas as pd

# Reconfigure stdout for UTF-8
sys.stdout.reconfigure(encoding="utf-8")

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config.db_config import get_connection

def verify_customs():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    print("=" * 80)
    print("THAI CUSTOMS DATABASE VERIFICATION & DATA QUALITY REPORT")
    print("=" * 80)

    try:
        # 1. Dimension Tables
        print("\n1. DIMENSION TABLES SUMMARY:")
        dim_tables = [
            ("dim_hs_code", "HS & Commodity Classifications"),
            ("dim_country", "Countries"),
            ("dim_transport_type", "Transport Modes"),
            ("dim_customs_port", "Customs Ports/Checkpoints"),
            ("dim_customs_office", "Regional Customs Offices")
        ]
        for tbl, label in dim_tables:
            cursor.execute(f"SELECT COUNT(*) AS total FROM `{tbl}`;")
            cnt = cursor.fetchone()["total"]
            print(f"  - {tbl:<20} ({label:<30}): {cnt:,} records")

        # 2. Fact Tables Summary
        print("\n2. FACT TABLES (TRADE TRANSACTIONS) SUMMARY:")
        fact_tables = [
            ("fact_trade_by_country", "Trade by Country"),
            ("fact_trade_by_transport", "Trade by Transport Mode"),
            ("fact_trade_by_port", "Trade by Customs Port"),
            ("fact_trade_by_office", "Trade by Regional Office")
        ]
        for tbl, label in fact_tables:
            cursor.execute(f"""
                SELECT 
                    COUNT(*) AS total_rows,
                    MIN(period_year) AS min_year,
                    MAX(period_year) AS max_year,
                    SUM(CASE WHEN trade_type = 'IMPORT' THEN value_thb ELSE 0 END) AS total_import_thb,
                    SUM(CASE WHEN trade_type = 'EXPORT' THEN value_thb ELSE 0 END) AS total_export_thb
                FROM `{tbl}`;
            """)
            res = cursor.fetchone()
            import_thb = float(res['total_import_thb']) if res['total_import_thb'] is not None else 0.0
            export_thb = float(res['total_export_thb']) if res['total_export_thb'] is not None else 0.0
            print(f"\n  --- {tbl} ({label}) ---")
            print(f"      Total Records   : {res['total_rows']:,}")
            print(f"      Year Range      : {res['min_year']} - {res['max_year']}")
            print(f"      Total Import THB: {import_thb:,.2f} THB")
            print(f"      Total Export THB: {export_thb:,.2f} THB")

        # 3. Top 5 Import/Export Commodities by Country Fact Table
        print("\n3. TOP 5 EXPORT COMMODITIES (by Value):")
        cursor.execute("""
            SELECT 
                f.hs_code,
                d.desc_th,
                SUM(f.value_thb) AS total_fob_thb
            FROM fact_trade_by_country f
            LEFT JOIN dim_hs_code d ON f.hs_code = d.hs_code
            WHERE f.trade_type = 'EXPORT'
            GROUP BY f.hs_code, d.desc_th
            ORDER BY total_fob_thb DESC
            LIMIT 5;
        """)
        top_exp = cursor.fetchall()
        df_exp = pd.DataFrame(top_exp)
        print(df_exp.to_string(index=False))

        # 4. Ingestion Log Status
        print("\n4. INGESTION AUDIT LOG SUMMARY:")
        cursor.execute("""
            SELECT 
                dataset_id,
                trade_type,
                COUNT(*) AS total_files_logged,
                SUM(rows_loaded) AS total_rows,
                MAX(ingested_at) AS last_ingested_at
            FROM data_ingestion_log
            GROUP BY dataset_id, trade_type
            ORDER BY dataset_id;
        """)
        logs = cursor.fetchall()
        df_logs = pd.DataFrame(logs)
        print(df_logs.to_string(index=False))

        print("\n" + "=" * 80)
        print("DATABASE VERIFICATION COMPLETED!")
        print("=" * 80)

    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    verify_customs()
