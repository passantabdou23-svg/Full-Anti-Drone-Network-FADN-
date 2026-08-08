"""
Real video Detection + Tracking pipeline.

Loads the fine-tuned YOLOv8 drone detector (best.pt, trained on real DUT-Anti-UAV
data via prepare_dataset.py + train_detector.py) and runs it on an actual video
file, frame by frame. Real detections are fed into the existing ByteTracker
(src/bytetrack_tracker.py) to produce persistent track IDs across frames.

This replaces the synthetic/simulated detection path that main_pipeline.py used
(hand-scripted trajectories with added noise). Everything here comes from real
model inference on real video frames -- no fake numbers, no synthetic ground truth.

Outputs:
    <out>/annotated_video.mp4   - input video with drawn boxes + track IDs
    <out>/detections_tracks.json - per-frame detections, tracks, and SAPIENT ASM reports

USAGE:
    python detect_and_track_video.py --video "path\\to\\video.mp4" --weights ".\\runs_dut_uav\\yolov8_dut_finetune\\weights\\best.pt" --out ".\\video_results"

Optional flags:
    --conf 0.25       minimum detection confidence to keep (default 0.25)
    --imgsz 640       inference resolution (must match training imgsz for best results)
    --device 0        '0' for GPU, 'cpu' for CPU
    --no-video        skip writing the annotated video (JSON only, faster)
    --show            live-preview the annotated video in a window while processing
"""

import argparse
import json
import os
import time

import cv2

from ultralytics import YOLO

from kalman_filter import TrackKalmanFilterBank
from src.yolo_detector import OrientedBoundingBox
from src.bytetrack_tracker import ByteTracker
from src.identity_resolver import IdentityResolver
from src.sapient_protocol import SapientMessageBuilder


def yolo_results_to_obbs(result, conf_thresh):
    """
    Converts one ultralytics Results object (single frame) into a list of
    OrientedBoundingBox objects, reusing the SAME class main_pipeline.py /
    bytetrack_tracker.py / sapient_protocol.py already expect. Angle is always
    0.0 since the fine-tuned model is a standard axis-aligned YOLOv8 detector
    (the real DUT-Anti-UAV dataset has axis-aligned boxes, not rotated ones).
    """
    obbs = []
    if result.boxes is None:
        return obbs

    for box in result.boxes:
        conf = float(box.conf[0])
        if conf < conf_thresh:
            continue

        x1, y1, x2, y2 = [float(v) for v in box.xyxy[0]]
        w = x2 - x1
        h = y2 - y1
        if w <= 0 or h <= 0:
            continue
        x_center = x1 + w / 2.0
        y_center = y1 + h / 2.0
        cls_id = int(box.cls[0])

        obbs.append(OrientedBoundingBox(
            x_center=x_center,
            y_center=y_center,
            width=w,
            height=h,
            angle_deg=0.0,
            confidence=conf,
            class_id=cls_id,
            class_name="drone"
        ))
    return obbs


