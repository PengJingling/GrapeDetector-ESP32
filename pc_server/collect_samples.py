import argparse
import json
import time
from datetime import datetime
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


def fetch_bytes(url: str, timeout: float = 5.0) -> bytes:
    with urlopen(url, timeout=timeout) as response:
        return response.read()


def fetch_json(url: str, timeout: float = 5.0) -> dict:
    raw = fetch_bytes(url, timeout=timeout)
    return json.loads(raw.decode("utf-8"))


def timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def collect_once(device: str, out_dir: Path, label: str) -> Path:
    sample_id = f"{timestamp()}_{label}"
    sample_dir = out_dir / sample_id
    sample_dir.mkdir(parents=True, exist_ok=True)

    image_url = f"{device}/capture-vga.jpg"
    stm32_url = f"{device}/stm32.json"
    health_url = f"{device}/health"

    image = fetch_bytes(image_url)
    (sample_dir / "capture.jpg").write_bytes(image)

    metadata = {
        "sample_id": sample_id,
        "device": device,
        "captured_at": datetime.now().isoformat(timespec="seconds"),
        "image_url": image_url,
    }

    for name, url in [("stm32", stm32_url), ("health", health_url)]:
        try:
            metadata[name] = fetch_json(url)
        except Exception as exc:
            metadata[name] = {"ok": False, "error": str(exc)}

    (sample_dir / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return sample_dir


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Collect ESP32 grape detector images and metadata."
    )
    parser.add_argument("--device", default="http://192.168.4.1")
    parser.add_argument("--out", default="data/samples")
    parser.add_argument("--label", default="grape")
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--interval", type=float, default=2.0)
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    for index in range(args.count):
        try:
            sample_dir = collect_once(args.device.rstrip("/"), out_dir, args.label)
            print(f"[OK] saved {sample_dir}")
        except (URLError, TimeoutError, OSError) as exc:
            print(f"[FAIL] collect failed: {exc}")

        if index + 1 < args.count:
            time.sleep(args.interval)


if __name__ == "__main__":
    main()
