import json
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


DEVICE = "http://192.168.4.1"
HOST = "127.0.0.1"
PORT = 8765
DATA_DIR = Path("data/live")

latest = {
    "ok": False,
    "updated_at": "",
    "error": "",
    "stm32": {},
    "health": {},
    "image_path": "",
}


def fetch_bytes(url: str, timeout: float = 4.0) -> bytes:
    with urlopen(url, timeout=timeout) as response:
        return response.read()


def fetch_json(url: str, timeout: float = 4.0) -> dict:
    return json.loads(fetch_bytes(url, timeout).decode("utf-8"))


def poll_device() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    image_path = DATA_DIR / "latest.jpg"

    while True:
        try:
            image_path.write_bytes(fetch_bytes(f"{DEVICE}/capture.jpg"))
            latest.update(
                {
                    "ok": True,
                    "updated_at": datetime.now().strftime("%H:%M:%S"),
                    "error": "",
                    "stm32": fetch_json(f"{DEVICE}/stm32.json"),
                    "health": fetch_json(f"{DEVICE}/health"),
                    "image_path": str(image_path),
                }
            )
        except Exception as exc:
            latest.update(
                {
                    "ok": False,
                    "updated_at": datetime.now().strftime("%H:%M:%S"),
                    "error": str(exc),
                }
            )

        time.sleep(1.0)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(render_html().encode("utf-8"))
            return

        if self.path == "/latest.jpg":
            image_path = DATA_DIR / "latest.jpg"
            if not image_path.exists():
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(image_path.read_bytes())
            return

        if self.path == "/status.json":
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(latest, ensure_ascii=False).encode("utf-8"))
            return

        self.send_error(404)

    def log_message(self, fmt: str, *args) -> None:
        return


def render_html() -> str:
    status = json.dumps(latest, ensure_ascii=False, indent=2)
    cache_buster = int(time.time())
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta http-equiv="refresh" content="2">
  <title>Grape Detector Dashboard</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; background: #f5f5f5; color: #222; }}
    main {{ max-width: 960px; margin: auto; }}
    img {{ max-width: 100%; image-rendering: auto; background: #111; }}
    pre {{ background: #fff; padding: 12px; border: 1px solid #ddd; overflow: auto; }}
  </style>
</head>
<body>
<main>
  <h2>Grape Detector Dashboard</h2>
  <p>Device: {DEVICE} | Updated: {latest.get("updated_at", "")}</p>
  <img src="/latest.jpg?t={cache_buster}" alt="latest capture">
  <h3>Status</h3>
  <pre>{status}</pre>
</main>
</body>
</html>"""


def main() -> None:
    threading.Thread(target=poll_device, daemon=True).start()
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Dashboard: http://{HOST}:{PORT}")
    print(f"Reading ESP32: {DEVICE}")
    server.serve_forever()


if __name__ == "__main__":
    main()
