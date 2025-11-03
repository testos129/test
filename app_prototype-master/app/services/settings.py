import sqlite3

DB_PATH = "data/data.db"

def get_connection():
    return sqlite3.connect(DB_PATH)


def get_setting(key, default=None):

    """Retrieve a setting from the database."""

    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT value FROM settings WHERE key=?", (key,))
        row = cur.fetchone()

        return row[0] if row else default
    

def set_setting(key, value):

    """Set a setting in the database."""

    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value
        """, (key, value))
        conn.commit()