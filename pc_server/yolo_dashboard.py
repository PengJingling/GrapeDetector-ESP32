import argparse
import json
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.request import urlopen


latest = {
    "ok": False,
    "updated_at": "",
    "error": "YOLO is starting",
    "summary": {},
    "device": "",
    "model": "",
    "image_endpoint": "",
    "allowed_classes": [],
}


DEFAULT_GRAPE_CLASSES = [
    "grape",
    "grape_bunch",
    "normal",
    "normal_grape",
    "rotten",
    "rotten_grape",
    "damaged",
    "damaged_grape",
    "bad_grape",
]


def fetch_bytes(url: str, timeout: float = 8.0) -> bytes:
    with urlopen(url, timeout=timeout) as response:
        return response.read()


def load_model(model_path: str):
    try:
        from ultralytics import YOLO
    except Exception as exc:
        raise RuntimeError(
            "ultralytics is not installed. Run: python -m pip install ultralytics"
        ) from exc

    path = Path(model_path)
    if not path.exists() and model_path != "yolov8n.pt":
        raise FileNotFoundError(
            f"Model not found: {model_path}. Put your trained model at models/grape_yolo.pt "
            "or use --model yolov8n.pt only for a smoke test."
        )

    return YOLO(model_path)


def parse_classes(value: str) -> set[str]:
    return {item.strip().lower() for item in value.split(",") if item.strip()}


def is_allowed_class(class_name: str, allowed: set[str]) -> bool:
    lower = class_name.lower()
    return lower in allowed or ("grape" in lower and lower not in {"grapefruit"})


def is_bad_class(class_name: str) -> bool:
    lower = class_name.lower()
    return any(
        key in lower
        for key in ["bad", "rotten", "rot", "damage", "damaged", "bruise", "disease", "mold"]
    )


def summarize(result, allowed: set[str]) -> dict:
    names = result.names
    detections = []
    normal = 0
    abnormal = 0
    ignored = 0

    for box in result.boxes:
        class_id = int(box.cls[0])
        name = str(names.get(class_id, class_id))
        conf = float(box.conf[0])
        xyxy = [round(float(v), 2) for v in box.xyxy[0]]

        if not is_allowed_class(name, allowed):
            ignored += 1
            continue

        is_bad = is_bad_class(name)
        if is_bad:
            abnormal += 1
        else:
            normal += 1

        detections.append(
            {
                "class": name,
                "confidence": round(conf, 3),
                "xyxy": xyxy,
                "is_bad": is_bad,
            }
        )

    total = normal + abnormal
    return {
        "total_grapes": total,
        "normal_grapes": normal,
        "abnormal_grapes": abnormal,
        "bad_rate": round(abnormal / total, 4) if total else 0.0,
        "ignored_non_grape_detections": ignored,
        "detections": detections,
    }


