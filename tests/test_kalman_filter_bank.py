"""Regression tests for missing-track handling in the Kalman filter bank."""

import unittest

from kalman_filter import TrackKalmanFilterBank


class Box:
    def __init__(self, x_center, y_center):
        self.x_center = x_center
        self.y_center = y_center


class Track:
    def __init__(self, track_id, x_center, y_center):
        self.track_id = track_id
        self.obb = Box(x_center, y_center)


class TrackKalmanFilterBankTests(unittest.TestCase):
    def test_missing_track_is_predicted_forward(self):
        bank = TrackKalmanFilterBank()
        bank.step([Track(1, 0.0, 0.0)])
        bank.step([Track(1, 10.0, 0.0)])

        before_gap = bank.filters[1].get_state()
        result = bank.step([])
        after_gap = bank.filters[1].get_state()

        self.assertEqual(result, {})
        self.assertGreater(after_gap["x"], before_gap["x"])
        self.assertEqual(after_gap["frames_since_last_detection"], 1)

    def test_stale_filter_is_removed_after_configured_limit(self):
        bank = TrackKalmanFilterBank(max_frames_without_detection=2)
        bank.step([Track(7, 100.0, 200.0)])

        bank.step([])
        bank.step([])
        self.assertIn(7, bank.filters)

        bank.step([])
        self.assertNotIn(7, bank.filters)


if __name__ == "__main__":
    unittest.main()
