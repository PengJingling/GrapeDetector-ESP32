import argparse
import re
import shutil
import zipfile
from pathlib import Path

try:
    import yaml
except Exception as exc:
    raise RuntimeError("Install PyYAML first: python -m pip install pyyaml") from exc


TARGET_NAMES = {
    0: "ripe_grape",
    1: "unripe_grape",
    2: "bad_grape",
}


def parse_label_map(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    names: dict[int, str] = {}
    for block in re.findall(r"item\s*\{(.*?)\}", text, flags=re.S):
        id_match = re.search(r"\bid\s*:\s*(\d+)", block)
        name_match = re.search(r"\bname\s*:\s*['\"]([^'\"]+)['\"]", block)
        if id_match and name_match:
            names[int(id_match.group(1))] = name_match.group(1)
    if names:
        start = 1 if min(names) == 1 else 0
        return [names[index] for index in range(start, max(names) + 1) if index in names]

    simple_names = re.findall(r"name\s*:\s*['\"]([^'\"]+)['\"]", text)
    if simple_names:
        return simple_names
    raise ValueError(f"Could not parse class names from {path}")


def target_class_id(source_name: str) -> int | None:
    lower = source_name.lower().replace("-", "_").replace(" ", "_")
    if any(key in lower for key in ["unripe", "immature", "green"]):
        return 1
    if any(key in lower for key in ["healthy", "normal", "good", "optimal", "ripe", "mature"]):
        return 0
    if any(
        key in lower
        for key in [
            "bad",
            "rotten",
            "rot",
            "damaged",
            "damage",
            "disease",
            "dry",
            "dried",
            "shrivel",
            "sunburn",
            "mold",
            "infect",
            "defect",
            "crack",
        ]
    ):
        return 2
    return 2


def find_dataset_root(extract_root: Path) -> Path:
    candidates = [path.parent for path in extract_root.rglob("label_map.pbtx")]
    candidates += [path.parent for path in extract_root.rglob("label_map.pbtxt")]
    candidates += [path.parent for path in extract_root.rglob("lable_map.pbtx")]
    candidates += [path.parent for path in extract_root.rglob("lable_map.pbtxt")]
    if candidates:
        return candidates[0]
    for path in extract_root.rglob("*"):
        if path.is_dir() and (path / "train").exists() and (path / "val").exists():
            return path
    raise FileNotFoundError(f"Could not find extracted Zenodo dataset root under {extract_root}")


def copy_split(source_root: Path, target_root: Path, split: str, class_names: list[str]) -> tuple[int, int]:
    src_images = source_root / split / "images"
    src_labels = source_root / split / "labels"
    dst_images = target_root / "images" / split
    dst_labels = target_root / "labels" / split
    dst_images.mkdir(parents=True, exist_ok=True)
    dst_labels.mkdir(parents=True, exist_ok=True)

    copied_images = 0
    copied_boxes = 0
    for image in src_images.glob("*"):
        if image.suffix.lower() not in [".jpg", ".jpeg", ".png", ".bmp"]:
            continue
        shutil.copy2(image, dst_images / image.name)
        copied_images += 1

        label = src_labels / f"{image.stem}.txt"
        if not label.exists():
            continue

        out_lines = []
        for line in label.read_text(encoding="utf-8").splitlines():
            parts = line.strip().split()
            if len(parts) < 5:
                continue
            source_id = int(float(parts[0]))
            if source_id >= len(class_names) and source_id - 1 >= 0:
                source_id -= 1
            if source_id < 0 or source_id >= len(class_names):
                continue
            target_id = target_class_id(class_names[source_id])
            if target_id is None:
                continue
            parts[0] = str(target_id)
            out_lines.append(" ".join(parts))
            copied_boxes += 1
        if out_lines:
            (dst_labels / f"{image.stem}.txt").write_text("\n".join(out_lines) + "\n", encoding="utf-8")

    return copied_images, copied_boxes


def write_yaml(output_yaml: Path, dataset_root: Path) -> None:
    data = {
        "path": str(dataset_root).replace("\\", "/"),
        "train": "images/train",
        "val": "images/val",
        "names": TARGET_NAMES,
    }
    output_yaml.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Import Zenodo Grapevine Bunch Condition dataset.")
    parser.add_argument("--zip", default="downloads/GrapevineBunchConditionDetection.zip")
    parser.add_argument("--dataset-root", default="datasets/grape_zenodo")
    parser.add_argument("--output-yaml", default="datasets/grape_zenodo.yaml")
    parser.add_argument("--clear", action="store_true")
    args = parser.parse_args()

    zip_path = Path(args.zip)
    if not zip_path.exists():
        raise FileNotFoundError(zip_path)

    extract_root = Path("downloads") / "GrapevineBunchConditionDetection"
    if extract_root.exists():
        shutil.rmtree(extract_root)
    extract_root.mkdir(parents=True)
    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(extract_root)

    source_root = find_dataset_root(extract_root)
    label_maps = list(source_root.glob("label_map.pbt*")) + list(source_root.glob("lable_map.pbt*"))
    if not label_maps:
        raise FileNotFoundError(f"No label map found under {source_root}")
    label_map = label_maps[0]
    class_names = parse_label_map(label_map)
    print("Source classes:")
    for index, name in enumerate(class_names):
        print(f"  {index}: {name} -> {TARGET_NAMES[target_class_id(name)]}")

    target_root = Path(args.dataset_root)
    if args.clear and target_root.exists():
        shutil.rmtree(target_root)

    for source_split, target_split in [("train", "train"), ("val", "val")]:
        images, boxes = copy_split(source_root, target_root, source_split, class_names)
        print(f"Imported {target_split}: images={images}, boxes={boxes}")

    write_yaml(Path(args.output_yaml), target_root)
    print(f"Dataset yaml: {args.output_yaml}")


if __name__ == "__main__":
    main()
