import os
import sys

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from a2wsgi import ASGIMiddleware
from main import app as asgi_app

# WSGI Application entry point for Hostinger hPanel (Passenger)
application = ASGIMiddleware(asgi_app)
