"""
Converts real detect_and_track_video.py output (detections_tracks.json) into
the dashboard's expected feed format (simulation_feed.json), so the web
dashboard (index.html/app.js) displays REAL detection/tracking results
instead of the old simulated demo data.

Honest scope: this pipeline has no radar, RF, or acoustic sensor, and no
georeferencing (no camera survey / GNSS), so:
  - "radar_detections" is written as an empty list every frame (real absence
    of data, not simulated blips)
  - "fused_threat_picture" is built from REAL EO/IR tracks only -- there is
    no second sensor to fuse with, so sensor_sources is always ["EO/IR"],
    never a fabricated multi-sensor correlation
  - "pos_3d" range in real-world metres is not available (no georeferencing
    step converts pixels to metres) -- this field is omitted rather than
    filled with a fake number; the dashboard has been patched to show "N/A"
    rather than "undefined" when it's missing

USAGE:
    python export_for_dashboard.py --input ".\\video_results\\detections_tracks.json" --out ".\\simulation_feed.json"

After running this, refresh the dashboard (index.html, served over
http://localhost:PORT, not file://) to see real results.
"""

import argparse
import json
import os
import sys

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))
try:
    from sapient_protocol import SapientMessageBuilder
except ImportError:
    from src.sapient_protocol import SapientMessageBuilder


def convert_frame(frame):
    tracks = frame.get("tracks", [])

    # Build a real, EO/IR-only "fused" threat picture (no fabricated fusion
    # with sensors that don't exist in this pipeline)
    fused_threat_picture = []
    for t in tracks:
        obb = t["obb"]
        fused_threat_picture.append({
            "fused_id": f"EO-TRK-{t['track_id']}",
            "classification": obb.get("class_name", "drone").upper(),
            "confidence_score": t.get("score", obb.get("confidence", 0.0)),
            "sensor_sources": ["EO/IR"],  # honestly single-sensor, never fabricated
            "pos_3d": None,  # no georeferencing step exists to produce real-world metres
            "speed_px_per_frame": t.get("speed_px_per_frame"),  # real pixel-space speed, not calibrated to real units
            "eo_track_id": t["track_id"],
            "radar_rcs": None
        })

    hlm = SapientMessageBuilder.create_high_level_fusion_report(fused_threat_picture)

    return {
        "frame_id": frame["frame_id"],
        "inference_speed_ms": frame.get("inference_speed_ms", 0.0),
        "eoir_detections": frame.get("detections", []),
        "bytetrack_tracks": tracks,  # already shaped correctly by STrack.to_dict()
        "radar_detections": [],  # honest: no radar sensor in this pipeline
        "fused_threat_picture": fused_threat_picture,
        "sapient_hlm": hlm,
        "sapient_asm_eoir": frame.get("sapient_asm_eoir")
    }


def main():
    parser = argparse.ArgumentParser(description="Convert real detection/tracking output to dashboard feed format")
    parser.add_argument("--input", required=True, help="Path to detections_tracks.json from detect_and_track_video.py")
    parser.add_argument("--out", default="./simulation_feed.json", help="Output path (default overwrites the dashboard's feed file)")
    args = parser.parse_args()

    if not os.path.exists(args.input):
        raise SystemExit(f"ERROR: input not found: {args.input}")

    with open(args.input, "r") as f:
        data = json.load(f)

    frames = [convert_frame(f) for f in data["frames"]]
    output = {
        "metadata": {
            "source": "REAL pipeline output (detect_and_track_video.py)",
            "original_video": data.get("metadata", {}).get("video_source"),
            "note": "radar_detections is always empty and fused_threat_picture uses EO/IR only -- no radar/RF/acoustic sensor exists in this pipeline"
        },
        "frames": frames
    }

    with open(args.out, "w") as f:
        json.dump(output, f, indent=2)

    print(f"Converted {len(frames)} frames.")
    print(f"Dashboard feed written to: {os.path.abspath(args.out)}")
    print("Serve the project folder over HTTP (not file://) and refresh index.html to see real results.")


if __name__ == "__main__":
    main()
