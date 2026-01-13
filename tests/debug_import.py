import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
print(f"Path: {sys.path[0]}")

try:
    import config
    print(f"Config loaded: {config}")
    print(f"DB Path: {config.DATABASE_PATH}")
except Exception as e:
    print(f"Config import failed: {e}")

try:
    from app import create_app
    print("App imported successfully")
except Exception as e:
    print(f"App import failed: {e}")
    import traceback
    traceback.print_exc()
