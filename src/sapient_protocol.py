"""
NATO SAPIENT (STANAG 4810 v2.0) Communication Protocol Module.
Implements standard JSON/XML message schemas for multi-sensor counter-UAS interoperability.
Nodes: Sensor Edge Nodes -> Fusion Node -> Decision Node -> Effector Nodes.
"""

import json
import time

class SapientMessageBuilder:
    """
    Builds NATO SAPIENT v2.0 compliant messages.
    """
    @staticmethod
    def create_autonomous_sensor_report(sensor_id, sensor_type, detections_list):
        """
        ASM - Autonomous Sensor Message from Edge Sensor (Radar, EO/IR, RF, Acoustic).
        """
        payload = {
            "sapient_header": {
                "version": "2.0",
                "stanag_standard": "STANAG 4810",
                "message_type": "AutonomousSensorReport",
                "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "source_id": sensor_id,
                "sensor_type": sensor_type
            },
            "sensor_location": {
                "lat": 34.0522,
                "lon": -118.2437,
                "alt_m": 125.0
            },
            "detections": detections_list
        }
        return payload

    @staticmethod
    def create_high_level_fusion_report(fused_tracks_list):
        """
        HLM - High Level Message from Sensor Fusion Node to Command Decision Center.
        """
        payload = {
            "sapient_header": {
                "version": "2.0",
                "stanag_standard": "STANAG 4810",
                "message_type": "HighLevelFusionReport",
                "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "source_id": "SAPIENT-FUSION-CORE-01"
            },
            "threat_environment": {
                "active_threat_count": len(fused_tracks_list),
                "system_threat_level": "DEFCON-2" if fused_tracks_list else "DEFCON-5"
            },
            "unified_tracks": fused_tracks_list
        }
        return payload

    @staticmethod
    def create_effector_command(target_id, effector_type, command_action):
        """
        Tasking Command Message sent to Effector Nodes (EW Jammer, Laser, Kinetic Interceptor).
        """
        payload = {
            "sapient_header": {
                "version": "2.0",
                "stanag_standard": "STANAG 4810",
                "message_type": "EffectorTaskingCommand",
                "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "source_id": "C2-DECISION-NODE-ALPHA"
            },
            "target_track_id": target_id,
            "effector_assigned": effector_type,
            "action": command_action,
            "status": "ENGAGEMENT_INITIATED"
        }
        return payload

if __name__ == "__main__":
    msg = SapientMessageBuilder.create_autonomous_sensor_report(
        "EOIR-CAM-01", "EO/IR_CAMERA", [{"track_id": 1, "class": "drone", "conf": 0.92}]
    )
    print(json.dumps(msg, indent=2))
