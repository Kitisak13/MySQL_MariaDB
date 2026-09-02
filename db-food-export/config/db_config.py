import mysql.connector
from mysql.connector import pooling

DB_CONFIG = {
    "host": "127.0.0.1",
    "port": 3306,
    "user": "root",
    "password": "",
    "database": "food_export",
    "charset": "utf8mb4",
    "collation": "utf8mb4_unicode_ci",
    "autocommit": False,
    "use_pure": True,
}

_connection_pool = None

def get_connection_pool(pool_name="food_export_pool", pool_size=5):
    """Initializes and returns a thread-safe connection pool."""
    global _connection_pool
    if _connection_pool is None:
        cfg = DB_CONFIG.copy()
        _connection_pool = pooling.MySQLConnectionPool(
            pool_name=pool_name,
            pool_size=pool_size,
            **cfg
        )
    return _connection_pool

def get_connection(include_db=True):
    """Returns a connection from pool or creates a standalone connection."""
    cfg = DB_CONFIG.copy()
    if not include_db:
        cfg.pop("database", None)
    
    conn = mysql.connector.connect(**cfg)
    cursor = conn.cursor()
    cursor.execute("SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;")
    cursor.close()
    return conn
