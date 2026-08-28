import os
import sys

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config.db_config import get_connection

def initialize_database():
    """Reads schema.sql and applies DDL to MySQL / MariaDB."""
    schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
    with open(schema_path, "r", encoding="utf-8") as f:
        sql_content = f.read()

    # Split statements
    statements = [stmt.strip() for stmt in sql_content.split(";") if stmt.strip()]

    print("Connecting to MySQL server...")
    conn = get_connection(include_db=False)
    cursor = conn.cursor()

    try:
        for stmt in statements:
            if stmt:
                cursor.execute(stmt)
        conn.commit()
        print("Thai Customs Database and 10 tables initialized successfully!")
    except Exception as e:
        conn.rollback()
        print(f"Error initializing database: {e}")
        raise
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    initialize_database()
