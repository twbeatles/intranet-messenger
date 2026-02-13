
import sqlite3
import os
from config import DATABASE_PATH

def migrate_db():
    print(f"Migrating database at: {DATABASE_PATH}")
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 1. Ensure new tables exist
    tables = {
        'pinned_messages': '''
            CREATE TABLE IF NOT EXISTS pinned_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                room_id INTEGER NOT NULL,
                message_id INTEGER,
                content TEXT,
                pinned_by INTEGER NOT NULL,
                pinned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (room_id) REFERENCES rooms(id),
                FOREIGN KEY (message_id) REFERENCES messages(id),
                FOREIGN KEY (pinned_by) REFERENCES users(id)
            )
        ''',
        'polls': '''
            CREATE TABLE IF NOT EXISTS polls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                room_id INTEGER NOT NULL,
                created_by INTEGER NOT NULL,
                question TEXT NOT NULL,
                multiple_choice INTEGER DEFAULT 0,
                anonymous INTEGER DEFAULT 0,
                closed INTEGER DEFAULT 0,
                ends_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (room_id) REFERENCES rooms(id),
                FOREIGN KEY (created_by) REFERENCES users(id)
            )
        ''',
        'poll_options': '''
            CREATE TABLE IF NOT EXISTS poll_options (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                poll_id INTEGER NOT NULL,
                option_text TEXT NOT NULL,
                FOREIGN KEY (poll_id) REFERENCES polls(id) ON DELETE CASCADE
            )
        ''',
        'poll_votes': '''
            CREATE TABLE IF NOT EXISTS poll_votes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                poll_id INTEGER NOT NULL,
                option_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                voted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(poll_id, option_id, user_id),
                FOREIGN KEY (poll_id) REFERENCES polls(id) ON DELETE CASCADE,
                FOREIGN KEY (option_id) REFERENCES poll_options(id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        ''',
        'room_files': '''
            CREATE TABLE IF NOT EXISTS room_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                room_id INTEGER NOT NULL,
                message_id INTEGER,
                file_path TEXT NOT NULL,
                file_name TEXT NOT NULL,
                file_size INTEGER,
                file_type TEXT,
                uploaded_by INTEGER NOT NULL,
                uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (room_id) REFERENCES rooms(id),
                FOREIGN KEY (message_id) REFERENCES messages(id),
                FOREIGN KEY (uploaded_by) REFERENCES users(id)
            )
        ''',
        'message_reactions': '''
            CREATE TABLE IF NOT EXISTS message_reactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                emoji TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(message_id, user_id, emoji),
                FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        '''
    }

    for table_name, create_sql in tables.items():
        try:
            cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table_name}'")
            if not cursor.fetchone():
                print(f"Creating table: {table_name}")
                cursor.execute(create_sql)
        except Exception as e:
            print(f"Error checking/creating table {table_name}: {e}")

    # 2. Check for missing columns in existing tables
    # Format: table_name: {column_name: column_type_definition}
    required_columns = {
        'room_members': {
            'role': 'TEXT DEFAULT "member"',
            'pinned': 'INTEGER DEFAULT 0',
            'muted': 'INTEGER DEFAULT 0',
            'last_read_message_id': 'INTEGER DEFAULT 0'
        },
        'messages': {
            'reply_to': 'INTEGER'
        },
        'rooms': {
             # Add if any new columns were added to rooms, none seen in init_db snippet so far, 
             # but keeping placeholder just in case. 
             # Wait, 'pinned' and 'muted' are in room_members, not rooms (usually).
             # Let's double check models.py... yes, they were in room_members schema.
        }
    }

    for table, columns in required_columns.items():
        try:
            cursor.execute(f"PRAGMA table_info({table})")
            existing_columns = [row['name'] for row in cursor.fetchall()]
            
            for col_name, col_def in columns.items():
                if col_name not in existing_columns:
                    print(f"Adding column '{col_name}' to table '{table}'")
                    try:
                        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_def}")
                    except Exception as e:
                        print(f"Failed to add column {col_name}: {e}")
        except Exception as e:
             print(f"Error checking columns for {table}: {e}")

    # 3. Create Indexes
    indexes = [
        'CREATE INDEX IF NOT EXISTS idx_messages_room_id ON messages(room_id)',
        'CREATE INDEX IF NOT EXISTS idx_messages_created_at ON messages(created_at)',
        'CREATE INDEX IF NOT EXISTS idx_room_members_user_id ON room_members(user_id)',
        'CREATE INDEX IF NOT EXISTS idx_room_members_room_id ON room_members(room_id)',
        'CREATE INDEX IF NOT EXISTS idx_message_reactions_message_id ON message_reactions(message_id)',
        'CREATE INDEX IF NOT EXISTS idx_room_files_file_path ON room_files(file_path)',
        'CREATE INDEX IF NOT EXISTS idx_users_status ON users(status)',
    ]

    for idx_sql in indexes:
        try:
            cursor.execute(idx_sql)
        except Exception as e:
            print(f"Error creating index: {e}")

    conn.commit()
    conn.close()
    print("Migration completed.")

if __name__ == "__main__":
    migrate_db()
