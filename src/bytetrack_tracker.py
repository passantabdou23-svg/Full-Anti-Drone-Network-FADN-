"""
ByteTrack Multi-Object Tracking Engine for EO/IR Drone Detection.
Maintains persistent track IDs, motion trajectories, velocities, and state handling.

PATCHED VERSION: the original matching logic relied purely on bounding-box IoU
between consecutive frames. That works fine for slow, synthetic motion, but on
real video a small fast-moving drone (or any camera motion) can shift more than
its own box size between frames, causing IoU to collapse to 0 -- which broke
frame-to-frame ID continuity almost entirely on real footage (1992 unique IDs
across 2200 frames of a single continuously-visible drone).

Fix applied:
  1. Motion-predicted matching: each track predicts its next position using its
     last known velocity, then matches to the nearest detection within a
     reasonable search radius (scaled to the track's own box size) -- not just
     boxes that already overlap.
  2. Lost-track revival: tracks that go briefly undetected (occlusion, a missed
     detection) are no longer discarded forever. They're kept in lost_stracks
     and can be re-matched to a reappearing detection for up to max_time_lost
     frames, preserving the original track_id instead of minting a new one.

IoU matching is still used as a secondary signal (helps disambiguate when two
detections are both within the search radius), but distance-to-prediction is
now the primary matching criterion.
"""

import numpy as np
import math

class STrack:
    """
    Single Track representation for ByteTrack.
    """
    _count = 0

    def __init__(self, obb, score):
        STrack._count += 1
        self.track_id = STrack._count
        self.obb = obb
        self.score = score

        # State: 0: New, 1: Tracked, 2: Lost, 3: Removed
        self.state = 1
        self.is_activated = True
        self.frame_id = 0
        self.tracklet_len = 0
        self.time_since_update = 0  # frames since last successful match

        # Motion history [x, y, timestamp]
        self.history = [(obb.x_center, obb.y_center)]
        self.velocity = (0.0, 0.0)  # (vx, vy) in px/frame

    def predict_position(self):
        """Predicts where this track's center should be next frame, using last known velocity."""
        vx, vy = self.velocity
        # Dampen velocity a bit each additional frame missed, so predictions
        # don't fly off to infinity during long occlusions.
        damping = 0.8 ** self.time_since_update
        px = self.obb.x_center + vx * damping
        py = self.obb.y_center + vy * damping
        return px, py

    def update(self, new_obb, new_score, frame_id):
        self.frame_id = frame_id
        self.tracklet_len += 1
        self.time_since_update = 0

        # Compute velocity vector
        last_x, last_y = self.history[-1]
        vx = new_obb.x_center - last_x
        vy = new_obb.y_center - last_y
        self.velocity = (vx, vy)

        self.obb = new_obb
        self.score = new_score
        self.history.append((new_obb.x_center, new_obb.y_center))
        if len(self.history) > 30:
            self.history.pop(0)

        self.state = 1  # Tracked

    def mark_lost(self):
        self.state = 2

    def mark_removed(self):
        self.state = 3

    def to_dict(self):
        vx, vy = self.velocity
        speed_px_per_frame = math.sqrt(vx * vx + vy * vy)
        return {
            "track_id": self.track_id,
            "obb": self.obb.to_dict(),
            "score": round(float(self.score), 3),
            "state": self.state,
            # Real, measured pixel-space speed. NOT converted to real-world
            # units (m/s) because doing so requires camera calibration
            # (focal length, altitude/range, sensor size) which this pipeline
            # does not have. A previous version of this file multiplied by an
            # arbitrary constant (15.0) and labelled the result "m/s" -- that
            # was a fabricated unit conversion and has been removed.
            "speed_px_per_frame": round(float(speed_px_per_frame), 2),
            "trajectory": [{"x": round(h[0], 1), "y": round(h[1], 1)} for h in self.history[-10:]]
        }


