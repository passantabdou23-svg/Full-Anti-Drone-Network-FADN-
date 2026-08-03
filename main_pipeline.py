"""
Main Pipeline Execution Script for Military Drone Detection & Multi-Sensor Fusion.
Combines YOLOv8-OBB, ByteTrack, 3D Radar Simulation, EKF Sensor Fusion, and NATO SAPIENT Messages.
Outputs benchmark evaluations and exports simulation dataset feeds for the Web Dashboard.
"""

import sys
import os
import json
import time
import math

# Ensure src directory is in path for both IDE PyLance and runtime
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

try:
    from yolo_detector import YoloDetectorEngine
    from bytetrack_tracker import ByteTracker
    from radar_simulator import RadarSimulatorEngine
    from sensor_fusion import SensorFusionEngine
    from sapient_protocol import SapientMessageBuilder
except ImportError:
    from src.yolo_detector import YoloDetectorEngine
    from src.bytetrack_tracker import ByteTracker
    from src.radar_simulator import RadarSimulatorEngine
    from src.sensor_fusion import SensorFusionEngine
    from src.sapient_protocol import SapientMessageBuilder

def run_main_pipeline():
    print("=" * 80)
    print(" NATO SAPIENT MILITARY DRONE DETECTION & SENSOR FUSION PIPELINE ")
    print(" Model: YOLOv8-OBB | Tracking: ByteTrack | Sensors: 3D Radar + EO/IR + RF + Acoustic")
    print("=" * 80)
    
    # 1. Initialize Engines
    detector = YoloDetectorEngine(model_name="YOLOv8-OBB", dataset_name="DUT Anti-UAV")
    tracker = ByteTracker(high_thresh=0.5, low_thresh=0.2)
    radar_sim = RadarSimulatorEngine(radar_name="AN/TPQ-50 Master-3D")
    fusion_engine = SensorFusionEngine()
    
    # 2. Simulated Ground Truth Drone & Clutter Trajectories (20 Frames)
    simulation_history = []
    
    base_x = 220.0
    base_y = 140.0
    base_range = 1450.0
    base_az = 42.0
    
    for frame_id in range(1, 21):
        # Target 1: Approaching Tactical Micro-Drone
        drone_target_1 = {
            "id": 1,
            "x": base_x + frame_id * 6.5,
            "y": base_y + math.sin(frame_id * 0.4) * 8.0,
            "w": 42.0,
            "h": 26.0,
            "angle": 14.0 + frame_id * 0.8,
            "base_conf": 0.92,
            "class": "drone",
            "range_m": base_range - frame_id * 22.0,
            "azimuth_deg": base_az + frame_id * 0.25,
            "elevation_deg": 9.2,
            "velocity_mps": 22.5,
            "rcs_sqm": 0.018 # micro drone RCS
        }
        
        # Target 2: Crossing Commercial Drone / Bird Clutter
        drone_target_2 = {
            "id": 2,
            "x": 480.0 - frame_id * 5.0,
            "y": 280.0 + math.cos(frame_id * 0.3) * 6.0,
            "w": 34.0,
            "h": 20.0,
            "angle": -25.0,
            "base_conf": 0.76,
            "class": "drone",
            "range_m": 2100.0 - frame_id * 15.0,
            "azimuth_deg": 68.0 - frame_id * 0.3,
            "elevation_deg": 12.0,
            "velocity_mps": 16.0,
            "rcs_sqm": 0.025
        }
        
        ground_truth = [drone_target_1, drone_target_2]
        
        # Step A: YOLOv8-OBB Detection
        obbs, infer_time = detector.detect_frame(frame_id, ground_truth)
        
        # Step B: ByteTrack Tracking
        active_stracks = tracker.update(obbs)
        
        # Step C: 3D Radar Sweep
        radar_dets = radar_sim.generate_radar_sweeps(ground_truth)
        
        # Step D: Multi-Sensor Fusion
        fused_tracks = fusion_engine.process_fusion_step(
            eo_tracks=active_stracks,
            radar_dets=radar_dets,
            rf_inputs={"signal": "2.4GHz / 5.8GHz Telemetry Detected", "snr": 18.4},
            acoustic_inputs={"signature": "Propeller Blade Pass Freq (BPF) Matched"}
        )
        
        # Step E: NATO SAPIENT Messages
        asm_radar = SapientMessageBuilder.create_autonomous_sensor_report(
            "RADAR-NODE-01", "3D_PULSE_DOPPLER", [r.to_dict() for r in radar_dets]
        )
        asm_eoir = SapientMessageBuilder.create_autonomous_sensor_report(
            "EOIR-CAM-01", "EO/IR_YOLOv8_OBB", [t.to_dict() for t in active_stracks]
        )
        hlm_fusion = SapientMessageBuilder.create_high_level_fusion_report(
            [ft.to_dict() for ft in fused_tracks]
        )
        
        frame_snapshot = {
            "frame_id": frame_id,
            "inference_speed_ms": round(infer_time, 1),
            "eoir_detections": [o.to_dict() for o in obbs],
            "bytetrack_tracks": [t.to_dict() for t in active_stracks],
            "radar_detections": [r.to_dict() for r in radar_dets],
            "fused_threat_picture": [ft.to_dict() for ft in fused_tracks],
            "sapient_asm_radar": asm_radar,
            "sapient_asm_eoir": asm_eoir,
            "sapient_hlm": hlm_fusion
        }
        simulation_history.append(frame_snapshot)

    # 3. Export Simulation Dataset Feed for Frontend Web Dashboard
    output_feed_path = os.path.join(os.path.dirname(__file__), "simulation_feed.json")
    export_data = {
        "metadata": {
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
            "system": "NATO SAPIENT Counter-UAS Multi-Sensor Pipeline",
            "yolo_model": "YOLOv8-OBB (Fine-Tuned DUT Anti-UAV)",
            "tracker": "ByteTrack",
            "radar": "3D Pulse-Doppler Millimeter Wave Radar"
        },
        "benchmarks": detector.benchmark_data,
        "fusion_metrics": fusion_engine.get_fusion_metrics(),
        "frames": simulation_history
    }
    
    with open(output_feed_path, "w") as f:
        json.dump(export_data, f, indent=2)
        
    print(f"\nPipeline execution successful. Simulation feed exported to: {output_feed_path}")
    print(f"Total Frames Processed: {len(simulation_history)}")
    print(f"Benchmark Summary (YOLOv8-OBB Fine-Tuned): Coverage {detector.benchmark_data['YOLOv8-OBB (Fine-Tuned DUT)']['coverage_pct']}%, Precision {detector.benchmark_data['YOLOv8-OBB (Fine-Tuned DUT)']['precision']}")

if __name__ == "__main__":
    run_main_pipeline()
