#!/home/u713703050/python/bin/python3
import os
import sys
import urllib.request
import urllib.error

# Project paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

VENV_PACKAGES = os.path.join(BASE_DIR, "venv", "lib", "python3.11", "site-packages")
if os.path.exists(VENV_PACKAGES):
    sys.path.insert(0, VENV_PACKAGES)

def try_proxy_to_uvicorn():
    """Forward request to background Uvicorn daemon on port 8000 if available"""
    path_info = os.environ.get("PATH_INFO", "")
    query_string = os.environ.get("QUERY_STRING", "")
    method = os.environ.get("REQUEST_METHOD", "GET")
    
    url = f"http://127.0.0.1:8000{path_info}"
    if query_string:
        url += f"?{query_string}"
        
    try:
        content_length = int(os.environ.get("CONTENT_LENGTH", 0) or 0)
        body = sys.stdin.buffer.read(content_length) if content_length > 0 else None
        
        headers = {}
        for key, val in os.environ.items():
            if key.startswith("HTTP_"):
                header_name = key[5:].replace("_", "-").title()
                headers[header_name] = val
            elif key in ("CONTENT_TYPE", "CONTENT_LENGTH") and val:
                headers[key.replace("_", "-").title()] = val
                
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=5) as response:
            print(f"Status: {response.status} {response.reason}")
            for header, val in response.getheaders():
                if header.lower() != "transfer-encoding":
                    print(f"{header}: {val}")
            print()
            sys.stdout.flush()
            sys.stdout.buffer.write(response.read())
            return True
    except Exception:
        return False

def run_wsgi_direct():
    """Fallback: Execute directly in-process via a2wsgi and CGIHandler"""
    from wsgiref.handlers import CGIHandler
    from a2wsgi import ASGIMiddleware
    from main import app
    
    wsgi_app = ASGIMiddleware(app)
    CGIHandler().run(wsgi_app)

if __name__ == "__main__":
    if not try_proxy_to_uvicorn():
        run_wsgi_direct()
