"""
SAPIENT (Sensing for Asset Protection with Integrated Electronic Networked
Technology) message formatting.

IMPORTANT -- honest scope statement:
SAPIENT is a real, public specification: BSI Flex 335 v1.0:2023-07
("SAPIENT Network of autonomous sensors and effectors - Interface control
document - Specification"), developed by UK Dstl and adopted by NATO as
STANREC 4869 (a NATO Standardization RECommendation, not "STANAG 4810" --
an earlier version of this file referenced a standard number that does not
match any publicly documented SAPIENT designation, and has been corrected).

The official standard mandates:
  - Google Protocol Buffers v3 (binary), not JSON, as the wire format
  - UUID v4 node identifiers and ULID (Universally Unique Lexicographically
    Sortable Identifier) report/object identifiers
  - A full Registration / RegistrationAck handshake before any node may send
    Status or Detection messages
  - Nine message types total: Registration, RegistrationAck, StatusReport,
    DetectionReport, Task, TaskAck, Alert, AlertAck, Error

This module implements a JSON approximation of two of those message types
(StatusReport, DetectionReport) plus a simplified Task message, using the
real field names and structure documented in BSI Flex 335 Clauses 5-6, so
that the shape of the data is recognisable and educationally accurate.
It does NOT implement Registration/RegistrationAck, Alert, TaskAck, or Error
messages, does not use Protobuf, and uses UUID4 (not true ULID) for report
and object identifiers since ULID requires an extra dependency. This is
therefore NOT wire-compatible with a real SAPIENT fusion node -- it is a
readable, structurally-accurate JSON stand-in suitable for a research/thesis
pipeline, not a certified implementation.

Reference: BSI Flex 335 v1.0:2023-07, Clauses 5 (Inner message types) and
6.3-6.5 (Status/Detection/Task outer message types).
"""

import json
import time
import uuid


def _new_id():
    """UUID4 hex string. Real SAPIENT requires ULIDs for report/object IDs
    (lexicographically sortable by time) -- this is a simplification."""
    return str(uuid.uuid4())


