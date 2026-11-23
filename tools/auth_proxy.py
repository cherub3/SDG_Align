"""Local dev proxy: forwards http://localhost:<port>/* to an IAM-protected Cloud Run service, adding the caller's gcloud identity token.
A browser cannot attach that token itself, so this is how the frontend's Mode A is pointed at the deployed API without making it public.
  python tools/auth_proxy.py <service_url> <gcloud.cmd> [port=8000]
Binds to 127.0.0.1 only. The token is never printed or written."""
import subprocess, sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import requests

URL, GCLOUD = sys.argv[1].rstrip("/"), sys.argv[2]
PORT = int(sys.argv[3]) if len(sys.argv) > 3 else 8000
TOKEN = subprocess.run([GCLOUD, "auth", "print-identity-token"], capture_output=True, text=True, check=True).stdout.strip()
SESSION = requests.Session()   # keep-alive to Cloud Run: a new TLS connection per request costs about 1 s, longer than the frontend 1.5 s detection timeout
SKIP = {"host", "content-length", "connection", "accept-encoding", "authorization"}


class H(BaseHTTPRequestHandler):
    def _go(self):
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0)) or None
        h = {k: v for k, v in self.headers.items() if k.lower() not in SKIP}
        h["Authorization"] = "Bearer " + TOKEN
        r = SESSION.request(self.command, URL + self.path, headers=h, data=body, timeout=130)
        self.send_response(r.status_code)
        for k, v in r.headers.items():
            if k.lower() not in ("content-length", "transfer-encoding", "content-encoding", "connection"):
                self.send_header(k, v)
        self.send_header("Content-Length", str(len(r.content)))
        self.end_headers()
        self.wfile.write(r.content)
    do_GET = do_POST = do_OPTIONS = _go

    def log_message(self, *a):
        pass


ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
