from app import create_app
import sys
import os

# Fix path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

app, socketio = create_app()

if __name__ == '__main__':
    print("Starting test server on 5001...")
    socketio.run(app, host='127.0.0.1', port=5001, debug=False, use_reloader=False)