def _utc_timestamp():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class SapientMessageBuilder:
    """
    Builds JSON messages structurally modelled on real SAPIENT (BSI Flex 335
    / STANREC 4869) DetectionReport, StatusReport, and Task messages.
    """

    STANDARD_REFERENCE = "BSI Flex 335 v1.0:2023-07 (SAPIENT), adopted by NATO as STANREC 4869"

    # ------------------------------------------------------------------
    # Detection Report (BSI Flex 335, Table 64) -- one per detected object,
    # sent by a sensor edge node.
    # ------------------------------------------------------------------
    @staticmethod
    def create_detection_report(node_id, object_id, detection_confidence,
                                 x_center, y_center, width, height,
                                 classification_type="drone",
                                 classification_confidence=None,
                                 task_id="0", destination_id=None,
                                 extra_object_info=None):
        """
        Builds one DetectionReport message for a single detected object,
        following the real field names in BSI Flex 335 Table 64.

        Note on location: the real spec requires location in a real-world
        coordinate system (GNSS lat/lon/alt, UTM, or range-bearing relative
        to a surveyed sensor position -- Table 3/Table 7). This pipeline has
        no georeferencing step (no camera survey, no GNSS), so image-plane
        pixel coordinates are reported instead, under an explicitly
        non-standard "coordinate_system": "IMAGE_PIXELS" value (the real
        enum only defines LAT_LNG_DEG_M, LAT_LNG_RAD_M, and UTM_M -- see
        Table 4). This is flagged rather than silently mislabelled as GNSS.
        """
        object_info = [
            {"type": "width_px", "value": round(float(width), 1)},
            {"type": "height_px", "value": round(float(height), 1)},
        ]
        if extra_object_info:
            object_info.extend(extra_object_info)

        classification = [{
            "type": classification_type,
            "confidence": round(float(classification_confidence), 3)
                          if classification_confidence is not None
                          else round(float(detection_confidence), 3)
        }]

        content = {
            "report_id": _new_id(),
            "object_id": object_id,
            "task_id": task_id,
            "location": {
                "x": round(float(x_center), 2),
                "y": round(float(y_center), 2),
                "coordinate_system": "IMAGE_PIXELS",  # non-standard, see docstring
                "datum": "UNSPECIFIED"
            },
            "detection_confidence": round(float(detection_confidence), 3),
            "object_info": object_info,
            "classification": classification
        }

        return {
            "timestamp": _utc_timestamp(),
            "node_id": node_id,
            "destination_id": destination_id,
            "message_type": "DetectionReport",
            "sapient_standard": SapientMessageBuilder.STANDARD_REFERENCE,
            "content": content
        }

    # ------------------------------------------------------------------
    # Status Report (BSI Flex 335, Table 55) -- heartbeat / node status
    # ------------------------------------------------------------------
    @staticmethod
    def create_status_report(node_id, system_status="OK", mode="default",
                              active_task_id=None, node_location=None,
                              destination_id=None):
        """
        system_status must be one of: UNSPECIFIED, OK, WARNING, ERROR, GOODBYE
        (BSI Flex 335 Table 56).
        """
        content = {
            "report_id": _new_id(),
            "system": system_status,
            "info": "NEW",
            "active_task_id": active_task_id,
            "mode": mode,
        }
        if node_location is not None:
            content["node_location"] = node_location

        return {
            "timestamp": _utc_timestamp(),
            "node_id": node_id,
            "destination_id": destination_id,
            "message_type": "StatusReport",
            "sapient_standard": SapientMessageBuilder.STANDARD_REFERENCE,
            "content": content
        }

    # ------------------------------------------------------------------
    # Task message (BSI Flex 335, Clause 6.5) -- fusion node tasking an
    # edge node or effector node
    # ------------------------------------------------------------------
    @staticmethod
    def create_task_message(source_node_id, destination_node_id, command_name,
                             command_value, region=None):
        """
        Per BSI Flex 335 6.5: a task shall define a region and/or a command.
        command_name should be one of the real defined command types where
        applicable (e.g. "Mode_Change", "LookAt", "DetectionThreshold") --
        see Table 54. Effector-specific actions beyond Arm/Start/Stop are
        outside the current (v1.0) standard's scope for effector tasking.
        """
        content = {
            "task_id": _new_id(),
            "command": {
                "name": command_name,
                "value": command_value
            }
        }
        if region is not None:
            content["region"] = region

        return {
            "timestamp": _utc_timestamp(),
            "node_id": source_node_id,
            "destination_id": destination_node_id,
            "message_type": "Task",
            "sapient_standard": SapientMessageBuilder.STANDARD_REFERENCE,
            "content": content
        }

    # ------------------------------------------------------------------
    # Backward-compatible wrappers around the OLD method names/shape used
    # elsewhere in this codebase (main_pipeline.py, detect_and_track_video.py),
    # so existing call sites keep working. New code should prefer the
    # correctly-named methods above.
    # ------------------------------------------------------------------
    @staticmethod
    def create_autonomous_sensor_report(sensor_id, sensor_type, detections_list):
        """
        DEPRECATED name (the real spec has no "AutonomousSensorReport" message
        type -- this was an invented name). Kept for backward compatibility;
        wraps one DetectionReport per item in detections_list using whatever
        fields are available on each dict (tolerant of both OrientedBoundingBox
        .to_dict() and STrack .to_dict() shapes used in this pipeline).
        """
        reports = []
        for det in detections_list:
            obb = det.get("obb", det)  # STrack.to_dict() nests under "obb"
            reports.append(SapientMessageBuilder.create_detection_report(
                node_id=sensor_id,
                object_id=str(det.get("track_id", det.get("class_id", _new_id()))),
                detection_confidence=det.get("score", obb.get("confidence", 0.0)),
                x_center=obb.get("x_center", 0.0),
                y_center=obb.get("y_center", 0.0),
                width=obb.get("width", 0.0),
                height=obb.get("height", 0.0),
                classification_type=obb.get("class_name", "drone"),
            ))
        return {
            "timestamp": _utc_timestamp(),
            "node_id": sensor_id,
            "message_type": "DetectionReportBatch",  # non-standard batching wrapper, see docstring
            "sapient_standard": SapientMessageBuilder.STANDARD_REFERENCE,
            "sensor_type": sensor_type,
            "detection_reports": reports
        }

    @staticmethod
    def create_high_level_fusion_report(fused_tracks_list):
        """
        DEPRECATED name. The real spec has no distinct "HighLevelFusionReport"
        message type -- a fusion node sends the SAME DetectionReport message
        type as edge nodes (with fused track points), per BSI Flex 335 4.5(g).
        Kept for backward compatibility with main_pipeline.py's simulated demo.
        """
        return {
            "timestamp": _utc_timestamp(),
            "node_id": "SAPIENT-FUSION-NODE-01",
            "message_type": "DetectionReportBatch (fusion node output)",
            "sapient_standard": SapientMessageBuilder.STANDARD_REFERENCE,
            "active_track_count": len(fused_tracks_list),
            "unified_tracks": fused_tracks_list
        }

    @staticmethod
    def create_effector_command(target_id, effector_type, command_action):
        """
        DEPRECATED name/shape. Real tasking uses the Task message (Clause 6.5),
        implemented properly in create_task_message() above. This wrapper
        preserves the old call signature for main_pipeline.py.
        """
        msg = SapientMessageBuilder.create_task_message(
            source_node_id="C2-DECISION-NODE-ALPHA",
            destination_node_id=effector_type,
            command_name=command_action,
            command_value=target_id
        )
        # Old shape had a "status" field with a hard-coded, presumptuous value
        # ("ENGAGEMENT_INITIATED") -- removed. A task is sent; whether it is
        # actioned is reported later by the recipient in a TaskAck message,
        # which this module does not yet implement.
        return msg


if __name__ == "__main__":
    # Real detection example
    msg = SapientMessageBuilder.create_detection_report(
        node_id="EOIR-CAM-01",
        object_id="track-1",
        detection_confidence=0.92,
        x_center=640.0, y_center=360.0, width=48.0, height=32.0,
        classification_type="drone"
    )
    print(json.dumps(msg, indent=2))

    # Real status report example
    status = SapientMessageBuilder.create_status_report(
        node_id="EOIR-CAM-01", system_status="OK", mode="default"
    )
    print(json.dumps(status, indent=2))
