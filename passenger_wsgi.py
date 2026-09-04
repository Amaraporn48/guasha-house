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

try:
    from a2wsgi import ASGIMiddleware
    from main import app as asgi_app
    application = ASGIMiddleware(asgi_app)
except Exception as e:
    import traceback
    err_text = traceback.format_exc()
    def application(environ, start_response):
        start_response('500 Internal Server Error', [('Content-Type', 'text/html; charset=utf-8')])
        html = f"""<!DOCTYPE html><html><head><meta charset='utf-8'><title>Guasha House - Setup</title></head>
<body style='font-family:-apple-system,BlinkMacSystemFont,sans-serif;padding:40px;background:#fbfaf7;'>
<div style='max-width:600px;margin:0 auto;background:#fff;padding:30px;border-radius:12px;border:1px solid #ddd;'>
<h2>🌿 Guasha House Python Status</h2>
<p style='color:#c00;'><strong>Error initializing application:</strong> {e}</p>
<pre style='background:#1a1a1a;color:#0f0;padding:15px;border-radius:8px;font-size:12px;overflow-x:auto;'>{err_text}</pre>
</div></body></html>"""
        return [html.encode('utf-8')]
