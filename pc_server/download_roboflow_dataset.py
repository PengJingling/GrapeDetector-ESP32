import argparse
import os
import shutil
import zipfile
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

try:
    import yaml
except Exception as exc:
    raise RuntimeError("Install PyYAML first: python -m pip install pyyaml") from exc


TARGET_NAMES = {
    0: "ripe_grape",
    1: "unripe_grape",
    2: "bad_grape",
}


def target_class_id(source_name: str) -> int | None:
    lower = source_name.lower().replace("-", "_").replace(" ", "_")

    if any(key in lower for key in ["bad", "rotten", "rot", "damaged", "damage", "disease", "busuk"]):
        return 2
    if any(key in lower for key in ["unripe", "immature", "green", "mentah"]):
        return 1
    if any(key in lower for key in ["ripe", "mature", "matang", "purple", "fully_ripe"]):
        return 0
    return None


def read_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def find_data_yaml(root: Path) -> Path:
    candidates = list(root.rglob("data.yaml"))
    if not candidates:
        candidates = list(root.rglob("*.yaml"))
    if not candidates:
        raise FileNotFoundError(f"No dataset yaml found under {root}")
    return candidates[0]


def names_to_list(names) -> list[str]:
    if isinstance(names, dict):
        return [str(names[key]) for key in sorted(names, key=lambda value: int(value))]
    return [str(item) for item in names]


def copy_images(src_images: Path, dst_images: Path) -> dict[str, str]:
    dst_images.mkdir(parents=True, exist_ok=True)
    copied = {}
    for image in src_images.glob("*"):
        if image.suffix.lower() not in [".jpg", ".jpeg", ".png", ".bmp"]:
            continue
        dst = dst_images / image.name
        if dst.exists():
            dst = dst_images / f"{image.stem}_{abs(hash(str(image))) & 0xffff:x}{image.suffix}"
        shutil.copy2(image, dst)
        copied[image.stem] = dst.stem
    return copied


def copy_labels(src_labels: Path, dst_labels: Path, stem_map: dict[str, str], source_names: list[str]) -> tuple[int, int]:
    dst_labels.mkdir(parents=True, exist_ok=True)
    kept = 0
    skipped = 0

    for label in src_labels.glob("*.txt"):
        dst_stem = stem_map.get(label.stem)
        if not dst_stem:
            continue

        out_lines = []
        for line in label.read_text(encoding="utf-8").splitlines():
            parts = line.strip().split()
            if len(parts) < 5:
                continue
            try:
                source_id = int(float(parts[0]))
            except ValueError:
                continue
            if source_id < 0 or source_id >= len(source_names):
                continue

            mapped_id = target_class_id(source_names[source_id])
            if mapped_id is None:
                skipped += 1
                continue

            parts[0] = str(mapped_id)
            out_lines.append(" ".join(parts))
            kept += 1

        if out_lines:
            (dst_labels / f"{dst_stem}.txt").write_text("\n".join(out_lines) + "\n", encoding="utf-8")

    return kept, skipped


def import_split(
    extract_root: Path,
    dataset_root: Path,
    source_split: str,
    target_split: str,
    source_names: list[str],
) -> tuple[int, int]:
    image_candidates = list(extract_root.rglob(f"images/{source_split}"))
    label_candidates = list(extract_root.rglob(f"labels/{source_split}"))
    if not image_candidates or not label_candidates:
        image_candidates = list(extract_root.rglob(f"{source_split}/images"))
        label_candidates = list(extract_root.rglob(f"{source_split}/labels"))
    if not image_candidates or not label_candidates:
        return 0, 0

    stem_map = copy_images(image_candidates[0], dataset_root / "images" / target_split)
    return copy_labels(label_candidates[0], dataset_root / "labels" / target_split, stem_map, source_names)


def write_target_yaml(path: Path, dataset_root: Path) -> None:
    data = {
        "path": str(dataset_root).replace("\\", "/"),
        "train": "images/train",
        "val": "images/val",
        "names": TARGET_NAMES,
    }
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Download a Roboflow YOLO dataset and map labels to grape classes.")
    parser.add_argument("--workspace", default="fruits-ripeness")
    parser.add_argument("--project", default="grape-unripe")
    parser.add_argument("--version", default="2")
    parser.add_argument("--format", default="yolov8")
    parser.add_argument("--api-key", default=os.getenv("ROBOFLOW_API_KEY", ""))
    parser.add_argument("--zip", default="", help="Import an already downloaded Roboflow YOLO zip file.")
    parser.add_argument("--download-url", default="", help="Use the Raw URL copied from Roboflow Download Dataset.")
    parser.add_argument("--dataset-root", default="datasets/grape")
    parser.add_argument("--output-yaml", default="datasets/grape.yaml")
    args = parser.parse_args()

    if not args.api_key and not args.zip and not args.download_url:
        raise SystemExit("Missing Roboflow API key. Use --api-key YOUR_KEY or set ROBOFLOW_API_KEY.")

    downloads = Path("downloads")
    downloads.mkdir(exist_ok=True)
    zip_path = downloads / f"{args.workspace}_{args.project}_v{args.version}_{args.format}.zip"
    extract_root = downloads / f"{args.workspace}_{args.project}_v{args.version}_{args.format}"

    if args.zip:
        zip_path = Path(args.zip)
        if not zip_path.exists():
            raise FileNotFoundError(f"Zip file not found: {zip_path}")
        print(f"Using local zip: {zip_path}")
    else:
        if args.download_url:
            url = args.download_url
        else:
            url = (
                f"https://universe.roboflow.com/{args.workspace}/{args.project}/dataset/{args.version}/download/{args.format}"
                f"?api_key={args.api_key}"
            )
        print(f"Downloading Roboflow dataset: {args.workspace}/{args.project}/{args.version}")
        try:
            with urlopen(url, timeout=120) as response:
                zip_path.write_bytes(response.read())
        except HTTPError as exc:
            if exc.code == 403:
                raise SystemExit(
                    "Roboflow returned 403 Forbidden.\n"
                    "This usually means your API key is not allowed to download this Universe dataset.\n"
                    "Fix: open the dataset page in Roboflow, click Download Dataset, choose YOLOv8,\n"
                    "then either copy the Raw URL and run:\n"
                    "  python pc_server\\download_roboflow_dataset.py --download-url \"PASTE_RAW_URL\"\n"
                    "or download the zip manually and run:\n"
                    "  python pc_server\\download_roboflow_dataset.py --zip C:\\path\\dataset.zip"
                ) from exc
            raise

    if extract_root.exists():
        shutil.rmtree(extract_root)
    extract_root.mkdir(parents=True)
    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(extract_root)

    data_yaml = find_data_yaml(extract_root)
    source_names = names_to_list(read_yaml(data_yaml).get("names", []))
    print("Source classes:")
    for index, name in enumerate(source_names):
        print(f"  {index}: {name} -> {TARGET_NAMES.get(target_class_id(name), 'skip')}")

    dataset_root = Path(args.dataset_root)
    kept_train, skipped_train = import_split(extract_root, dataset_root, "train", "train", source_names)
    kept_val, skipped_val = import_split(extract_root, dataset_root, "valid", "val", source_names)
    if kept_val == 0:
        kept_val, skipped_val = import_split(extract_root, dataset_root, "val", "val", source_names)

    write_target_yaml(Path(args.output_yaml), dataset_root)

    print(f"Imported train labels: kept={kept_train}, skipped={skipped_train}")
    print(f"Imported val labels: kept={kept_val}, skipped={skipped_val}")
    print(f"Dataset yaml: {args.output_yaml}")


if __name__ == "__main__":
    main()
