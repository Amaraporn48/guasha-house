import sys
import os

# Add parent directory to sys.path so Vercel can locate main.py and database.py
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app

# Export app instance for Vercel Serverless Function
app = app
