import os
from dotenv import load_dotenv, find_dotenv
import mysql.connector

# Load environment variables from closest .env file
load_dotenv(find_dotenv(usecwd=True))

DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_CUSTOMS_NAME", "thai_customs")

def get_connection(include_db: bool = True):
    """
    Get a resilient connection to MySQL / MariaDB server.
    """
    config = {
        "host": DB_HOST,
        "port": DB_PORT,
        "user": DB_USER,
        "password": DB_PASSWORD,
        "charset": "utf8mb4",
        "use_unicode": True,
        "use_pure": True,
        "connection_timeout": 120,
        "autocommit": False
    }
    conn = mysql.connector.connect(**config)
    try:
        cur = conn.cursor()
        cur.execute("SET SESSION max_allowed_packet=1073741824;")
        cur.close()
    except Exception:
        pass
    if include_db:
        conn.database = DB_NAME
    return conn
