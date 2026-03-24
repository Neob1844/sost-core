"""SOST Auth Gateway — standalone FastAPI server.

Run directly: python3 -m auth.server
Or via uvicorn: uvicorn auth.server:app --host 127.0.0.1 --port 8200
"""
import sys
import os

# Add repo root to path so auth package imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from auth.gateway import create_auth_app

app = create_auth_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8200, log_level="info")
