import os
import sys
from urllib.parse import parse_qs, urlencode

# Add root directory to sys.path
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from app import app

class VercelPathFixMiddleware:
    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        if environ.get("HTTP_X_FORWARDED_PROTO") == "https":
            environ["wsgi.url_scheme"] = "https"

        qs = environ.get("QUERY_STRING", "")
        if "__path=" in qs:
            params = parse_qs(qs, keep_blank_values=True)
            if "__path" in params and params["__path"]:
                target = params.pop("__path")[0] or "/"
                while target.startswith("//"):
                    target = target[1:]
                if not target.startswith("/"):
                    target = "/" + target
                environ["PATH_INFO"] = target
                environ["QUERY_STRING"] = urlencode([(k, v) for k, vs in params.items() for v in vs])
        elif environ.get("PATH_INFO", "").startswith("/api/index"):
            environ["PATH_INFO"] = "/"
            
        return self.wsgi_app(environ, start_response)

app.wsgi_app = VercelPathFixMiddleware(app.wsgi_app)
