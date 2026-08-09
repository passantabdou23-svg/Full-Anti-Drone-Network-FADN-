# Drone Detection & Tracking Pipeline (YOLOv8 + ByteTrack)

Real-time drone detection and multi-object tracking on video, using a YOLOv8
detector fine-tuned on the [DUT-Anti-UAV](https://github.com/wangdongdut/DUT-Anti-UAV)
dataset, with a custom ByteTrack-style tracker for persistent track IDs across frames.

Upload any video → get an annotated output video (bounding boxes + track IDs)
and a structured JSON log of every detection and track, per frame.

## Real, measured results (not simulated)

The detector was fine-tuned from `yolov8s.pt` on the real DUT-Anti-UAV
Detection split (5,200 train / 2,600 val / 2,200 test images, Pascal VOC
annotations converted to YOLO format), for 80 epochs on an RTX 2000 Ada (16GB).

| Metric | Value |
|---|---|
| mAP50 | 0.907 |
| mAP50-95 | 0.577 |
| Precision | 0.956 |
| Recall | 0.868 |
| Inference speed | ~2.1 ms/image (GPU) |

These numbers come directly from Ultralytics' validation run on the held-out
validation split — see `runs/detect/.../results.png` after training for the
full curves. No numbers in this repo are hand-picked or simulated.

**Note on box type:** the DUT-Anti-UAV dataset provides axis-aligned bounding
boxes (`xmin/ymin/xmax/ymax`), not rotated/oriented boxes. This project
therefore trains a standard YOLOv8 detector (angle always 0°), not a true
YOLOv8-OBB model. Any earlier reference to "OBB" in this codebase reflects
that constraint being fixed to standard axis-aligned detection.

## What's real vs. what's a placeholder

This repo grew out of an earlier prototype that generated a fully synthetic
demo feed (hand-scripted trajectories, hard-coded benchmark numbers) to drive
a dashboard mockup. Being transparent about what's real:

| Component | Status |
|---|---|
| YOLOv8 detector (`src/yolo_detector.py` inference path, `models/best.pt`) | **Real**, trained on real data (see table above) |
| ByteTrack-style tracker (`src/bytetrack_tracker.py`) | **Real**, motion-predicted matching + lost-track revival, tested on real video |
| Identity reconciliation (`src/identity_resolver.py`) | **Real**, assigns `TEMP-n` while comparing a new internal track with dormant identities, then restores the old `ID-n` or promotes a new permanent ID |
| `detect_and_track_video.py` | **Real** end-to-end pipeline: real video in, real detections/tracks out |
| `frames_to_video.py` | **Real** utility to stitch a real dataset frame sequence into a playable video |
| SAPIENT (STANAG 4810) message formatting (`src/sapient_protocol.py`) | Real data formatting, fed by real detections/tracks when used with `detect_and_track_video.py` |
| Radar simulation, RF/acoustic fusion, `main_pipeline.py` | **Simulated / placeholder.** No real radar/RF hardware or dataset is used. Kept for architectural completeness and future work; not used by the real video pipeline. |
| Web dashboard (`index.html`, `app.js`) | Currently wired to the simulated `simulation_feed.json`. Wiring it to real `detections_tracks.json` output is a planned next step. |

## Quickstart

### 1. Environment setup

```bash
git clone https://github.com/<your-username>/<your-repo>.git
cd <your-repo>
python -m venv .venv
# Windows:
.\.venv\Scripts\Activate.ps1
# macOS/Linux:
source .venv/bin/activate

# Upgrade packaging tools inside the virtual environment.
python -m pip install --upgrade pip

# Install PyTorch FIRST using the command generated for your OS and CPU/CUDA
# platform at https://pytorch.org/get-started/locally/. For a CPU-only setup:
python -m pip install torch torchvision

# Install this project's direct runtime dependencies.
python -m pip install -r requirements.txt

# Verify imports and see whether PyTorch can use your GPU.
python check_environment.py
```

Use `--device cpu` when `check_environment.py` reports that CUDA is not
available. For an NVIDIA GPU, use the CUDA-specific PyTorch command generated
by the official PyTorch installer instead of guessing a CUDA wheel version.

Run the focused regression suite before processing a video:

```bash
python -m unittest discover -s tests -v
```

For the complete CPU/GPU, headless-server, dashboard, and verification steps,
see [DEPLOYMENT.md](DEPLOYMENT.md).

### 2. Run detection + tracking on your own video

The fine-tuned weights are already included at `models/best.pt` — no training
required to try it out.

```bash
python detect_and_track_video.py \
    --video "path/to/your_video.mp4" \
    --weights "models/best.pt" \
    --out "./video_results"
```

Outputs:
- `video_results/annotated_video.mp4` — your video with drawn boxes + track IDs
- `video_results/detections_tracks.json` — full per-frame detection/track/SAPIENT data

Identity labels in the annotated video have explicit states:

- `ID-n` (green): confirmed identity.
- `TEMP-n VERIFYING` (orange): evidence is still being collected.
- `ID-n RECOVERED` (cyan): a new internal track was matched to a dormant identity.

The JSON keeps both `internal_track_id` (immutable tracker history) and the
operator-facing identity fields. It also records identity lifecycle events and
the final alias, for example `TEMP-1 -> ID-1`. See
[IDENTITY_RECONCILIATION.md](IDENTITY_RECONCILIATION.md) for the state machine,
scoring method, tuning guidance, and measured validation.

Useful flags:
```
--conf 0.25                 minimum detection confidence to keep
--imgsz 640                 inference resolution
--device 0                  '0' for GPU, 'cpu' for CPU
--max_time_lost 90          frames a track can go undetected before it's dropped
--search_radius_factor 4.0  how far (in box-diagonals) a detection can be from
                             a track's predicted position and still be matched
--identity_retention_seconds 10  dormant-identity memory duration
--identity_confirm_frames 8     evidence frames before an old ID may be restored
--identity_max_provisional_frames 24  unmatched TEMP promotion deadline
--identity_match_threshold 0.62  maximum hybrid match cost; lower is stricter
--disable_identity_resolver     use raw tracker IDs only
--show                      live preview while processing
```

### 3. (Optional) Retrain the detector yourself

Download [DUT-Anti-UAV](https://github.com/wangdongdut/DUT-Anti-UAV) (Detection
split), then:

```bash
python prepare_dataset.py --src "path/to/DUT Anti-UAV Detection" --out "./yolo_dataset"
python train_detector.py --data "./yolo_dataset/data.yaml" --model yolov8s.pt --epochs 80 --batch 32
```

### 4. (Optional) Build a test video from a raw frame sequence

If you have a folder of sequential frame images instead of a video file:

```bash
python frames_to_video.py --frames_dir "path/to/img_folder" --out "./my_video.mp4" --fps 25
```

## Repository structure

```
.
├── detect_and_track_video.py   # Main entry point: real video → detection + tracking
├── frames_to_video.py          # Utility: stitch real frame sequences into a video
├── prepare_dataset.py          # Converts DUT-Anti-UAV VOC XML → YOLO format
├── train_detector.py           # Fine-tunes YOLOv8 on the converted dataset
├── main_pipeline.py            # Legacy simulated demo pipeline (see table above)
├── kalman_filter.py            # Per-track 2D constant-velocity Kalman filter
├── models/
│   └── best.pt                 # Fine-tuned detector weights (real, trained)
├── src/
│   ├── __init__.py             # Explicit Python package marker
│   ├── yolo_detector.py        # OrientedBoundingBox class + detector benchmark data
│   ├── bytetrack_tracker.py    # Motion-predicted tracker with lost-track revival
│   ├── identity_resolver.py    # TEMP/confirmed identity reconciliation layer
│   ├── sapient_protocol.py     # NATO SAPIENT (STANAG 4810) message formatting
│   ├── sensor_fusion.py        # [placeholder] simulated multi-sensor fusion
│   └── radar_simulator.py      # [placeholder] simulated radar returns
├── index.html / app.js / styles.css   # Web dashboard (currently demo-fed)
└── requirements.txt
```

## Known limitations

- Single class only (`drone`) — no classification of drone type/model.
- Axis-aligned boxes only, not true oriented/rotated boxes.
- Tracker is a simplified, from-scratch ByteTrack-style implementation, not the
  official `bytetrack` package. It uses tracker motion prediction plus a
  separate per-track Kalman estimator; IoU assists disambiguation.
- Long-gap identity reconciliation uses deterministic motion/Kalman, appearance,
  size, and elapsed-time evidence. The LSTM interface is present, but no LSTM is
  claimed or enabled until a temporal model is trained and validated on
  identity-labelled trajectories.
- Performance on footage outside the DUT-Anti-UAV domain (different camera
  angles, drone types, or backgrounds) has not been benchmarked — expect lower
  recall on genuinely out-of-distribution video.
- Radar/RF/acoustic sensor fusion is simulated, not connected to real hardware
  or datasets.

## License

Code in this repository: MIT (adjust as needed).
Dataset: DUT-Anti-UAV is provided by its original authors under their own
license/terms — see [their repository](https://github.com/wangdongdut/DUT-Anti-UAV)
before redistributing any dataset content.
