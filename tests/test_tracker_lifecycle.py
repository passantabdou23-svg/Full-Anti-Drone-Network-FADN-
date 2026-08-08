"""Focused lifecycle tests for the custom ByteTrack-style tracker."""

import unittest

from src.bytetrack_tracker import ByteTracker, STrack


class Detection:
    """Minimal detection shape consumed by ByteTracker."""

    def __init__(self, x_center=100.0, y_center=100.0, confidence=0.9):
        self.x_center = x_center
        self.y_center = y_center
        self.width = 20.0
        self.height = 20.0
        self.confidence = confidence


class TrackerLifecycleTests(unittest.TestCase):
    def setUp(self):
        STrack._count = 0

    def test_lost_track_can_be_revived_at_the_configured_limit(self):
        tracker = ByteTracker(max_time_lost=2)
        original_id = tracker.update([Detection()])[0].track_id

        tracker.update([])
        tracker.update([])
        revived = tracker.update([Detection()])

        self.assertEqual([track.track_id for track in revived], [original_id])
        self.assertEqual(tracker.lost_stracks, [])
        self.assertEqual(tracker.removed_stracks, [])

    def test_lost_track_expires_after_the_configured_limit(self):
        tracker = ByteTracker(max_time_lost=2)
        original_id = tracker.update([Detection()])[0].track_id

        tracker.update([])
        tracker.update([])
        tracker.update([])

        self.assertEqual(tracker.lost_stracks, [])
        self.assertEqual(
            [track.track_id for track in tracker.removed_stracks],
            [original_id],
        )

        replacement = tracker.update([Detection()])
        self.assertEqual(len(replacement), 1)
        self.assertNotEqual(replacement[0].track_id, original_id)


if __name__ == "__main__":
    unittest.main()
