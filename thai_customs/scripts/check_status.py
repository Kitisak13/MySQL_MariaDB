import sys
import mysql.connector

sys.stdout.reconfigure(encoding="utf-8")

conn = mysql.connector.connect(host="127.0.0.1", port=3306, user="root", password="", database="thai_customs", use_pure=True)
cur = conn.cursor(dictionary=True)
cur.execute("SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED;")

cur.execute("SELECT COUNT(*) AS total_files, SUM(rows_loaded) AS total_rows, SUM(total_value_thb) AS total_thb FROM data_ingestion_log WHERE status = 'SUCCESS';")
row = cur.fetchone()

print("=" * 80)
print("THAI CUSTOMS LIVE INGESTION STATUS")
print("=" * 80)
print(f"Total Files Completed: {row['total_files']} files")
print(f"Total Fact Rows Ingested: {row['total_rows'] or 0:,} rows")
print(f"Total Value Processed: {row['total_thb'] or 0:,.2f} THB")

print("\nDimension Tables Summary:")
for tbl in ["dim_hs_code", "dim_country", "dim_transport_type", "dim_customs_port", "dim_customs_office"]:
    cur.execute(f"SELECT COUNT(*) AS c FROM `{tbl}`;")
    print(f"  - {tbl:<22}: {cur.fetchone()['c']:,} records")

cur.execute("SELECT dataset_id, filename, rows_loaded, total_value_thb, ingested_at FROM data_ingestion_log ORDER BY id DESC LIMIT 5;")
print("\nRecent Completed Files:")
for r in cur.fetchall():
    print(f"  - [{r['dataset_id']}] {r['filename']} -> {r['rows_loaded']:,} rows ({r['total_value_thb']:,.2f} THB) at {r['ingested_at']}")

cur.execute("SELECT dataset_id, COUNT(*) as file_count, SUM(rows_loaded) as rows_sum FROM data_ingestion_log GROUP BY dataset_id;")
print("\nBreakdown by Dataset:")
for r in cur.fetchall():
    print(f"  * {r['dataset_id']:<20}: {r['file_count']} files, {r['rows_sum']:,} rows")

cur.close()
conn.close()
