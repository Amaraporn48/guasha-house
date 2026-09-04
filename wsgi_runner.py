import os
import sys
import glob

# Set base directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# Auto-discover virtualenv paths on Hostinger / cPanel / CloudLinux
for pattern in [
    os.path.join(BASE_DIR, "venv", "lib", "python*", "site-packages"),
    os.path.join(BASE_DIR, ".venv", "lib", "python*", "site-packages"),
    os.path.expanduser("~/virtualenv/**/lib/python*/site-packages"),
    os.path.expanduser("~/.local/lib/python*/site-packages"),
    os.path.expanduser("~/python/lib/python*/site-packages"),
]:
    for p in glob.glob(pattern, recursive=True):
        if p not in sys.path:
            sys.path.insert(0, p)

from a2wsgi import ASGIMiddleware
from main import app as asgi_app
from wsgiref.handlers import CGIHandler

# Wrap FastAPI ASGI app into standard WSGI
wsgi_app = ASGIMiddleware(asgi_app)

if __name__ == "__main__":
    CGIHandler().run(wsgi_app)
