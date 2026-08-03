"""
Converts the DUT-Anti-UAV detection dataset (Pascal VOC XML annotations)
into YOLO format (normalized x_center, y_center, width, height) so it can
be used to fine-tune a YOLOv8 detection model with the ultralytics library.

DUT-Anti-UAV annotation format (confirmed from a real sample file):

    <annotation>
        <size><width>550</width><height>412</height></size>
        <object>
            <name>UAV</name>
            <bndbox>
                <xmin>228</xmin><ymin>155</ymin>
                <xmax>353</xmax><ymax>245</ymax>
            </bndbox>
        </object>
    </annotation>

Only one class exists in this dataset ("UAV"), which we map to class_id 0
("drone") for YOLO training.

USAGE (run from the folder containing this script):

    python prepare_dataset.py --src "D:\\Project Data\\Trials\\Final XAI\\Passant\\DUT-Anti-UAV dataset folder\\DUT Anti-UAV Detection" --out ".\\yolo_dataset"

This will look for train/val/test subfolders under --src (each containing
an img/ folder and an xml/ folder, wherever they are nested -- the script
searches recursively so it doesn't matter if there's an extra nested
folder from the zip extraction), and produce:

    yolo_dataset/
        images/train/*.jpg
        images/val/*.jpg
        images/test/*.jpg
        labels/train/*.txt
        labels/val/*.txt
        labels/test/*.txt
        data.yaml

data.yaml is what you point ultralytics YOLO training at.
"""

import argparse
import os
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

CLASS_NAME = "drone"  # single class, mapped from DUT-Anti-UAV's "UAV" label
CLASS_ID = 0


def find_split_dirs(split_root: Path):
    """
    Given a split root folder (e.g. .../DUT Anti-UAV Detection/train), find the
    actual img/ and xml/ folders underneath it, however deeply nested.
    Returns (img_dir, xml_dir) as Path objects, or (None, None) if not found.
    """
    img_dir, xml_dir = None, None
    for root, dirs, _files in os.walk(split_root):
        base = os.path.basename(root).lower()
        if base == "img" and img_dir is None:
            img_dir = Path(root)
        if base == "xml" and xml_dir is None:
            xml_dir = Path(root)
    return img_dir, xml_dir


def convert_one_annotation(xml_path: Path, img_width_fallback=None, img_height_fallback=None):
    """
    Parses one VOC XML file and returns a list of YOLO-format label lines:
    "class_id x_center y_center width height" (all normalized 0-1).
    """
    tree = ET.parse(xml_path)
    root = tree.getroot()

    size_node = root.find("size")
    if size_node is not None:
        img_w = float(size_node.find("width").text)
        img_h = float(size_node.find("height").text)
    else:
        # Fall back to actual image dimensions if <size> is missing/corrupt
        if img_width_fallback is None or img_height_fallback is None:
            raise ValueError(f"No <size> in {xml_path} and no fallback provided")
        img_w, img_h = img_width_fallback, img_height_fallback

    lines = []
    for obj in root.findall("object"):
        name = obj.find("name").text.strip()
        # DUT-Anti-UAV only has "UAV" as a label; map anything present to our single class.
        # (defensive: if some other class name ever shows up, skip it rather than mislabel)
        if name.upper() != "UAV":
            continue

        bnd = obj.find("bndbox")
        xmin = float(bnd.find("xmin").text)
        ymin = float(bnd.find("ymin").text)
        xmax = float(bnd.find("xmax").text)
        ymax = float(bnd.find("ymax").text)

        # Clip to image bounds defensively (some datasets have off-by-a-few-px boxes)
        xmin = max(0.0, min(xmin, img_w))
        xmax = max(0.0, min(xmax, img_w))
        ymin = max(0.0, min(ymin, img_h))
        ymax = max(0.0, min(ymax, img_h))

        box_w = xmax - xmin
        box_h = ymax - ymin
        if box_w <= 0 or box_h <= 0:
            continue  # skip degenerate boxes

        x_center = (xmin + xmax) / 2.0 / img_w
        y_center = (ymin + ymax) / 2.0 / img_h
        norm_w = box_w / img_w
        norm_h = box_h / img_h

        lines.append(f"{CLASS_ID} {x_center:.6f} {y_center:.6f} {norm_w:.6f} {norm_h:.6f}")

    return lines


