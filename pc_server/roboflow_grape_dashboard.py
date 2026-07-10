import argparse
import base64
import json
import os
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen


latest = {
    "ok": False,
    "updated_at": "",
    "error": "Roboflow dashboard is starting",
    "device": "",
    "image_endpoint": "",
    "roboflow_model": "",
    "summary": {},
    "predictions": [],
}


def fetch_bytes(url: str, timeout: float = 10.0) -> bytes:
    with urlopen(url, timeout=timeout) as response:
        return response.read()


def post_roboflow(image_bytes: bytes, model: str, api_key: str, confidence: int, overlap: int) -> dict:
    endpoint = (
        f"https://detect.roboflow.com/{model}"
        f"?api_key={api_key}&confidence={confidence}&overlap={overlap}"
    )
    payload = base64.b64encode(image_bytes)
    request = Request(
        endpoint,
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urlopen(request, timeout=30.0) as response:
        return json.loads(response.read().decode("utf-8"))


def summarize(predictions: list[dict]) -> dict:
    total = len(predictions)
    return {
        "total_grapes": total,
        "normal_grapes": total,
        "abnormal_grapes": 0,
        "bad_rate": 0.0,
        "note": "This public Roboflow model detects grapes only; it does not classify rotten/damaged grapes.",
    }


def annotate(raw_path: Path, annotated_path: Path, predictions: list[dict]) -> None:
    try:
        import cv2

        image = cv2.imread(str(raw_path))
        if image is None:
            annotated_path.write_bytes(raw_path.read_bytes())
            return

        for item in predictions:
            x = float(item.get("x", 0))
            y = float(item.get("y", 0))
            w = float(item.get("width", 0))
            h = float(item.get("height", 0))
            conf = float(item.get("confidence", 0))
            name = str(item.get("class", "grape"))
            x1 = int(x - w / 2)
            y1 = int(y - h / 2)
            x2 = int(x + w / 2)
            y2 = int(y + h / 2)
            label = f"{name} {conf:.2f}"
            cv2.rectangle(image, (x1, y1), (x2, y2), (0, 180, 0), 2)
            cv2.putText(image, label, (x1, max(22, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 180, 0), 2)

        cv2.imwrite(str(annotated_path), image)
    except Exception:
        annotated_path.write_bytes(raw_path.read_bytes())


def detector_loop(
    device: str,
    image_endpoint: str,
    model: str,
    api_key: str,
    confidence: int,
    overlap: int,
    out_dir: Path,
    interval: float,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_path = out_dir / "roboflow_latest.jpg"
    annotated_path = out_dir / "roboflow_latest_detected.jpg"
    json_path = out_dir / "roboflow_latest_result.json"

    while True:
        try:
            image_bytes = fetch_bytes(f"{device.rstrip('/')}/{image_endpoint.lstrip('/')}")
            raw_path.write_bytes(image_bytes)
            result = post_roboflow(image_bytes, model, api_key, confidence, overlap)
            predictions = result.get("predictions", [])
            annotate(raw_path, annotated_path, predictions)

            payload = {
                "ok": True,
                "updated_at": datetime.now().strftime("%H:%M:%S"),
                "device": device,
                "image_endpoint": image_endpoint,
                "roboflow_model": model,
                "summary": summarize(predictions),
                "predictions": predictions,
                "raw_image": str(raw_path),
                "annotated_image": str(annotated_path),
            }
            json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            latest.update(payload)
            latest["error"] = ""
        except Exception as exc:
            latest.update(
                {
                    "ok": False,
                    "updated_at": datetime.now().strftime("%H:%M:%S"),
                    "error": str(exc),
                    "device": device,
                    "image_endpoint": image_endpoint,
                    "roboflow_model": model,
                }
            )

        time.sleep(interval)


def render_html() -> str:
    cache_buster = int(time.time() * 1000)
    status = json.dumps(latest, ensure_ascii=False, indent=2)
    summary = latest.get("summary", {})
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta http-equiv="refresh" content="2">
  <title>Roboflow Grape Dashboard</title>
  <style>
    body {{ margin: 0; font-family: Arial, sans-serif; background: #f3f4f6; color: #111827; }}
    main {{ max-width: 1080px; margin: 0 auto; padding: 24px; }}
    .bar {{ display: grid; grid-template-columns: repeat(3, minmax(120px, 1fr)); gap: 10px; margin: 14px 0; }}
    .metric {{ background: white; border: 1px solid #d1d5db; border-radius: 8px; padding: 12px; }}
    .metric b {{ display: block; font-size: 24px; }}
    .images {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }}
    figure {{ margin: 0; }}
    figcaption {{ margin: 6px 0 10px; color: #374151; }}
    img {{ width: 100%; background: #111; border: 1px solid #d1d5db; }}
    pre {{ background: white; padding: 12px; border: 1px solid #d1d5db; overflow: auto; }}
  </style>
</head>
<body>
<main>
  <h2>Roboflow Grape Dashboard</h2>
  <p>Model: {latest.get("roboflow_model", "")} | Image: /{latest.get("image_endpoint", "")} | Updated: {latest.get("updated_at", "")} | OK: {latest.get("ok", False)}</p>
  <div class="bar">
    <div class="metric">Grapes<b>{summary.get("total_grapes", 0)}</b></div>
    <div class="metric">Bad<b>{summary.get("abnormal_grapes", 0)}</b></div>
    <div class="metric">Bad Rate<b>{summary.get("bad_rate", 0)}</b></div>
  </div>
  <div class="images">
    <figure>
      <img src="/latest.jpg?t={cache_buster}" alt="raw frame">
      <figcaption>Raw frame sent to Roboflow</figcaption>
    </figure>
    <figure>
      <img src="/latest_detected.jpg?t={cache_buster}" alt="Roboflow result">
      <figcaption>Roboflow grape result</figcaption>
    </figure>
  </div>
  <h3>Status</h3>
  <pre>{status}</pre>
</main>
</body>
</html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(render_html().encode("utf-8"))
            return

        if self.path.startswith("/latest_detected.jpg"):
            image_path = Path("data/yolo/roboflow_latest_detected.jpg")
            if not image_path.exists():
                image_path = Path("data/yolo/roboflow_latest.jpg")
            if not image_path.exists():
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(image_path.read_bytes())
            return

        if self.path.startswith("/latest.jpg"):
            image_path = Path("data/yolo/roboflow_latest.jpg")
            if not image_path.exists():
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(image_path.read_bytes())
            return

        if self.path == "/result.json":
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(latest, ensure_ascii=False).encode("utf-8"))
            return

        self.send_error(404)

    def log_message(self, fmt: str, *args) -> None:
        return


def main() -> None:
    parser = argparse.ArgumentParser(description="Call a public Roboflow grape model on ESP32 camera images.")
    parser.add_argument("--device", default="http://192.168.4.1")
    parser.add_argument("--image-endpoint", default="capture-xga.jpg")
    parser.add_argument("--model", default="grape-detection-oquct/14")
    parser.add_argument("--api-key", default=os.getenv("ROBOFLOW_API_KEY", ""))
    parser.add_argument("--confidence", type=int, default=35)
    parser.add_argument("--overlap", type=int, default=30)
    parser.add_argument("--interval", type=float, default=3.0)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8767)
    args = parser.parse_args()

    if not args.api_key:
        raise SystemExit(
            "Missing Roboflow API key. Use --api-key YOUR_KEY or set ROBOFLOW_API_KEY."
        )

    latest["device"] = args.device
    latest["image_endpoint"] = args.image_endpoint
    latest["roboflow_model"] = args.model

    threading.Thread(
        target=detector_loop,
        args=(
            args.device,
            args.image_endpoint,
            args.model,
            args.api_key,
            args.confidence,
            args.overlap,
            Path("data/yolo"),
            args.interval,
        ),
        daemon=True,
    ).start()

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Roboflow Dashboard: http://{args.host}:{args.port}")
    print(f"Reading ESP32: {args.device}")
    print(f"Roboflow model: {args.model}")
    server.serve_forever()


if __name__ == "__main__":
    main()