class ByteTracker:
    """
    ByteTrack algorithm implementation for aerial visual & thermal tracking.

    match_thresh: IoU acceptance floor when two candidates are both within the
                  search radius (higher match_thresh here now means a LOOSER
                  IoU requirement, since it's used only as a tie-breaker).
    max_time_lost: how many consecutive frames a track can go unmatched before
                   being permanently removed (instead of instantly minting a
                   brand-new ID on the very next frame).
    search_radius_factor: how many box-diagonals away a detection can still be
                   considered "the same object" relative to the predicted
                   position. Tune this up if your drone moves fast/erratically,
                   down if you have multiple close-together targets that keep
                   swapping IDs.
    """
    def __init__(self, high_thresh=0.5, low_thresh=0.2, match_thresh=0.3,
                 max_time_lost=30, search_radius_factor=4.0):
        self.high_thresh = high_thresh
        self.low_thresh = low_thresh
        self.match_thresh = match_thresh
        self.max_time_lost = max_time_lost
        self.search_radius_factor = search_radius_factor

        self.tracked_stracks = []
        self.lost_stracks = []
        self.removed_stracks = []
        self.frame_id = 0

    def compute_iou_obb(self, obb1, obb2):
        """Axis-aligned box IoU (angle ignored -- fine for angle=0 detections)."""
        dx = abs(obb1.x_center - obb2.x_center)
        dy = abs(obb1.y_center - obb2.y_center)

        w_inter = max(0, (obb1.width + obb2.width) / 2.0 - dx)
        h_inter = max(0, (obb1.height + obb2.height) / 2.0 - dy)
        area_inter = w_inter * h_inter

        area1 = obb1.width * obb1.height
        area2 = obb2.width * obb2.height
        area_union = area1 + area2 - area_inter

        return area_inter / area_union if area_union > 0 else 0.0

    def _search_radius_for(self, track):
        diag = math.hypot(track.obb.width, track.obb.height)
        return max(diag * self.search_radius_factor, 40.0)

    def _find_best_match(self, track, candidates, predicted_pos):
        """Finds the nearest candidate detection to a track's predicted position,
        within its search radius. Returns (index, distance) or (-1, None)."""
        px, py = predicted_pos
        radius = self._search_radius_for(track)

        best_idx = -1
        best_dist = None
        for idx, det in enumerate(candidates):
            dist = math.hypot(det.x_center - px, det.y_center - py)
            if dist <= radius and (best_dist is None or dist < best_dist):
                best_dist = dist
                best_idx = idx
        return best_idx, best_dist

    def _try_match_pool(self, tracks, det_pool):
        """
        Attempts to match each track in `tracks` against remaining detections in
        `det_pool` (mutated in place -- matched detections are removed).
        Returns (matched_pairs, still_unmatched_tracks) where matched_pairs is a
        list of (track, det).
        """
        matched_pairs = []
        still_unmatched = []

        for track in tracks:
            predicted_pos = track.predict_position()
            idx, dist = self._find_best_match(track, det_pool, predicted_pos)
            if idx != -1:
                det = det_pool.pop(idx)
                matched_pairs.append((track, det))
            else:
                still_unmatched.append(track)

        return matched_pairs, still_unmatched

    def update(self, detections):
        self.frame_id += 1

        det_high = []
        det_low = []
        for det in detections:
            if det.confidence >= self.high_thresh:
                det_high.append(det)
            elif det.confidence >= self.low_thresh:
                det_low.append(det)

        output_stracks = []

        # 1) Try to match currently-tracked tracks against high-confidence detections
        matched, unmatched_tracks = self._try_match_pool(self.tracked_stracks, det_high)
        for track, det in matched:
            track.update(det, det.confidence, self.frame_id)
            output_stracks.append(track)

        # 2) Remaining tracked-but-unmatched tracks get a shot at low-confidence detections
        matched_low, still_unmatched_tracks = self._try_match_pool(unmatched_tracks, det_low)
        for track, det in matched_low:
            track.update(det, det.confidence, self.frame_id)
            output_stracks.append(track)

        # 3) Tracks still unmatched after both passes -> try reviving from lost_stracks pool
        #    is handled below (lost tracks themselves try to match remaining high dets).
        #    For now, mark these as freshly lost.
        for track in still_unmatched_tracks:
            track.time_since_update += 1
            track.mark_lost()
            if track.time_since_update <= self.max_time_lost:
                self.lost_stracks.append(track)
            else:
                track.mark_removed()

        # 4) Try to revive previously-lost tracks using any remaining unmatched high-conf detections
        #    (prune out anything that's exceeded max_time_lost first)
        alive_lost = [t for t in self.lost_stracks if t.time_since_update <= self.max_time_lost]
        matched_revive, still_lost = self._try_match_pool(alive_lost, det_high)
        revived_ids = set()
        for track, det in matched_revive:
            track.update(det, det.confidence, self.frame_id)
            output_stracks.append(track)
            revived_ids.add(track.track_id)

        self.lost_stracks = [t for t in still_lost if t.track_id not in revived_ids
                              and t.time_since_update <= self.max_time_lost]

        # 5) Any detections still unmatched after all of the above become brand-new tracks
        for det in det_high:
            new_track = STrack(det, det.confidence)
            output_stracks.append(new_track)

        self.tracked_stracks = output_stracks
        return [t for t in self.tracked_stracks if t.state == 1]


if __name__ == "__main__":
    from yolo_detector import OrientedBoundingBox

    # Simulate a small, fast-moving drone (30px/frame jump -- would break the
    # old pure-IoU matcher, since a 20x20 box moving 30px has zero overlap
    # between consecutive frames) to confirm the fix holds a single ID.
    tracker = ByteTracker()
    ids_seen = set()
    x = 100.0
    for frame in range(30):
        x += 30.0  # large jump between frames, mimicking real fast footage
        obb = OrientedBoundingBox(x, 200, 20, 20, 0, 0.9, 0)
        tracks = tracker.update([obb])
        if tracks:
            ids_seen.add(tracks[0].track_id)

    print(f"Unique IDs across 30 fast-moving frames: {len(ids_seen)} (should be 1)")

    # Simulate a 5-frame occlusion (no detection at all) then reappearing nearby.
    # Reset the global ID counter first so this scenario's expected ID isn't
    # offset by the previous scenario above (STrack._count is shared/global,
    # by design, so IDs stay unique across the whole video -- not a bug).
    STrack._count = 0
    tracker2 = ByteTracker()
    x = 100.0
    tracker2.update([OrientedBoundingBox(x, 200, 20, 20, 0, 0.9, 0)])
    for _ in range(5):
        tracker2.update([])  # occluded, no detections this frame
        x += 15.0
    final_tracks = tracker2.update([OrientedBoundingBox(x, 200, 20, 20, 0, 0.9, 0)])
    print(f"Track ID after 5-frame occlusion: {final_tracks[0].track_id if final_tracks else 'LOST'} (should be 1)")
