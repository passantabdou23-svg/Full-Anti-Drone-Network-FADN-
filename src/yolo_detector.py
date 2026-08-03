"""
YOLOv8-OBB Detection and Benchmark Engine for Military Drone Detection.
Compliant with NATO SAPIENT Counter-UAS Architecture.

Supports Oriented Bounding Boxes (OBB): [x_center, y_center, width, height, angle_deg]
and benchmark evaluations against baseline YOLOv9 and YOLOv11 models.
"""

import numpy as np
import math
import time

class OrientedBoundingBox:
    def __init__(self, x_center, y_center, width, height, angle_deg, confidence, class_id, class_name="drone"):
        self.x_center = x_center
        self.y_center = y_center
        self.width = width
        self.height = height
        self.angle_deg = angle_deg
        self.confidence = confidence
        self.class_id = class_id
        self.class_name = class_name

    def to_dict(self):
        return {
            "x_center": round(float(self.x_center), 2),
            "y_center": round(float(self.y_center), 2),
            "width": round(float(self.width), 2),
            "height": round(float(self.height), 2),
            "angle_deg": round(float(self.angle_deg), 1),
            "confidence": round(float(self.confidence), 3),
            "class_id": int(self.class_id),
            "class_name": self.class_name
        }

    def get_corners(self):
        """Compute the 4 oriented corners of the box."""
        angle_rad = math.radians(self.angle_deg)
        cos_a = math.cos(angle_rad)
        sin_a = math.sin(angle_rad)
        
        w2 = self.width / 2.0
        h2 = self.height / 2.0
        
        # Local unrotated corners
        corners_local = [
            (-w2, -h2),
            (w2, -h2),
            (w2, h2),
            (-w2, h2)
        ]
        
        # Rotate and translate
        corners_world = []
        for cx, cy in corners_local:
            rx = cx * cos_a - cy * sin_a + self.x_center
            ry = cx * sin_a + cy * cos_a + self.y_center
            corners_world.append((rx, ry))
            
        return corners_world


class YoloDetectorEngine:
    """
    Simulation and evaluation engine for YOLOv8-OBB vs baseline YOLOv9 & YOLOv11.
    """
    def __init__(self, model_name="YOLOv8-OBB", dataset_name="DUT Anti-UAV"):
        self.model_name = model_name
        self.dataset_name = dataset_name
        
        # Performance specs based on research PPTX slide 20 & 21
        self.benchmark_data = {
            "YOLOv8-OBB (Baseline)": {
                "pretraining": "DOTA aerial imagery",
                "precision": 0.750,
                "recall": 0.040,
                "mAP50": 0.033,
                "speed_ms": 13.0,
                "coverage_pct": 8.0,
                "detected_ratio": "24 / 301",
                "false_alarm_rate": 4.2
            },
            "YOLOv8-OBB (Fine-Tuned DUT)": {
                "pretraining": "DOTA + DUT Anti-UAV 10k",
                "precision": 0.912,
                "recall": 0.845,
                "mAP50": 0.868,
                "speed_ms": 13.2,
                "coverage_pct": 84.5,
                "detected_ratio": "254 / 301",
                "false_alarm_rate": 1.8
            },
            "YOLOv9": {
                "pretraining": "COCO dataset",
                "precision": 0.035,
                "recall": 0.003,
                "mAP50": 0.000,
                "speed_ms": 48.0,
                "coverage_pct": 3.7,
                "detected_ratio": "3 / 80",
                "false_alarm_rate": 15.6
            },
            "YOLOv11": {
                "pretraining": "COCO dataset",
                "precision": 0.000,
                "recall": 0.000,
                "mAP50": 0.000,
                "speed_ms": 18.0,
                "coverage_pct": 0.0,
                "detected_ratio": "0 / 80",
                "false_alarm_rate": 22.1
            }
        }

    def detect_frame(self, frame_id, targets_in_scene):
        """
        Runs OBB detection on a given frame with simulated targets.
        """
        detections = []
        t0 = time.time()
        
        for target in targets_in_scene:
            # Simulate YOLOv8-OBB oriented detection box
            noise_x = np.random.normal(0, 1.5)
            noise_y = np.random.normal(0, 1.5)
            conf = np.clip(np.random.normal(target.get("base_conf", 0.88), 0.04), 0.50, 0.99)
            
            obb = OrientedBoundingBox(
                x_center=target["x"] + noise_x,
                y_center=target["y"] + noise_y,
                width=target.get("w", 38),
                height=target.get("h", 24),
                angle_deg=target.get("angle", 15.0) + np.random.normal(0, 1.0),
                confidence=conf,
                class_id=0,
                class_name=target.get("class", "drone")
            )
            detections.append(obb)
            
        inference_time_ms = (time.time() - t0) * 1000 + 12.8  # ~13ms simulated inference
        return detections, inference_time_ms

    def evaluate_metrics(self, tp, fp, fn, total_instances, total_empty_frames, false_alarms):
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        coverage = (tp / total_instances * 100.0) if total_instances > 0 else 0.0
        far = (false_alarms / total_empty_frames * 100.0) if total_empty_frames > 0 else 0.0
        
        return {
            "precision": round(precision, 3),
            "recall": round(recall, 3),
            "coverage_pct": round(coverage, 1),
            "false_alarm_rate_pct": round(far, 2)
        }

if __name__ == "__main__":
    detector = YoloDetectorEngine()
    print("YOLO Detector Engine initialized.")
    for m, data in detector.benchmark_data.items():
        print(f"[{m}] Precision: {data['precision']}, Speed: {data['speed_ms']}ms, Coverage: {data['coverage_pct']}%")
