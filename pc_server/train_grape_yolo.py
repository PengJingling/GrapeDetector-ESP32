import argparse
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Train the grape-only YOLO model.")
    parser.add_argument("--data", default="datasets/grape.yaml")
    parser.add_argument("--model", default="yolov8n.pt")
    parser.add_argument("--epochs", type=int, default=80)
    parser.add_argument("--imgsz", type=int, default=960)
    parser.add_argument("--batch", type=int, default=4)
    args = parser.parse_args()

    try:
        from ultralytics import YOLO
    except Exception as exc:
        raise RuntimeError("Install first: python -m pip install ultralytics") from exc

    data_path = Path(args.data)
    if not data_path.exists():
        raise FileNotFoundError(f"Dataset yaml not found: {data_path}")

    model = YOLO(args.model)
    model.train(
        data=str(data_path),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        project="runs/grape",
        name="grape_yolov8n",
    )


if __name__ == "__main__":
    main()
