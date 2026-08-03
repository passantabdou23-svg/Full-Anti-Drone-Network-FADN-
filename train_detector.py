"""
Fine-tunes a YOLOv8 detection model on the converted DUT-Anti-UAV dataset.

Requires: pip install ultralytics
Requires: prepare_dataset.py already run, producing yolo_dataset/data.yaml

USAGE:
    python train_detector.py --data ".\\yolo_dataset\\data.yaml" --model yolov8s.pt --epochs 80 --batch 32

Sized defaults below assume an RTX 2000 Ada (16GB VRAM). If you hit a
CUDA out-of-memory error, lower --batch (try 16, then 8) or switch
--model to yolov8n.pt (smaller/faster, slightly less accurate).
"""

import argparse
from ultralytics import YOLO


def main():
    parser = argparse.ArgumentParser(description="Fine-tune YOLOv8 on DUT-Anti-UAV")
    parser.add_argument("--data", required=True, help="Path to data.yaml produced by prepare_dataset.py")
    parser.add_argument("--model", default="yolov8s.pt",
                         help="Base pretrained checkpoint: yolov8n.pt (fastest), yolov8s.pt (balanced, default), yolov8m.pt (more accurate, slower)")
    parser.add_argument("--epochs", type=int, default=80)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=32)
    parser.add_argument("--device", default="0", help="'0' for first GPU, 'cpu' for CPU")
    parser.add_argument("--project", default="runs_dut_uav", help="Output folder for training runs")
    parser.add_argument("--name", default="yolov8_dut_finetune", help="Run name")
    args = parser.parse_args()

    print("=" * 70)
    print(f"Fine-tuning {args.model} on {args.data}")
    print(f"epochs={args.epochs} imgsz={args.imgsz} batch={args.batch} device={args.device}")
    print("=" * 70)

    # Loads pretrained COCO weights, then fine-tunes on our single-class UAV dataset.
    # ultralytics automatically downloads the base checkpoint the first time it's used.
    model = YOLO(args.model)

    model.train(
        data=args.data,
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=args.device,
        project=args.project,
        name=args.name,
        patience=20,        # early-stop if val performance plateaus for 20 epochs
        save=True,
        plots=True,          # saves precision/recall/mAP curves as images
        val=True,
    )

    # Run final evaluation explicitly on the held-out test split, if defined in data.yaml
    print("\nTraining complete. Running evaluation on validation set...")
    metrics = model.val()
    print(f"\nmAP50: {metrics.box.map50:.3f}")
    print(f"mAP50-95: {metrics.box.map:.3f}")
    print(f"\nBest weights saved to: {args.project}/{args.name}/weights/best.pt")
    print("Use this best.pt as your fine-tuned detector in the video pipeline (next step).")


if __name__ == "__main__":
    main()
