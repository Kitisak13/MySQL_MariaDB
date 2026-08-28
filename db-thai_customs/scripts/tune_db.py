import sys
import mysql.connector

sys.stdout.reconfigure(encoding="utf-8")

conn = mysql.connector.connect(host="127.0.0.1", port=3306, user="root", password="", database="thai_customs", use_pure=True)
cur = conn.cursor()

try:
    cur.execute("SHOW VARIABLES LIKE 'innodb_buffer_pool_size';")
    print("innodb_buffer_pool_size:", cur.fetchone())
except Exception as e:
    print("Error getting buffer pool:", e)

try:
    cur.execute("SET GLOBAL innodb_buffer_pool_size = 1073741824;") # 1GB
    print("SET GLOBAL innodb_buffer_pool_size = 1GB SUCCESS!")
except Exception as e:
    print("Error setting global buffer pool:", e)

# Add index on (period_year, trade_type) for all 4 fact tables to make delete & partition queries lightning fast
for tbl in ["fact_trade_by_country", "fact_trade_by_transport", "fact_trade_by_port", "fact_trade_by_office"]:
    try:
        cur.execute(f"ALTER TABLE `{tbl}` ADD INDEX `idx_yt` (`period_year`, `trade_type`);")
        print(f"Added index idx_yt on {tbl}")
    except Exception as e:
        print(f"Index on {tbl}: {e}")

conn.commit()
cur.close()
conn.close()