def convert_split(split_name: str, src_split_root: Path, out_root: Path):
    img_dir, xml_dir = find_split_dirs(src_split_root)
    if img_dir is None or xml_dir is None:
        print(f"  [SKIP] Could not find img/ and xml/ folders under {src_split_root}")
        return 0, 0

    out_img_dir = out_root / "images" / split_name
    out_lbl_dir = out_root / "labels" / split_name
    out_img_dir.mkdir(parents=True, exist_ok=True)
    out_lbl_dir.mkdir(parents=True, exist_ok=True)

    xml_files = sorted(xml_dir.glob("*.xml"))
    n_images, n_boxes = 0, 0

    for xml_path in xml_files:
        stem = xml_path.stem  # e.g. "00001"

        # Find the matching image (try common extensions)
        img_path = None
        for ext in (".jpg", ".jpeg", ".png", ".JPG", ".PNG"):
            candidate = img_dir / f"{stem}{ext}"
            if candidate.exists():
                img_path = candidate
                break
        if img_path is None:
            print(f"  [WARN] No matching image for {xml_path.name}, skipping")
            continue

        try:
            yolo_lines = convert_one_annotation(xml_path)
        except Exception as e:
            print(f"  [WARN] Failed to parse {xml_path.name}: {e}")
            continue

        # Copy image (hardlink would be faster, but copy is safest cross-filesystem)
        dest_img = out_img_dir / img_path.name
        if not dest_img.exists():
            shutil.copy2(img_path, dest_img)

        # Write YOLO label file (empty file if no valid boxes = background image, still valid for YOLO)
        dest_lbl = out_lbl_dir / f"{stem}.txt"
        with open(dest_lbl, "w") as f:
            f.write("\n".join(yolo_lines))

        n_images += 1
        n_boxes += len(yolo_lines)

    return n_images, n_boxes


def main():
    parser = argparse.ArgumentParser(description="Convert DUT-Anti-UAV VOC XML dataset to YOLO format")
    parser.add_argument("--src", required=True, help="Path to 'DUT Anti-UAV Detection' folder (containing train/val/test)")
    parser.add_argument("--out", default="./yolo_dataset", help="Output folder for YOLO-formatted dataset")
    args = parser.parse_args()

    src_root = Path(args.src)
    out_root = Path(args.out)
    out_root.mkdir(parents=True, exist_ok=True)

    if not src_root.exists():
        raise SystemExit(f"ERROR: --src path does not exist: {src_root}")

    splits = {
        "train": src_root / "train",
        "val": src_root / "val",
        "test": src_root / "test",
    }

    summary = {}
    for split_name, split_root in splits.items():
        if not split_root.exists():
            print(f"[{split_name}] folder not found at {split_root}, skipping")
            continue
        print(f"[{split_name}] converting from {split_root} ...")
        n_images, n_boxes = convert_split(split_name, split_root, out_root)
        summary[split_name] = (n_images, n_boxes)
        print(f"[{split_name}] done: {n_images} images, {n_boxes} UAV boxes")

    # Write data.yaml for ultralytics
    data_yaml_path = out_root / "data.yaml"
    with open(data_yaml_path, "w") as f:
        f.write(f"path: {out_root.resolve()}\n")
        f.write("train: images/train\n")
        f.write("val: images/val\n")
        if "test" in summary:
            f.write("test: images/test\n")
        f.write("names:\n")
        f.write(f"  0: {CLASS_NAME}\n")

    print("\n" + "=" * 60)
    print("CONVERSION SUMMARY")
    print("=" * 60)
    for split_name, (n_images, n_boxes) in summary.items():
        print(f"  {split_name:6s}: {n_images:5d} images, {n_boxes:5d} boxes")
    print(f"\ndata.yaml written to: {data_yaml_path.resolve()}")
    print("Ready for training.")


if __name__ == "__main__":
    main()
