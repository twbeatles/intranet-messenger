import sys
import os

# Emulate conftest.py path hack
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
sys.path.insert(0, project_root)

print(f"Project root: {project_root}")
print(f"sys.path[0]: {sys.path[0]}")

try:
    import config
    print("Successfully imported config")
except ImportError as e:
    print(f"Failed to import config: {e}")

try:
    from app import create_app
    print("Successfully imported create_app")
except ImportError as e:
    print(f"Failed to import create_app: {e}")

try:
    import Crypto
    from Crypto.Cipher import AES
    print("Successfully imported Crypto.Cipher.AES")
except ImportError as e:
    print(f"Failed to import Crypto: {e}")

try:
    import app.utils
    print("Successfully imported app.utils")
except ImportError as e:
    print(f"Failed to import app.utils: {e}")

try:
    from app.models import init_db
    print("Successfully imported init_db")
except ImportError as e:
    print(f"Failed to import init_db: {e}")
