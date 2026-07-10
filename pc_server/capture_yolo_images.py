import argparse
import time
from datetime import datetime
from pathlib import Path
from urllib.request import urlopen


def fetch_bytes(url: str, timeout: float = 8.0) -> bytes:
    with urlopen(url, timeout=timeout) as response:
        return response.read()


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture ESP32 images for YOLO labeling.")
    parser.add_argument("--device", default="http://192.168.4.1")
    parser.add_argument("--image-endpoint", default="capture-xga.jpg")
    parser.add_argument("--split", choices=["train", "val"], default="train")
    parser.add_argument("--count", type=int, default=30)
    parser.add_argument("--interval", type=float, default=1.5)
    args = parser.parse_args()

    out_dir = Path("datasets/grape/images") / args.split
    out_dir.mkdir(parents=True, exist_ok=True)

    for index in range(args.count):
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        image_path = out_dir / f"grape_{args.split}_{stamp}.jpg"
        url = f"{args.device.rstrip('/')}/{args.image_endpoint.lstrip('/')}"
        image_path.write_bytes(fetch_bytes(url))
        print(f"[{index + 1}/{args.count}] saved {image_path}")
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
