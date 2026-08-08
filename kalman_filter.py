"""
Track Kalman Filter (TKF) -- a real, standard discrete linear Kalman filter
applied to a single EO/IR track's 2D pixel position over time.

Honest scope: this is single-sensor state estimation/smoothing, NOT
multi-sensor fusion. There is no radar, RF, or acoustic sensor in this
pipeline to fuse with (see src/sensor_fusion.py's docstring for that
placeholder). What this DOES do, for real:
  - Models each track as a constant-velocity object: state = [x, y, vx, vy]
  - Maintains a real state covariance matrix P, updated every frame via the
    standard KF predict/update equations (not a heuristic average)
  - Produces a smoothed position estimate that is less noisy than the raw
    per-frame detection, plus a real velocity estimate and its uncertainty
  - Can predict a track's position one or more frames into the future even
    when a frame has no detection (useful for brief occlusion bridging)

Reference: standard discrete linear Kalman filter equations, e.g.
Bar-Shalom, Li & Kirubarajan, "Estimation with Applications to Tracking
and Navigation" (2001), Ch. 5.
"""

import numpy as np


class TrackKalmanFilter:
    """
    Constant-velocity Kalman filter for a single track's 2D pixel position.

    State vector x = [px, py, vx, vy]^T  (position and velocity, px/frame)
    Measurement z = [px, py]^T           (detected box center each frame)

    process_noise_std: how much we expect true velocity to change frame to
        frame (higher = trust the motion model less, adapt to detections
        faster). Tune this up for erratic/maneuvering targets.
    measurement_noise_std: how noisy we believe the raw detector's box
        center is (higher = trust detections less, smooth more heavily).
    """

    def __init__(self, initial_x, initial_y, process_noise_std=2.0, measurement_noise_std=3.0):
        # State: [x, y, vx, vy]
        self.x = np.array([initial_x, initial_y, 0.0, 0.0], dtype=float)

        # State covariance -- start with high uncertainty on velocity since
        # we have no motion history yet on the first frame
        self.P = np.diag([5.0, 5.0, 50.0, 50.0])

        # State transition matrix F (constant velocity model, dt=1 frame)
        self.F = np.array([
            [1, 0, 1, 0],
            [0, 1, 0, 1],
            [0, 0, 1, 0],
            [0, 0, 0, 1]
        ], dtype=float)

        # Measurement matrix H (we only observe position, not velocity)
        self.H = np.array([
            [1, 0, 0, 0],
            [0, 1, 0, 0]
        ], dtype=float)

        q = process_noise_std ** 2
        self.Q = np.diag([q * 0.25, q * 0.25, q, q])  # process noise covariance

        r = measurement_noise_std ** 2
        self.R = np.diag([r, r])  # measurement noise covariance

        self.frames_since_update = 0

    def predict(self):
        """Advances the state estimate by one frame using the motion model alone."""
        self.x = self.F @ self.x
        self.P = self.F @ self.P @ self.F.T + self.Q
        self.frames_since_update += 1
        return self.x[0], self.x[1]

    def update(self, measured_x, measured_y):
        """Corrects the prediction using a real detection this frame (standard KF update step)."""
        z = np.array([measured_x, measured_y])
        y = z - self.H @ self.x  # innovation (measurement residual)
        S = self.H @ self.P @ self.H.T + self.R  # innovation covariance
        K = self.P @ self.H.T @ np.linalg.inv(S)  # Kalman gain

        self.x = self.x + K @ y
        I = np.eye(4)
        self.P = (I - K @ self.H) @ self.P
        self.frames_since_update = 0

    def get_state(self):
        return {
            "x": round(float(self.x[0]), 2),
            "y": round(float(self.x[1]), 2),
            "vx": round(float(self.x[2]), 2),
            "vy": round(float(self.x[3]), 2),
            "position_uncertainty_px": round(float(np.sqrt(self.P[0, 0] + self.P[1, 1])), 2),
            "frames_since_last_detection": self.frames_since_update
        }


class TrackKalmanFilterBank:
    """
    Manages one TrackKalmanFilter per active track_id, so multiple
    simultaneous drones each get independently filtered.
    """
    def __init__(self, process_noise_std=2.0, measurement_noise_std=3.0,
                 max_frames_without_detection=30):
        self.filters = {}
        self.process_noise_std = process_noise_std
        self.measurement_noise_std = measurement_noise_std
        self.max_frames_without_detection = max_frames_without_detection

    def step(self, active_tracks):
        """
        active_tracks: list of dicts/objects with .track_id, .obb.x_center, .obb.y_center
        (matches STrack from bytetrack_tracker.py). Returns a dict of
        {track_id: TrackKalmanFilter.get_state()} for every track seen this call.
        Filters for tracks not present this frame are predict()-only advanced
        (bridging brief gaps) but not returned, and are dropped after
        max_frames_without_detection frames with no update to avoid unbounded
        memory growth.
        """
        seen_ids = set()
        results = {}

        # Advance every existing filter exactly once per video frame. The old
        # implementation predicted only filters that also had a measurement,
        # so missing tracks neither moved forward nor accumulated stale age.
        for track_filter in self.filters.values():
            track_filter.predict()

        for t in active_tracks:
            tid = t.track_id
            seen_ids.add(tid)
            mx, my = t.obb.x_center, t.obb.y_center

            if tid not in self.filters:
                self.filters[tid] = TrackKalmanFilter(
                    mx, my, self.process_noise_std, self.measurement_noise_std
                )
            else:
                self.filters[tid].update(mx, my)

            results[tid] = self.filters[tid].get_state()

        # Drop stale filters (track gone for a long time) to avoid memory growth
        stale = [tid for tid, f in self.filters.items()
                 if tid not in seen_ids
                 and f.frames_since_update > self.max_frames_without_detection]
        for tid in stale:
            del self.filters[tid]

        return results


if __name__ == "__main__":
    # Self-test: feed a noisy straight-line trajectory in, confirm the
    # Kalman filter's smoothed output has meaningfully lower error against
    # the true (noise-free) path than the raw noisy measurements do.
    np.random.seed(42)
    true_positions = [(100 + i * 5.0, 200 + i * 2.0) for i in range(60)]
    noisy_positions = [(x + np.random.normal(0, 4.0), y + np.random.normal(0, 4.0))
                        for x, y in true_positions]

    kf = TrackKalmanFilter(noisy_positions[0][0], noisy_positions[0][1])
    smoothed_positions = [(kf.x[0], kf.x[1])]
    for mx, my in noisy_positions[1:]:
        kf.predict()
        kf.update(mx, my)
        smoothed_positions.append((kf.x[0], kf.x[1]))

    def rmse(est, true):
        errs = [((ex - tx) ** 2 + (ey - ty) ** 2) ** 0.5
                for (ex, ey), (tx, ty) in zip(est, true)]
        return sum(errs) / len(errs)

    raw_rmse = rmse(noisy_positions, true_positions)
    smoothed_rmse = rmse(smoothed_positions, true_positions)

    print(f"Raw noisy measurement RMSE vs ground truth: {raw_rmse:.3f} px")
    print(f"Kalman-filtered RMSE vs ground truth:       {smoothed_rmse:.3f} px")
    print(f"Improvement: {(1 - smoothed_rmse / raw_rmse) * 100:.1f}% lower error")
    assert smoothed_rmse < raw_rmse, "Kalman filter should reduce noise, but did not!"
    print("PASS: Kalman filter measurably reduces position noise.")
