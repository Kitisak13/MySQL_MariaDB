import os
import mysql.connector
from dotenv import load_dotenv

# Load environment variables
dotenv_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)

DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("DB_PORT", 3306))
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_DIT_NAME", "dit_product_prices")

def get_connection(database: str = DB_NAME):
    """
    Creates and returns a connection to MySQL/MariaDB with utf8mb4 encoding,
    buffered cursors, and optimal packet sizing.
    """
    conn = mysql.connector.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        database=database,
        charset="utf8mb4",
        collation="utf8mb4_unicode_ci",
        use_pure=True,
        autocommit=False
    )
    # Dynamically ensure max_allowed_packet is adequate for large batch inserts
    try:
        cursor = conn.cursor()
        cursor.execute("SET SESSION max_allowed_packet = 1073741824;")
        cursor.close()
    except Exception:
        pass
    return conn
