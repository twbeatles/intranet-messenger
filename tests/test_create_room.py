
import os
import sys
import unittest
import shutil

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, socketio
from app import models
from config import DATABASE_PATH

class TestCreateRoom(unittest.TestCase):
    def setUp(self):
        # Use a temporary DB
        self.test_db_path = 'test_messenger.db'
        
        # Override config via monkeypatching specific modules if needed,
        # but simpler to let app use its config and we swap the DB file path in config?
        # Since config is imported in models.py, we can't easily swap it.
        # So we will backup real DB and restore it?
        # Or better: Just use a separate test runner that sets env var?
        
        # Actually, let's just use the real DB logic but separate file?
        pass

    def test_create_room_logic(self):
        app, _ = create_app()
        app.config['WTF_CSRF_ENABLED'] = False
        app.config['TESTING'] = True
        
        # We need to ensure models uses a test DB?
        # models.py imports DATABASE_PATH from config.
        # We can't change it easily.
        
        # So I will test with the REAL DB (assuming user deleted it).
        # OR I rely on the fact that 'verify_and_fix_db' works.
        
        print("Testing create_room with current DB setup...")
        
        with app.app_context():
            # Ensure DB init
            models.init_db()
            
            # Create 2 dummy users
            u1_id = models.create_user('test_u1', 'pass', 'U1')
            u2_id = models.create_user('test_u2', 'pass', 'U2')
            
            if not u1_id: # Might already exist
                u1 = models.get_user_by_username('test_u1')
                u1_id = u1['id']
            if not u2_id:
                u2 = models.get_user_by_username('test_u2')
                u2_id = u2['id']
                
            print(f"Users: {u1_id}, {u2_id}")
            
            # Try create room
            try:
                room_id = models.create_room('Test Room', 'group', u1_id, [u1_id, u2_id])
                print(f"Room Created: {room_id}")
                
                # Check Key
                key = models.get_room_key(room_id)
                print(f"Room Key: {key}")
                
                if not key:
                    print("FAIL: Key is None!")
                else:
                    print("SUCCESS: Key generated.")
                    
            except Exception as e:
                print(f"CRASH: {e}")
                import traceback
                traceback.print_exc()

if __name__ == "__main__":
    t = TestCreateRoom()
    t.test_create_room_logic()
