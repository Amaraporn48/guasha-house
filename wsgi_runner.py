import os
import sys
import glob

# Set up paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

# Auto-discover site-packages
for p in [
    os.path.join(BASE_DIR, "venv", "lib", "python*", "site-packages"),
    os.path.expanduser("~/python/lib/python*/site-packages"),
    os.path.expanduser("~/.local/lib/python*/site-packages"),
]:
    for match in glob.glob(p):
        if match not in sys.path:
            sys.path.insert(0, match)

from wsgiref.handlers import CGIHandler
from a2wsgi import ASGIMiddleware
from main import app

# Convert FastAPI (ASGI) to standard WSGI
wsgi_app = ASGIMiddleware(app)

if __name__ == "__main__":
    CGIHandler().run(wsgi_app)
