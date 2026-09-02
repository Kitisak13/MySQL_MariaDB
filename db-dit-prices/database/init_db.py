import os
import sys
import mysql.connector

# Ensure UTF-8 output
sys.stdout.reconfigure(encoding="utf-8")

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config.db_config import DB_HOST, DB_PORT, DB_USER, DB_PASSWORD

def init_database():
    schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
    if not os.path.exists(schema_path):
        raise FileNotFoundError(f"Schema file not found at: {schema_path}")

    print(f"Connecting to MariaDB/MySQL at {DB_HOST}:{DB_PORT} as {DB_USER}...")
    conn = mysql.connector.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        use_pure=True
    )
    cursor = conn.cursor()

    try:
        print(f"Executing DDL statements from: {schema_path}")
        with open(schema_path, "r", encoding="utf-8") as f:
            sql_script = f.read()

        # Split statements by semicolon while handling comments
        statements = sql_script.split(";")
        for stmt in statements:
            cleaned_stmt = stmt.strip()
            if cleaned_stmt:
                cursor.execute(cleaned_stmt)

        conn.commit()
        print("Database `dit_product_prices` and all tables initialized successfully!")
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    init_database()
