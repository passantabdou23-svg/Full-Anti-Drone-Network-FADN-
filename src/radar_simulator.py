"""
3D Pulse-Doppler Military Radar Simulator & Dataset Parser.
Provides long-range 3D tracking data: Range (m), Azimuth (deg), Elevation (deg),
Radial Velocity (m/s), and Radar Cross Section (RCS in m^2).
"""

import math
import numpy as np

class RadarDetection:
    def __init__(self, radar_id, range_m, azimuth_deg, elevation_deg, velocity_mps, rcs_sqm, confidence=0.92):
        self.radar_id = radar_id
        self.range_m = range_m
        self.azimuth_deg = azimuth_deg
        self.elevation_deg = elevation_deg
        self.velocity_mps = velocity_mps
        self.rcs_sqm = rcs_sqm
        self.confidence = confidence

    def get_cartesian_3d(self, radar_origin_xyz=(0, 0, 0)):
        """Convert spherical Radar coordinates to 3D Cartesian (x, y, z)."""
        az_rad = math.radians(self.azimuth_deg)
        el_rad = math.radians(self.elevation_deg)
        
        # Spherical to Cartesian
        x = self.range_m * math.cos(el_rad) * math.sin(az_rad) + radar_origin_xyz[0]
        y = self.range_m * math.cos(el_rad) * math.cos(az_rad) + radar_origin_xyz[1]
        z = self.range_m * math.sin(el_rad) + radar_origin_xyz[2]
        return x, y, z

    def to_dict(self):
        x, y, z = self.get_cartesian_3d()
        return {
            "radar_id": self.radar_id,
            "range_m": round(float(self.range_m), 1),
            "azimuth_deg": round(float(self.azimuth_deg), 1),
            "elevation_deg": round(float(self.elevation_deg), 1),
            "velocity_mps": round(float(self.velocity_mps), 1),
            "rcs_sqm": round(float(self.rcs_sqm), 3),
            "confidence": round(float(self.confidence), 3),
            "cartesian_3d": {"x": round(x, 1), "y": round(y, 1), "z": round(z, 1)}
        }


class RadarSimulatorEngine:
    """
    Simulates a NATO SAPIENT-compliant Military Pulse-Doppler 3D Radar Node.
    """
    def __init__(self, radar_name="AN/TPQ-50 Master-3D", max_range_m=10000):
        self.radar_name = radar_name
        self.max_range_m = max_range_m

    def generate_radar_sweeps(self, ground_truth_targets):
        """
        Generates 3D radar detections from true physical target trajectories with realistic noise.
        """
        detections = []
        for target in ground_truth_targets:
            # Add radar noise (Range +- 8m, Azimuth +- 0.3 deg, Elevation +- 0.4 deg)
            r_noise = np.random.normal(0, 7.5)
            az_noise = np.random.normal(0, 0.25)
            el_noise = np.random.normal(0, 0.35)
            
            det = RadarDetection(
                radar_id=f"RAD-{target['id']}",
                range_m=target["range_m"] + r_noise,
                azimuth_deg=target["azimuth_deg"] + az_noise,
                elevation_deg=target.get("elevation_deg", 8.5) + el_noise,
                velocity_mps=target.get("velocity_mps", 18.5) + np.random.normal(0, 0.5),
                rcs_sqm=target.get("rcs_sqm", 0.015), # micro drone RCS ~0.01-0.03 m^2
                confidence=np.clip(0.88 + np.random.normal(0, 0.04), 0.70, 0.98)
            )
            detections.append(det)
            
        return detections

if __name__ == "__main__":
    sim = RadarSimulatorEngine()
    targets = [{"id": 101, "range_m": 1420.0, "azimuth_deg": 45.0, "rcs_sqm": 0.012}]
    dets = sim.generate_radar_sweeps(targets)
    print(f"Radar detection: {dets[0].to_dict()}")
