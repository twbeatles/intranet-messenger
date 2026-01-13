
import sqlite3
import os
from config import DATABASE_PATH

def check_db_integrity():
    print(f"Checking database at: {DATABASE_PATH}")
    if not os.path.exists(DATABASE_PATH):
        print("Database not found.")
        return

    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Check Messages Schema
    print("\n--- Messages Table Columns ---")
    cursor.execute("PRAGMA table_info(messages)")
    cols = cursor.fetchall()
    for c in cols:
        print(f"{c['name']} ({c['type']})")

    # Check Rooms Schema
    print("\n--- Rooms Table Columns ---")
    cursor.execute("PRAGMA table_info(rooms)")
    cols = cursor.fetchall()
    for c in cols:
        print(f"{c['name']} ({c['type']})")

    conn.close()

if __name__ == "__main__":
    check_db_integrity()
