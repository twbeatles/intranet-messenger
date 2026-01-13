
import sqlite3
import os
import sys
import base64
import logging

# Setup path to import app modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import DATABASE_PATH
from app.crypto_manager import CryptoManager

# Setup basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("DB_Fix")

def verify_and_fix_db():
    print(f"Verifying database at: {DATABASE_PATH}")
    if not os.path.exists(DATABASE_PATH):
        print("Database not found!")
        return

    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 1. Check/Add Columns
    # room_members: last_read_message_id, pinned, muted
    # messages: reply_to
    # rooms: encryption_key
    
    tables_to_check = {
        'room_members': [
            ('last_read_message_id', 'INTEGER DEFAULT 0'),
            ('pinned', 'INTEGER DEFAULT 0'),
            ('muted', 'INTEGER DEFAULT 0')
        ],
        'messages': [
            ('reply_to', 'INTEGER')
        ],
        'rooms': [
            ('encryption_key', 'TEXT')
        ],
        'users': [
            ('profile_image', 'TEXT'),
            ('status_message', 'TEXT')
        ]
    }

    try:
        for table, columns in tables_to_check.items():
            print(f"Checking table {table}...")
            cursor.execute(f"PRAGMA table_info({table})")
            existing = [row['name'] for row in cursor.fetchall()]
            
            for col_name, col_def in columns:
                if col_name not in existing:
                    print(f"  Adding missing column: {table}.{col_name}")
                    try:
                        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_def}")
                        conn.commit()
                    except Exception as e:
                        print(f"  Failed to add column {col_name}: {e}")
                else:
                    print(f"  Column {col_name} OK.")

        # 2. Fix NULL encryption keys in rooms
        print("Checking for missing encryption keys...")
        cursor.execute("SELECT id, encryption_key FROM rooms")
        rooms = cursor.fetchall()
        
        fixed_keys = 0
        for room in rooms:
            if not room['encryption_key']:
                print(f"  Room {room['id']} has no key. Generating one...")
                # Generate new raw key (base64)
                raw_key = base64.b64encode(os.urandom(32)).decode('utf-8')
                # Encrypt with master key
                encrypted_key = CryptoManager.encrypt_room_key(raw_key)
                
                cursor.execute("UPDATE rooms SET encryption_key = ? WHERE id = ?", (encrypted_key, room['id']))
                conn.commit()
                fixed_keys += 1
        
        if fixed_keys > 0:
            print(f"Fixed {fixed_keys} rooms with missing keys.")
        else:
            print("All rooms have encryption keys.")

        # 3. Fix potential NULLs in new columns
        # Set pinned/muted to 0 if NULL
        cursor.execute("UPDATE room_members SET pinned = 0 WHERE pinned IS NULL")
        cursor.execute("UPDATE room_members SET muted = 0 WHERE muted IS NULL")
        cursor.execute("UPDATE room_members SET last_read_message_id = 0 WHERE last_read_message_id IS NULL")
        conn.commit()
        print("Ensured default values for room_members columns.")

    except Exception as e:
        print(f"Error during verification: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    verify_and_fix_db()
