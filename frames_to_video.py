"""
Stitches a folder of sequentially-numbered real image frames (e.g. DUT-Anti-UAV
Tracking dataset's test/img folder: 00001.jpg, 00002.jpg, ...) into a single
real, playable .mp4 video file, in correct numeric order.

No synthetic content is created here -- every frame in the output video is a
real, unmodified frame from the dataset, just re-encoded as video instead of
loose images.

USAGE:
    python frames_to_video.py --frames_dir "PATH_TO_img_FOLDER" --out "OUTPUT_VIDEO_PATH.mp4" --fps 25
"""

import argparse
import os
import re
import cv2


def natural_sort_key(filename):
    """Sorts '2.jpg' before '10.jpg' correctly (not lexicographic '10' before '2')."""
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", filename)]


def main():
    parser = argparse.ArgumentParser(description="Stitch a real frame sequence into a real video file")
    parser.add_argument("--frames_dir", required=True, help="Folder containing sequential frame images")
    parser.add_argument("--out", default="./output_video.mp4", help="Output video path")
    parser.add_argument("--fps", type=float, default=25.0, help="Output video frame rate")
    parser.add_argument("--limit", type=int, default=None, help="Optional: only use first N frames (for a quick test)")
    args = parser.parse_args()

    if not os.path.isdir(args.frames_dir):
        raise SystemExit(f"ERROR: frames_dir not found: {args.frames_dir}")

    valid_ext = (".jpg", ".jpeg", ".png")
    files = [f for f in os.listdir(args.frames_dir) if f.lower().endswith(valid_ext)]
    if not files:
        raise SystemExit(f"ERROR: no image files found in {args.frames_dir}")

    files.sort(key=natural_sort_key)
    if args.limit:
        files = files[:args.limit]

    first_frame = cv2.imread(os.path.join(args.frames_dir, files[0]))
    if first_frame is None:
        raise SystemExit(f"ERROR: could not read first frame: {files[0]}")
    height, width = first_frame.shape[:2]

    out_dir = os.path.dirname(os.path.abspath(args.out))
    os.makedirs(out_dir, exist_ok=True)

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(args.out, fourcc, args.fps, (width, height))

    print(f"Stitching {len(files)} real frames from {args.frames_dir}")
    print(f"  Resolution: {width}x{height}  FPS: {args.fps}")

    written = 0
    skipped = 0
    for i, fname in enumerate(files, 1):
        frame = cv2.imread(os.path.join(args.frames_dir, fname))
        if frame is None:
            print(f"  [WARN] could not read {fname}, skipping")
            skipped += 1
            continue
        if frame.shape[:2] != (height, width):
            frame = cv2.resize(frame, (width, height))
        writer.write(frame)
        written += 1
        if i % 200 == 0 or i == len(files):
            print(f"  {i}/{len(files)} frames processed...")

    writer.release()

    duration_s = written / args.fps
    print("=" * 60)
    print(f"DONE: {written} real frames written ({skipped} skipped)")
    print(f"Video duration: {duration_s:.1f}s at {args.fps} FPS")
    print(f"Saved to: {os.path.abspath(args.out)}")
    print("=" * 60)


if __name__ == "__main__":
    main()
