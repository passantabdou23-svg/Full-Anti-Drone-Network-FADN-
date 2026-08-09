"""Regression tests for provisional and dormant identity reconciliation."""

import unittest

import numpy as np

from src.identity_resolver import IdentityResolver
from src.sapient_protocol import SapientMessageBuilder


class Box:
    def __init__(self, x_center=50.0, y_center=50.0, width=30.0, height=30.0):
        self.x_center = x_center
        self.y_center = y_center
        self.width = width
        self.height = height


class Track:
    def __init__(self, track_id, x_center=50.0, y_center=50.0):
        self.track_id = track_id
        self.obb = Box(x_center, y_center)
        self.score = 0.9
        self.velocity = (0.0, 0.0)


def coloured_frame(bgr):
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    frame[35:66, 35:66] = np.asarray(bgr, dtype=np.uint8)
    return frame


class IdentityResolverTests(unittest.TestCase):
    def test_new_track_without_dormant_candidate_is_confirmed(self):
        resolver = IdentityResolver(fps=10.0, confirm_frames=2, max_provisional_frames=4)

        assignments, events = resolver.step(1, coloured_frame((0, 0, 255)), [Track(10)])

        self.assertEqual(assignments[10]["display_id"], "ID-1")
        self.assertEqual(assignments[10]["identity_status"], "confirmed")
        self.assertEqual(events[0]["event"], "identity_created")
        self.assertEqual(assignments[10]["internal_track_id"], 10)

    def test_matching_reappearance_uses_temp_then_restores_old_identity(self):
        resolver = IdentityResolver(
            fps=10.0,
            retention_seconds=10.0,
            confirm_frames=2,
            max_provisional_frames=4,
        )
        red = coloured_frame((0, 0, 255))

        resolver.step(1, red, [Track(1)])
        resolver.step(2, red, [])
        first, first_events = resolver.step(8, red, [Track(2)])
        second, second_events = resolver.step(9, red, [Track(2)])

        self.assertEqual(first[2]["display_id"], "TEMP-1")
        self.assertEqual(first[2]["identity_status"], "provisional")
        self.assertEqual(first_events[0]["event"], "provisional_created")
        self.assertEqual(second[2]["display_id"], "ID-1")
        self.assertEqual(second[2]["identity_status"], "reidentified")
        self.assertEqual(second[2]["internal_track_id"], 2)
        self.assertEqual(second_events[0]["event"], "identity_reidentified")
        self.assertEqual(resolver.identity_aliases["TEMP-1"], "ID-1")

        historical = resolver.apply_final_alias({"display_id": "TEMP-1", "identity_id": None})
        self.assertEqual(historical["display_id_at_frame"], "TEMP-1")
        self.assertEqual(historical["final_display_id"], "ID-1")
        self.assertEqual(historical["final_identity_id"], 1)

    def test_different_appearance_promotes_temporary_identity(self):
        resolver = IdentityResolver(
            fps=10.0,
            retention_seconds=10.0,
            confirm_frames=1,
            max_provisional_frames=2,
            min_appearance_similarity=0.30,
        )
        red = coloured_frame((0, 0, 255))
        blue = coloured_frame((255, 0, 0))

        resolver.step(1, red, [Track(1)])
        resolver.step(2, red, [])
        first, _ = resolver.step(5, blue, [Track(2)])
        second, events = resolver.step(6, blue, [Track(2)])

        self.assertEqual(first[2]["display_id"], "TEMP-1")
        self.assertEqual(second[2]["display_id"], "ID-2")
        self.assertEqual(second[2]["identity_status"], "confirmed")
        self.assertEqual(events[0]["event"], "provisional_promoted")
        self.assertEqual(resolver.identity_aliases["TEMP-1"], "ID-2")

    def test_identity_outside_retention_becomes_new_immediately(self):
        resolver = IdentityResolver(
            fps=10.0,
            retention_seconds=1.0,
            confirm_frames=2,
            max_provisional_frames=4,
        )
        frame = coloured_frame((0, 255, 0))

        resolver.step(1, frame, [Track(1)])
        resolver.step(2, frame, [])
        assignments, events = resolver.step(15, frame, [Track(2)])

        self.assertEqual(assignments[2]["display_id"], "ID-2")
        self.assertEqual(assignments[2]["identity_status"], "confirmed")
        self.assertEqual(events[0]["event"], "identity_created")

    def test_provisional_that_disappears_is_abandoned_not_promoted(self):
        resolver = IdentityResolver(
            fps=10.0,
            retention_seconds=10.0,
            confirm_frames=3,
            max_provisional_frames=5,
        )
        frame = coloured_frame((0, 255, 0))

        resolver.step(1, frame, [Track(1)])
        resolver.step(2, frame, [])
        resolver.step(5, frame, [Track(2)])
        assignments, events = resolver.step(6, frame, [])

        self.assertEqual(assignments, {})
        self.assertEqual(events[0]["event"], "provisional_abandoned")
        self.assertEqual(len(resolver.identities), 1)

    def test_sapient_report_uses_operator_identity_without_losing_internal_id(self):
        track = {
            "track_id": 42,
            "internal_track_id": 42,
            "identity_id": None,
            "sapient_object_id": "TEMP-3",
            "score": 0.8,
            "obb": {
                "x_center": 50.0,
                "y_center": 50.0,
                "width": 30.0,
                "height": 30.0,
                "class_name": "drone",
            },
        }

        batch = SapientMessageBuilder.create_autonomous_sensor_report(
            "EOIR-CAM-01", "EO/IR", [track]
        )

        report = batch["detection_reports"][0]
        self.assertEqual(report["content"]["object_id"], "TEMP-3")
        self.assertEqual(track["internal_track_id"], 42)


if __name__ == "__main__":
    unittest.main()
