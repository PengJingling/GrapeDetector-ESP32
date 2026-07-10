import argparse
import json
import time
from datetime import datetime
from pathlib import Path
from urllib.request import urlopen


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


def is_bad_class(class_name: str) -> bool:
    lower = class_name.lower()
    return any(
        key in lower
        for key in [
            "bad",
            "rotten",
            "rot",
            "damage",
            "damaged",
            "bruise",
            "disease",
            "mold",
        ]
    )


def is_grape_class(class_name: str) -> bool:
    lower = class_name.lower()
    return lower in ALLOWED_CLASSES or ("grape" in lower and lower not in {"grapefruit"})


ALLOWED_CLASSES = {item.lower() for item in DEFAULT_GRAPE_CLASSES}


def summarize_detections(result) -> dict:
    names = result.names
    detections = []
    normal = 0
    abnormal = 0
    ignored = 0

    for box in result.boxes:
        class_id = int(box.cls[0])
        name = str(names.get(class_id, class_id))
        conf = float(box.conf[0])
        xyxy = [float(v) for v in box.xyxy[0]]
        is_bad = is_bad_class(name)

        if not is_grape_class(name):
            ignored += 1
            continue

        if is_bad:
            abnormal += 1
        else:
            normal += 1

        detections.append(
            {
                "class_id": class_id,
                "class_name": name,
                "confidence": round(conf, 4),
                "xyxy": [round(v, 2) for v in xyxy],
                "is_bad": is_bad,
            }
        )

    total = normal + abnormal
    bad_rate = abnormal / total if total else 0.0

    return {
        "total_grapes": total,
        "normal_grapes": normal,
        "abnormal_grapes": abnormal,
        "bad_rate": round(bad_rate, 4),
        "ignored_non_grape_detections": ignored,
        "detections": detections,
    }


def run_once(model, device: str, image_endpoint: str, out_dir: Path, conf: float) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    image_path = out_dir / "latest.jpg"
    annotated_path = out_dir / "latest_detected.jpg"
    result_path = out_dir / "latest_result.json"

    image_url = f"{device.rstrip('/')}/{image_endpoint.lstrip('/')}"
    image_path.write_bytes(fetch_bytes(image_url))

    result = model.predict(str(image_path), conf=conf, verbose=False)[0]
    summary = summarize_detections(result)

    try:
        import cv2

        image = result.orig_img.copy()
        for item in summary["detections"]:
            x1, y1, x2, y2 = [int(v) for v in item["xyxy"]]
            color = (0, 0, 255) if item["is_bad"] else (0, 180, 0)
            label = f"{item['class_name']} {item['confidence']:.2f}"
            cv2.rectangle(image, (x1, y1), (x2, y2), color, 2)
            cv2.putText(image, label, (x1, max(20, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
        cv2.imwrite(str(annotated_path), image)
    except Exception as exc:
        annotated_path = image_path
        summary["annotation_warning"] = str(exc)

    payload = {
        "ok": True,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "device": device,
        "image_endpoint": image_endpoint,
        "image": str(image_path),
        "annotated_image": str(annotated_path),
        "model_names": result.names,
        "summary": summary,
    }

    result_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Run YOLO on ESP32 grape detector images.")
    parser.add_argument("--device", default="http://192.168.4.1")
    parser.add_argument("--model", default="models/grape_yolo.pt")
    parser.add_argument("--image-endpoint", default="capture.jpg")
    parser.add_argument("--out", default="data/yolo")
    parser.add_argument("--conf", type=float, default=0.35)
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--interval", type=float, default=2.0)
    args = parser.parse_args()

    model = load_model(args.model)
    out_dir = Path(args.out)

    while True:
        payload = run_once(model, args.device, args.image_endpoint, out_dir, args.conf)
        summary = payload["summary"]
        print(
            f"[YOLO] total={summary['total_grapes']} "
            f"bad={summary['abnormal_grapes']} "
            f"bad_rate={summary['bad_rate']}"
        )
        if not args.loop:
            break
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