def save_grape_annotation(result, allowed: set[str], output_path: Path) -> None:
    try:
        import cv2

        image = result.orig_img.copy()
        names = result.names
        for box in result.boxes:
            class_id = int(box.cls[0])
            name = str(names.get(class_id, class_id))
            if not is_allowed_class(name, allowed):
                continue

            conf = float(box.conf[0])
            x1, y1, x2, y2 = [int(float(v)) for v in box.xyxy[0]]
            color = (0, 0, 255) if is_bad_class(name) else (0, 180, 0)
            label = f"{name} {conf:.2f}"
            cv2.rectangle(image, (x1, y1), (x2, y2), color, 2)
            cv2.putText(image, label, (x1, max(20, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)

        cv2.imwrite(str(output_path), image)
    except Exception:
        output_path.write_bytes(Path("data/yolo/latest.jpg").read_bytes())


def detector_loop(
    model,
    device: str,
    image_endpoint: str,
    allowed: set[str],
    out_dir: Path,
    conf: float,
    interval: float,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_path = out_dir / "latest.jpg"
    annotated_path = out_dir / "latest_detected.jpg"
    json_path = out_dir / "latest_result.json"

    while True:
        try:
            raw_path.write_bytes(fetch_bytes(f"{device.rstrip('/')}/{image_endpoint.lstrip('/')}"))
            result = model.predict(str(raw_path), conf=conf, verbose=False)[0]
            summary = summarize(result, allowed)

            save_grape_annotation(result, allowed, annotated_path)

            payload = {
                "ok": True,
                "updated_at": datetime.now().strftime("%H:%M:%S"),
                "device": device,
                "image_endpoint": image_endpoint,
                "summary": summary,
                "raw_image": str(raw_path),
                "annotated_image": str(annotated_path),
                "model_names": result.names,
                "allowed_classes": sorted(allowed),
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
                }
            )

        time.sleep(interval)


def render_html() -> str:
    status = json.dumps(latest, ensure_ascii=False, indent=2)
    cache_buster = int(time.time() * 1000)
    summary = latest.get("summary", {})
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta http-equiv="refresh" content="2">
  <title>Grape YOLO Dashboard</title>
  <style>
    body {{ margin: 0; font-family: Arial, sans-serif; background: #f3f4f6; color: #111827; }}
    main {{ max-width: 1080px; margin: 0 auto; padding: 24px; }}
    .bar {{ display: grid; grid-template-columns: repeat(4, minmax(120px, 1fr)); gap: 10px; margin: 14px 0; }}
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
  <h2>Grape YOLO Dashboard</h2>
  <p>Device: {latest.get("device", "")} | Image: /{latest.get("image_endpoint", "")} | Updated: {latest.get("updated_at", "")} | OK: {latest.get("ok", False)}</p>
  <p>Allowed classes: {", ".join(latest.get("allowed_classes", []))}</p>
  <div class="bar">
    <div class="metric">Total<b>{summary.get("total_grapes", 0)}</b></div>
    <div class="metric">Normal<b>{summary.get("normal_grapes", 0)}</b></div>
    <div class="metric">Bad<b>{summary.get("abnormal_grapes", 0)}</b></div>
    <div class="metric">Bad Rate<b>{summary.get("bad_rate", 0)}</b></div>
  </div>
  <div class="images">
    <figure>
      <img src="/latest.jpg?t={cache_buster}" alt="raw frame">
      <figcaption>Raw frame used by YOLO</figcaption>
    </figure>
    <figure>
      <img src="/latest_detected.jpg?t={cache_buster}" alt="YOLO result">
      <figcaption>YOLO result</figcaption>
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
            image_path = Path("data/yolo/latest_detected.jpg")
            if not image_path.exists():
                image_path = Path("data/yolo/latest.jpg")
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
            image_path = Path("data/yolo/latest.jpg")
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
    parser = argparse.ArgumentParser(description="Local web dashboard for ESP32 camera and YOLO.")
    parser.add_argument("--device", default="http://192.168.4.1")
    parser.add_argument("--model", default="models/grape_yolo.pt")
    parser.add_argument("--image-endpoint", default="capture.jpg")
    parser.add_argument("--allowed-classes", default=",".join(DEFAULT_GRAPE_CLASSES))
    parser.add_argument("--conf", type=float, default=0.35)
    parser.add_argument("--interval", type=float, default=2.0)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8766)
    args = parser.parse_args()

    latest["device"] = args.device
    latest["model"] = args.model
    latest["image_endpoint"] = args.image_endpoint
    allowed = parse_classes(args.allowed_classes)
    latest["allowed_classes"] = sorted(allowed)
    model = load_model(args.model)

    threading.Thread(
        target=detector_loop,
        args=(model, args.device, args.image_endpoint, allowed, Path("data/yolo"), args.conf, args.interval),
        daemon=True,
    ).start()

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"YOLO Dashboard: http://{args.host}:{args.port}")
    print(f"Reading ESP32: {args.device}")
    server.serve_forever()


if __name__ == "__main__":
    main()
