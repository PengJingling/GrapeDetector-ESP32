import argparse
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Train the grape berry YOLO model.")
    parser.add_argument("--data", default="datasets/grape.yaml")
    parser.add_argument("--model", default="yolov8n.pt")
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--imgsz", type=int, default=960)
    parser.add_argument("--batch", type=int, default=4)
    parser.add_argument("--project", default="runs/grape")
    parser.add_argument("--name", default="grape_berry_yolov8n")
    parser.add_argument("--copy-to", default="models/grape_yolo.pt")
    parser.add_argument("--degrees", type=float, default=8.0)
    parser.add_argument("--translate", type=float, default=0.08)
    parser.add_argument("--scale", type=float, default=0.45)
    parser.add_argument("--fliplr", type=float, default=0.5)
    parser.add_argument("--hsv-h", type=float, default=0.015)
    parser.add_argument("--hsv-s", type=float, default=0.45)
    parser.add_argument("--hsv-v", type=float, default=0.35)
    parser.add_argument("--mosaic", type=float, default=0.8)
    parser.add_argument("--close-mosaic", type=int, default=5)
    args = parser.parse_args()

    try:
        from ultralytics import YOLO
    except Exception as exc:
        raise RuntimeError("Install first: python -m pip install ultralytics") from exc

    data_path = Path(args.data)
    if not data_path.exists():
        raise FileNotFoundError(f"Dataset yaml not found: {data_path}")

    model = YOLO(args.model)
    result = model.train(
        data=str(data_path),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        project=args.project,
        name=args.name,
        degrees=args.degrees,
        translate=args.translate,
        scale=args.scale,
        fliplr=args.fliplr,
        hsv_h=args.hsv_h,
        hsv_s=args.hsv_s,
        hsv_v=args.hsv_v,
        mosaic=args.mosaic,
        close_mosaic=args.close_mosaic,
    )
    best = Path(result.save_dir) / "weights" / "best.pt"
    if best.exists() and args.copy_to:
        target = Path(args.copy_to)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(best.read_bytes())
        print(f"Copied best model to {target}")


if __name__ == "__main__":
    main()
