import argparse
import random
import shutil
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageOps


IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp"}


def image_feature(path: Path) -> np.ndarray:
    img = Image.open(path).convert("RGB")
    img.thumbnail((160, 160))
    arr = np.asarray(img, dtype=np.float32) / 255.0
    hsv = np.asarray(img.convert("HSV"), dtype=np.float32) / 255.0
    mean_rgb = arr.reshape(-1, 3).mean(axis=0)
    std_rgb = arr.reshape(-1, 3).std(axis=0)
    mean_hsv = hsv.reshape(-1, 3).mean(axis=0)
    bright = arr.mean()
    white_ratio = np.mean(np.all(arr > 0.78, axis=2))
    red_ratio = np.mean((arr[:, :, 0] > arr[:, :, 1] * 1.12) & (arr[:, :, 0] > arr[:, :, 2] * 1.05))
    return np.concatenate([mean_rgb, std_rgb, mean_hsv, [bright, white_ratio, red_ratio]])


def class_set(label_path: Path) -> set[int]:
    classes: set[int] = set()
    if not label_path.exists():
        return classes
    for line in label_path.read_text(errors="ignore").splitlines():
        parts = line.strip().split()
        if parts:
            try:
                classes.add(int(float(parts[0])))
            except ValueError:
                pass
    return classes


def remap_label(src: Path, dst: Path) -> bool:
    kept = []
    for line in src.read_text(errors="ignore").splitlines():
        parts = line.strip().split()
        if len(parts) < 5:
            continue
        old_cls = int(float(parts[0]))
        if old_cls == 0:
            parts[0] = "0"
        elif old_cls == 2:
            parts[0] = "1"
        else:
            continue
        kept.append(" ".join(parts))
    if not kept:
        return False
    dst.write_text("\n".join(kept) + "\n", encoding="utf-8")
    return True


def copy_split(items, out_root: Path, split: str):
    img_out = out_root / "images" / split
    lab_out = out_root / "labels" / split
    img_out.mkdir(parents=True, exist_ok=True)
    lab_out.mkdir(parents=True, exist_ok=True)
    copied = 0
    for image_path, label_path, _score in items:
        dst_img = img_out / image_path.name
        dst_lab = lab_out / (image_path.stem + ".txt")
        if remap_label(label_path, dst_lab):
            shutil.copy2(image_path, dst_img)
            copied += 1
    return copied


def make_contact_sheet(items, out_file: Path, title: str, max_items: int = 24):
    thumbs = []
    for image_path, _label_path, score in items[:max_items]:
        img = Image.open(image_path).convert("RGB")
        img = ImageOps.contain(img, (220, 160), Image.Resampling.LANCZOS)
        tile = Image.new("RGB", (220, 190), "white")
        tile.paste(img, ((220 - img.width) // 2, 0))
        draw = ImageDraw.Draw(tile)
        draw.text((4, 164), f"{score:.3f} {image_path.name[:22]}", fill=(0, 0, 0))
        thumbs.append(tile)
    if not thumbs:
        return
    cols = 4
    rows = (len(thumbs) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * 220, rows * 190 + 28), "white")
    draw = ImageDraw.Draw(sheet)
    draw.text((8, 6), title, fill=(0, 0, 0))
    for i, tile in enumerate(thumbs):
        x = (i % cols) * 220
        y = 28 + (i // cols) * 190
        sheet.paste(tile, (x, y))
    out_file.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out_file, quality=92)


def main():
    parser = argparse.ArgumentParser(description="Build a good/bad grape subset visually similar to an ESP32 capture.")
    parser.add_argument("--source", default="datasets/grape_zenodo")
    parser.add_argument("--reference", default="pc_server/current_esp32_capture.jpg")
    parser.add_argument("--out", default="datasets/grape_badfruit_similar")
    parser.add_argument("--per-class", type=int, default=180)
    parser.add_argument("--val-ratio", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    random.seed(args.seed)
    source = Path(args.source)
    ref = Path(args.reference)
    out_root = Path(args.out)
    if not source.exists():
        raise FileNotFoundError(source)
    if not ref.exists():
        raise FileNotFoundError(ref)

    ref_feat = image_feature(ref)
    candidates = {0: [], 2: []}
    for split in ("train", "val"):
        img_dir = source / "images" / split
        lab_dir = source / "labels" / split
        if not img_dir.exists():
            continue
        for image_path in img_dir.iterdir():
            if image_path.suffix.lower() not in IMAGE_EXTS:
                continue
            label_path = lab_dir / (image_path.stem + ".txt")
            classes = class_set(label_path)
            target_cls = 2 if 2 in classes else 0 if 0 in classes else None
            if target_cls is None:
                continue
            try:
                feat = image_feature(image_path)
            except Exception:
                continue
            score = float(np.linalg.norm((feat - ref_feat) * np.array([1, 1, 1, 0.6, 0.6, 0.6, 1, 0.7, 0.7, 0.9, 1.4, 1.2])))
            candidates[target_cls].append((image_path, label_path, score))

    selected = []
    for cls in (0, 2):
        ranked = sorted(candidates[cls], key=lambda x: x[2])[: args.per_class]
        selected.extend(ranked)

    random.shuffle(selected)
    val_count = max(1, int(len(selected) * args.val_ratio))
    val_items = selected[:val_count]
    train_items = selected[val_count:]

    if out_root.exists():
        shutil.rmtree(out_root)
    n_train = copy_split(train_items, out_root, "train")
    n_val = copy_split(val_items, out_root, "val")

    yaml_path = out_root.with_suffix(".yaml")
    yaml_path.write_text(
        f"path: {out_root.as_posix()}\n"
        "train: images/train\n"
        "val: images/val\n"
        "names:\n"
        "  0: good_grape\n"
        "  1: bad_grape\n",
        encoding="utf-8",
    )

    preview_dir = Path("pc_server/preview")
    make_contact_sheet(sorted(candidates[0], key=lambda x: x[2]), preview_dir / "similar_good_candidates.jpg", "similar good_grape candidates")
    make_contact_sheet(sorted(candidates[2], key=lambda x: x[2]), preview_dir / "similar_bad_candidates.jpg", "similar bad_grape candidates")

    print(f"Created {yaml_path}")
    print(f"train images: {n_train}")
    print(f"val images: {n_val}")
    print(f"good candidates: {len(candidates[0])}, bad candidates: {len(candidates[2])}")
    print(f"preview: {preview_dir / 'similar_good_candidates.jpg'}")
    print(f"preview: {preview_dir / 'similar_bad_candidates.jpg'}")


if __name__ == "__main__":
    main()
