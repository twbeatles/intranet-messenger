import sqlite3
import os

db_path = 'messenger.db'
print(f"DB Path: {os.path.abspath(db_path)}")
print(f"DB Exists: {os.path.exists(db_path)}")
print(f"DB Size: {os.path.getsize(db_path) if os.path.exists(db_path) else 'N/A'} bytes")

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in cursor.fetchall()]
print(f"\nTables in DB: {tables}")

if 'users' in tables:
    cursor.execute("SELECT COUNT(*) FROM users")
    print(f"User count: {cursor.fetchone()[0]}")
else:
    print("ERROR: 'users' table does NOT exist!")

conn.close()