def draw_annotations(frame, tracks, kf_states=None, identity_assignments=None):
    """Draw boxes, operator-facing IDs and Kalman velocity vectors.

    Low-level tracker IDs remain immutable.  Confirmed identities are green,
    reidentified tracks are cyan, and unresolved temporary identities are
    orange so the operator can see that verification is still in progress.
    """
    kf_states = kf_states or {}
    identity_assignments = identity_assignments or {}
    for t in tracks:
        obb = t.obb
        x1 = int(obb.x_center - obb.width / 2)
        y1 = int(obb.y_center - obb.height / 2)
        x2 = int(obb.x_center + obb.width / 2)
        y2 = int(obb.y_center + obb.height / 2)

        identity = identity_assignments.get(t.track_id, {})
        status = identity.get("identity_status", "tracker_only")
        if status == "provisional":
            color = (0, 165, 255)  # orange
            display_id = identity.get("display_id", f"TEMP-{t.track_id}")
            label = f"{display_id} VERIFYING drone {t.score:.2f}"
        elif status == "reidentified":
            color = (255, 220, 0)  # cyan
            display_id = identity.get("display_id", f"ID-{t.track_id}")
            label = f"{display_id} RECOVERED drone {t.score:.2f}"
        else:
            color = (0, 220, 0)  # green
            display_id = identity.get("display_id", f"ID-{t.track_id}")
            label = f"{display_id} drone {t.score:.2f}"
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
        cv2.rectangle(frame, (x1, max(0, y1 - th - 8)), (x1 + tw + 4, y1), color, -1)
        cv2.putText(frame, label, (x1 + 2, max(12, y1 - 5)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 2, cv2.LINE_AA)

        # Real Kalman-filtered velocity vector (yellow arrow), scaled up for
        # visibility -- shows the TKF's actual predicted direction/speed
        kf = kf_states.get(t.track_id)
        if kf is not None:
            end_x = int(obb.x_center + kf["vx"] * 5)
            end_y = int(obb.y_center + kf["vy"] * 5)
            cv2.arrowedLine(frame, (int(obb.x_center), int(obb.y_center)),
                             (end_x, end_y), (0, 255, 255), 2, tipLength=0.3)
    return frame


def serialize_identity_track(track, assignment):
    """Preserve the internal track contract and add identity-layer fields."""

    result = track.to_dict()
    result["internal_track_id"] = int(track.track_id)
    result.update(assignment)
    result["sapient_object_id"] = assignment.get("display_id", f"ID-{track.track_id}")
    return result


def tracker_only_assignment(track):
    """Backward-compatible identity shape when reconciliation is disabled."""

    return {
        "internal_track_id": int(track.track_id),
        "identity_id": int(track.track_id),
        "display_id": f"ID-{track.track_id}",
        "identity_status": "tracker_only",
        "provisional_id": None,
        "identity_confidence": 1.0,
        "identity_source": "low_level_tracker",
    }


def main():
    parser = argparse.ArgumentParser(description="Run real YOLOv8 detection + ByteTrack tracking on a video")
    parser.add_argument("--video", required=True, help="Path to input video file")
    parser.add_argument("--weights", required=True, help="Path to fine-tuned best.pt")
    parser.add_argument("--out", default="./video_results", help="Output folder")
    parser.add_argument("--conf", type=float, default=0.25, help="Confidence threshold")
    parser.add_argument("--imgsz", type=int, default=640, help="Inference image size")
    parser.add_argument("--device", default="0", help="'0' for GPU, 'cpu' for CPU")
    parser.add_argument("--no-video", action="store_true", help="Skip writing annotated video (JSON only)")
    parser.add_argument("--show", action="store_true", help="Live preview while processing")
    parser.add_argument("--max_time_lost", type=int, default=90,
                         help="Frames a track can go undetected before it's permanently dropped "
                              "(raise this if a real object briefly loses detection and gets a new ID; "
                              "default 90 frames = ~3.6s at 25fps)")
    parser.add_argument("--search_radius_factor", type=float, default=4.0,
                         help="How far (in box-diagonals) a detection can be from a track's predicted "
                              "position and still count as the same object. Raise for fast/erratic motion, "
                              "lower if multiple close targets keep swapping IDs.")
    parser.add_argument("--kf_process_noise", type=float, default=2.0,
                         help="Kalman filter process noise std-dev (px/frame^2). Higher = trust the "
                              "constant-velocity motion model less, adapt to raw detections faster.")
    parser.add_argument("--kf_measurement_noise", type=float, default=3.0,
                         help="Kalman filter measurement noise std-dev (px). Higher = trust the raw "
                              "detector's box center less, smooth more heavily.")
    parser.add_argument("--disable_identity_resolver", action="store_true",
                         help="Disable provisional/dormant identity reconciliation and display raw tracker IDs.")
    parser.add_argument("--identity_retention_seconds", type=float, default=10.0,
                         help="Seconds to retain a dormant confirmed identity for possible re-identification.")
    parser.add_argument("--identity_confirm_frames", type=int, default=8,
                         help="Evidence frames collected before a temporary identity may be reconciled.")
    parser.add_argument("--identity_max_provisional_frames", type=int, default=24,
                         help="Maximum evidence frames before an unmatched temporary identity becomes permanent.")
    parser.add_argument("--identity_match_threshold", type=float, default=0.62,
                         help="Maximum hybrid match cost for restoring a dormant identity (lower is stricter).")
    args = parser.parse_args()

    if not os.path.exists(args.video):
        raise SystemExit(f"ERROR: video not found: {args.video}")
    if not os.path.exists(args.weights):
        raise SystemExit(f"ERROR: weights not found: {args.weights}")

    os.makedirs(args.out, exist_ok=True)

    print("=" * 70)
    print(f"Loading model: {args.weights}")
    model = YOLO(args.weights)

    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        raise SystemExit(f"ERROR: could not open video: {args.video}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    print(f"Video: {args.video}")
    print(f"  {width}x{height} @ {fps:.1f} FPS, ~{total_frames} frames")
    print("=" * 70)

    writer = None
    if not args.no_video:
        out_video_path = os.path.join(args.out, "annotated_video.mp4")
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(out_video_path, fourcc, fps, (width, height))

    tracker = ByteTracker(
        high_thresh=0.5,
        low_thresh=0.2,
        max_time_lost=args.max_time_lost,
        search_radius_factor=args.search_radius_factor
    )

    # Track Kalman Filter (TKF) -- real per-track state estimation/smoothing.
    # Single-sensor (EO/IR only): see src/kalman_filter.py docstring for why
    # this is not "multi-sensor fusion" despite the project's original goal
    # of a TKF stage -- there is no second real sensor to fuse with here.
    kf_bank = TrackKalmanFilterBank(
        process_noise_std=args.kf_process_noise,
        measurement_noise_std=args.kf_measurement_noise
    )

    identity_resolver = None
    if not args.disable_identity_resolver:
        identity_resolver = IdentityResolver(
            fps=fps,
            retention_seconds=args.identity_retention_seconds,
            confirm_frames=args.identity_confirm_frames,
            max_provisional_frames=args.identity_max_provisional_frames,
            match_threshold=args.identity_match_threshold,
        )
        print(
            "Identity resolver: enabled "
            f"(retention={identity_resolver.retention_frames} frames / "
            f"{identity_resolver.retention_seconds:.1f}s, "
            f"confirm={identity_resolver.confirm_frames} frames)"
        )
    else:
        print("Identity resolver: disabled (raw tracker IDs only)")

    frame_records = []
    frame_id = 0
    t_start = time.time()

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        frame_id += 1

        t0 = time.time()
        results = model.predict(
            source=frame,
            imgsz=args.imgsz,
            conf=args.conf,
            device=args.device,
            verbose=False
        )
        infer_ms = (time.time() - t0) * 1000.0

        obbs = yolo_results_to_obbs(results[0], args.conf)
        active_tracks = tracker.update(obbs)

        # Track Kalman Filter step: real predict+update per active track,
        # producing a smoothed position and a genuine velocity estimate
        # (see src/kalman_filter.py for the standard KF math and a
        # self-test proving it measurably reduces position noise).
        kf_states = kf_bank.step(active_tracks)

        if identity_resolver is not None:
            identity_assignments, identity_events = identity_resolver.step(
                frame_id, frame, active_tracks, kf_states
            )
        else:
            identity_assignments = {
                track.track_id: tracker_only_assignment(track) for track in active_tracks
            }
            identity_events = []

        identity_tracks = [
            serialize_identity_track(track, identity_assignments[track.track_id])
            for track in active_tracks
        ]

        # Real SAPIENT-formatted sensor report from real EO/IR detections+tracks
        asm_eoir = SapientMessageBuilder.create_autonomous_sensor_report(
            "EOIR-CAM-01", "EO/IR_YOLOv8_FineTuned", identity_tracks
        )

        frame_records.append({
            "frame_id": frame_id,
            "inference_speed_ms": round(infer_ms, 1),
            "detections": [o.to_dict() for o in obbs],
            "tracks": identity_tracks,
            "kalman_filter_states": kf_states,  # {track_id: {x,y,vx,vy,position_uncertainty_px,...}}
            "identity_events": identity_events,
            "sapient_asm_eoir": asm_eoir
        })

        if writer is not None or args.show:
            annotated = draw_annotations(
                frame.copy(), active_tracks, kf_states, identity_assignments
            )
            if writer is not None:
                writer.write(annotated)
            if args.show:
                cv2.imshow("Detection + Tracking", annotated)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break

        if frame_id % 30 == 0 or frame_id == total_frames:
            elapsed = time.time() - t_start
            print(f"  frame {frame_id}/{total_frames}  "
                  f"detections={len(obbs)}  active_tracks={len(active_tracks)}  "
                  f"infer={infer_ms:.1f}ms  elapsed={elapsed:.1f}s")

    cap.release()
    if writer is not None:
        writer.release()
    if args.show:
        cv2.destroyAllWindows()

    total_elapsed = time.time() - t_start
    total_dets = sum(len(f["detections"]) for f in frame_records)
    internal_track_ids = {
        t["internal_track_id"] for f in frame_records for t in f["tracks"]
    }
    total_tracks_seen = len(internal_track_ids)

    if identity_resolver is not None:
        final_events = identity_resolver.finalize(frame_id)
        if final_events and frame_records:
            frame_records[-1]["identity_events"].extend(final_events)
        for frame_record in frame_records:
            frame_record["tracks"] = [
                identity_resolver.apply_final_alias(track)
                for track in frame_record["tracks"]
            ]
        identity_summary = identity_resolver.summary()
    else:
        identity_summary = {
            "confirmed_identity_count": total_tracks_seen,
            "temporary_identity_count": 0,
            "temporal_model": "disabled",
            "identity_aliases": {},
            "event_counts": {},
        }

    json_out_path = os.path.join(args.out, "detections_tracks.json")
    export = {
        "metadata": {
            "video_source": os.path.abspath(args.video),
            "weights_used": os.path.abspath(args.weights),
            "conf_threshold": args.conf,
            "total_frames_processed": frame_id,
            "total_processing_time_s": round(total_elapsed, 1),
            "avg_fps_processing": round(frame_id / total_elapsed, 1) if total_elapsed > 0 else 0,
            "total_detections": total_dets,
            "unique_tracks_seen": total_tracks_seen,
            "unique_internal_tracks_seen": total_tracks_seen,
            "unique_confirmed_identities": identity_summary["confirmed_identity_count"]
        },
        "identity_summary": identity_summary,
        "frames": frame_records
    }
    with open(json_out_path, "w") as f:
        json.dump(export, f, indent=2)

    print("=" * 70)
    print("DONE")
    print(f"  Frames processed: {frame_id}")
    print(f"  Total detections: {total_dets}")
    print(f"  Unique internal tracks seen: {total_tracks_seen}")
    print(f"  Confirmed identities: {identity_summary['confirmed_identity_count']}")
    print(f"  Temporary identities created: {identity_summary['temporary_identity_count']}")
    print(f"  Re-identifications: {identity_summary['event_counts'].get('identity_reidentified', 0)}")
    print(f"  Processing speed: {frame_id / total_elapsed:.1f} FPS" if total_elapsed > 0 else "")
    if writer is not None:
        print(f"  Annotated video saved to: {os.path.join(args.out, 'annotated_video.mp4')}")
    print(f"  JSON results saved to: {json_out_path}")
    print("=" * 70)


if __name__ == "__main__":
    main()
