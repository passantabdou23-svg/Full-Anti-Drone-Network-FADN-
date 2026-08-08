"""Operator-facing identity reconciliation for interrupted visual tracks.

The low-level tracker owns immutable ``track_id`` values.  This module adds a
separate identity layer so a new internal track can be labelled ``TEMP-n``
while it is compared with dormant identities.  A provisional track is either
merged back into an older ``ID-n`` or promoted to a new permanent identity.

The default resolver uses evidence that is available in this repository now:

* motion and Kalman state,
* bounding-box size,
* elapsed time, and
* a compact colour/brightness appearance descriptor extracted from the real
  video crop.

``temporal_model`` is an explicit extension point for a future *trained* LSTM
motion model.  No untrained neural network is used: random LSTM weights would
create impressive-looking but meaningless identity scores.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Dict, Iterable, List, Optional, Protocol, Tuple

import cv2
import numpy as np


class TemporalMotionModel(Protocol):
    """Interface for a future trained temporal model.

    Implementations return a normalized non-negative motion distance where
    zero is an exact match.  The deterministic fallback remains active when no
    model is supplied.
    """

    name: str

    def normalized_distance(self, identity, observation, frame_gap: int) -> float:
        ...


@dataclass
class TrackObservation:
    internal_track_id: int
    center: Tuple[float, float]
    size: Tuple[float, float]
    velocity: Tuple[float, float]
    score: float
    appearance: Optional[np.ndarray]
    kf_state: Optional[dict]


@dataclass
class IdentityRecord:
    identity_id: int
    internal_track_ids: List[int]
    last_seen_frame: int
    last_center: Tuple[float, float]
    last_size: Tuple[float, float]
    last_velocity: Tuple[float, float]
    appearance: Optional[np.ndarray]
    appearance_samples: int
    active_internal_track_id: Optional[int]
    last_kf_state: Optional[dict] = None


@dataclass
class ProvisionalIdentity:
    temporary_id: str
    internal_track_id: int
    created_frame: int
    candidate_identity_ids: List[int]
    age_frames: int = 0
    score_history: Dict[int, List[float]] = field(default_factory=dict)
    appearance_history: Dict[int, List[float]] = field(default_factory=dict)


def _normalized(vector: np.ndarray) -> Optional[np.ndarray]:
    vector = np.asarray(vector, dtype=np.float32).reshape(-1)
    norm = float(np.linalg.norm(vector))
    if norm <= 1e-9:
        return None
    return vector / norm


def extract_appearance_descriptor(frame, obb) -> Optional[np.ndarray]:
    """Return a small, normalized appearance descriptor for a detected crop.

    The descriptor deliberately avoids claiming learned ReID.  It combines a
    hue/saturation histogram with a brightness histogram.  This is inexpensive
    and useful as supporting evidence, while motion/time gates remain active.
    """

    if frame is None or getattr(frame, "size", 0) == 0:
        return None

    height, width = frame.shape[:2]
    x1 = max(0, int(round(obb.x_center - obb.width / 2.0)))
    y1 = max(0, int(round(obb.y_center - obb.height / 2.0)))
    x2 = min(width, int(round(obb.x_center + obb.width / 2.0)))
    y2 = min(height, int(round(obb.y_center + obb.height / 2.0)))
    if x2 - x1 < 4 or y2 - y1 < 4:
        return None

    crop = frame[y1:y2, x1:x2]
    if crop.size == 0:
        return None

    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    hs_hist = cv2.calcHist([hsv], [0, 1], None, [12, 4], [0, 180, 0, 256]).reshape(-1)
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    gray_hist = cv2.calcHist([gray], [0], None, [16], [0, 256]).reshape(-1)

    hs_hist = _normalized(hs_hist)
    gray_hist = _normalized(gray_hist)
    if hs_hist is None or gray_hist is None:
        return None
    return _normalized(np.concatenate([0.75 * hs_hist, 0.25 * gray_hist]))


def cosine_distance(first: Optional[np.ndarray], second: Optional[np.ndarray]) -> float:
    """Cosine distance in [0, 1], or a neutral value when evidence is absent."""

    if first is None or second is None:
        return 0.5
    similarity = float(np.clip(np.dot(first, second), 0.0, 1.0))
    return 1.0 - similarity


class IdentityResolver:
    """Maintain confirmed and provisional identities above immutable tracks."""

    def __init__(
        self,
        fps: float,
        retention_seconds: float = 10.0,
        confirm_frames: int = 8,
        max_provisional_frames: int = 24,
        match_threshold: float = 0.62,
        min_appearance_similarity: float = 0.20,
        ambiguity_margin: float = 0.08,
        temporal_model: Optional[TemporalMotionModel] = None,
    ):
        if fps <= 0:
            raise ValueError("fps must be positive")
        if retention_seconds <= 0:
            raise ValueError("retention_seconds must be positive")
        if confirm_frames <= 0:
            raise ValueError("confirm_frames must be positive")
        if max_provisional_frames < confirm_frames:
            raise ValueError("max_provisional_frames must be >= confirm_frames")

        self.fps = float(fps)
        self.retention_seconds = float(retention_seconds)
        self.retention_frames = max(1, int(round(self.fps * self.retention_seconds)))
        self.confirm_frames = int(confirm_frames)
        self.max_provisional_frames = int(max_provisional_frames)
        self.match_threshold = float(match_threshold)
        self.min_appearance_similarity = float(min_appearance_similarity)
        self.ambiguity_margin = float(ambiguity_margin)
        self.temporal_model = temporal_model

        self.identities: Dict[int, IdentityRecord] = {}
        self.internal_assignments: Dict[int, dict] = {}
        self.provisionals: Dict[int, ProvisionalIdentity] = {}
        self.identity_events: List[dict] = []
        self.identity_aliases: Dict[str, str] = {}
        self._next_identity_id = 1
        self._next_temporary_id = 1

    @staticmethod
    def _event(frame_id: int, event: str, **fields) -> dict:
        return {"frame_id": int(frame_id), "event": event, **fields}

    @staticmethod
    def _ema(old: Optional[np.ndarray], new: Optional[np.ndarray], alpha: float = 0.20):
        if new is None:
            return old
        if old is None:
            return new.copy()
        return _normalized((1.0 - alpha) * old + alpha * new)

    @staticmethod
    def _track_observation(frame, track, kf_states) -> TrackObservation:
        kf_state = (kf_states or {}).get(track.track_id)
        if kf_state:
            velocity = (float(kf_state.get("vx", 0.0)), float(kf_state.get("vy", 0.0)))
        else:
            velocity = tuple(float(value) for value in getattr(track, "velocity", (0.0, 0.0)))
        return TrackObservation(
            internal_track_id=int(track.track_id),
            center=(float(track.obb.x_center), float(track.obb.y_center)),
            size=(float(track.obb.width), float(track.obb.height)),
            velocity=velocity,
            score=float(track.score),
            appearance=extract_appearance_descriptor(frame, track.obb),
            kf_state=kf_state,
        )

    def _create_identity(self, observation: TrackObservation, frame_id: int, source: str) -> dict:
        identity_id = self._next_identity_id
        self._next_identity_id += 1
        record = IdentityRecord(
            identity_id=identity_id,
            internal_track_ids=[observation.internal_track_id],
            last_seen_frame=int(frame_id),
            last_center=observation.center,
            last_size=observation.size,
            last_velocity=observation.velocity,
            appearance=observation.appearance,
            appearance_samples=1 if observation.appearance is not None else 0,
            active_internal_track_id=observation.internal_track_id,
            last_kf_state=observation.kf_state,
        )
        self.identities[identity_id] = record
        assignment = {
            "internal_track_id": observation.internal_track_id,
            "identity_id": identity_id,
            "display_id": f"ID-{identity_id}",
            "identity_status": "confirmed",
            "provisional_id": None,
            "identity_confidence": 1.0,
            "identity_source": source,
        }
        self.internal_assignments[observation.internal_track_id] = assignment
        return assignment

    def _create_provisional(
        self, observation: TrackObservation, frame_id: int, candidate_ids: Iterable[int]
    ) -> dict:
        temporary_id = f"TEMP-{self._next_temporary_id}"
        self._next_temporary_id += 1
        candidate_ids = sorted(set(int(value) for value in candidate_ids))
        provisional = ProvisionalIdentity(
            temporary_id=temporary_id,
            internal_track_id=observation.internal_track_id,
            created_frame=int(frame_id),
            candidate_identity_ids=candidate_ids,
            score_history={identity_id: [] for identity_id in candidate_ids},
            appearance_history={identity_id: [] for identity_id in candidate_ids},
        )
        self.provisionals[observation.internal_track_id] = provisional
        assignment = {
            "internal_track_id": observation.internal_track_id,
            "identity_id": None,
            "display_id": temporary_id,
            "identity_status": "provisional",
            "provisional_id": temporary_id,
            "identity_confidence": 0.0,
            "identity_source": "dormant_candidate_check",
        }
        self.internal_assignments[observation.internal_track_id] = assignment
        return assignment

    def _update_identity_record(
        self, record: IdentityRecord, observation: TrackObservation, frame_id: int
    ) -> None:
        record.last_seen_frame = int(frame_id)
        record.last_center = observation.center
        record.last_size = observation.size
        record.last_velocity = observation.velocity
        record.last_kf_state = observation.kf_state
        record.active_internal_track_id = observation.internal_track_id
        if observation.internal_track_id not in record.internal_track_ids:
            record.internal_track_ids.append(observation.internal_track_id)
        if observation.appearance is not None:
            record.appearance = self._ema(record.appearance, observation.appearance)
            record.appearance_samples += 1

    def _motion_distance(
        self, record: IdentityRecord, observation: TrackObservation, frame_gap: int
    ) -> float:
        if self.temporal_model is not None:
            value = self.temporal_model.normalized_distance(record, observation, frame_gap)
            return max(0.0, float(value))

        old_x, old_y = record.last_center
        vx, vy = record.last_velocity
        # Trust velocity only briefly; long off-screen motion is fundamentally
        # uncertain and should enlarge the gate instead of extrapolating forever.
        trusted_steps = min(frame_gap, max(1, int(round(self.fps * 0.5))))
        decay = 0.85
        displacement_scale = (1.0 - decay ** trusted_steps) / (1.0 - decay)
        predicted_x = old_x + vx * displacement_scale
        predicted_y = old_y + vy * displacement_scale

        distance = math.hypot(
            observation.center[0] - predicted_x,
            observation.center[1] - predicted_y,
        )
        old_diag = max(1.0, math.hypot(*record.last_size))
        speed = math.hypot(vx, vy)
        uncertainty = old_diag * 4.0 + frame_gap * 3.0 + speed * min(frame_gap, 12) * 0.15
        return distance / max(40.0, uncertainty)

    def _candidate_score(
        self, record: IdentityRecord, observation: TrackObservation, frame_id: int
    ) -> Tuple[float, float]:
        frame_gap = max(1, int(frame_id) - record.last_seen_frame)
        motion = min(self._motion_distance(record, observation, frame_gap), 2.0)
        appearance = cosine_distance(record.appearance, observation.appearance)

        old_diag = max(1.0, math.hypot(*record.last_size))
        new_diag = max(1.0, math.hypot(*observation.size))
        size = min(abs(math.log(new_diag / old_diag)), 2.0)
        elapsed = min(frame_gap / self.retention_frames, 1.0)

        cost = 0.35 * motion + 0.35 * appearance + 0.15 * size + 0.15 * elapsed
        return float(cost), float(1.0 - appearance)

    def _dormant_candidates(self, frame_id: int) -> List[int]:
        return [
            identity_id
            for identity_id, record in self.identities.items()
            if record.active_internal_track_id is None
            and int(frame_id) - record.last_seen_frame <= self.retention_frames
        ]

    def _resolve_provisional(
        self, provisional: ProvisionalIdentity, identity_id: int, observation, frame_id, score
    ) -> dict:
        record = self.identities[identity_id]
        self._update_identity_record(record, observation, frame_id)
        assignment = self.internal_assignments[observation.internal_track_id]
        assignment.update({
            "identity_id": identity_id,
            "display_id": f"ID-{identity_id}",
            "identity_status": "reidentified",
            "identity_confidence": round(max(0.0, min(1.0, 1.0 - score)), 3),
            "identity_source": "dormant_identity_reconciliation",
        })
        self.identity_aliases[provisional.temporary_id] = f"ID-{identity_id}"
        del self.provisionals[observation.internal_track_id]
        return assignment

    def _promote_provisional(self, provisional, observation, frame_id) -> dict:
        assignment = self._create_identity(observation, frame_id, "provisional_promotion")
        assignment["provisional_id"] = provisional.temporary_id
        self.identity_aliases[provisional.temporary_id] = assignment["display_id"]
        self.provisionals.pop(observation.internal_track_id, None)
        return assignment

    def _score_and_maybe_resolve(self, provisional, observation, frame_id, events):
        provisional.age_frames += 1
        valid_candidates = []
        for identity_id in provisional.candidate_identity_ids:
            record = self.identities.get(identity_id)
            if record is None or record.active_internal_track_id is not None:
                continue
            if frame_id - record.last_seen_frame > self.retention_frames:
                continue
            cost, appearance_similarity = self._candidate_score(record, observation, frame_id)
            provisional.score_history[identity_id].append(cost)
            provisional.appearance_history[identity_id].append(appearance_similarity)
            valid_candidates.append(identity_id)

        averages = []
        for identity_id in valid_candidates:
            costs = provisional.score_history[identity_id]
            appearances = provisional.appearance_history[identity_id]
            averages.append((
                sum(costs) / len(costs),
                identity_id,
                sum(appearances) / len(appearances),
            ))
        averages.sort()

        assignment = self.internal_assignments[observation.internal_track_id]
        if averages:
            best_cost, best_identity, best_appearance = averages[0]
            assignment["identity_confidence"] = round(max(0.0, min(1.0, 1.0 - best_cost)), 3)
            assignment["candidate_identity_id"] = best_identity
            assignment["candidate_cost"] = round(best_cost, 4)

            second_cost = averages[1][0] if len(averages) > 1 else None
            has_margin = second_cost is None or second_cost - best_cost >= self.ambiguity_margin
            if (
                provisional.age_frames >= self.confirm_frames
                and best_cost <= self.match_threshold
                and best_appearance >= self.min_appearance_similarity
                and has_margin
            ):
                assignment = self._resolve_provisional(
                    provisional, best_identity, observation, frame_id, best_cost
                )
                events.append(self._event(
                    frame_id,
                    "identity_reidentified",
                    provisional_id=provisional.temporary_id,
                    identity_id=best_identity,
                    internal_track_id=observation.internal_track_id,
                    match_cost=round(best_cost, 4),
                    appearance_similarity=round(best_appearance, 4),
                ))
                return assignment

        if provisional.age_frames >= self.max_provisional_frames:
            assignment = self._promote_provisional(provisional, observation, frame_id)
            events.append(self._event(
                frame_id,
                "provisional_promoted",
                provisional_id=provisional.temporary_id,
                identity_id=assignment["identity_id"],
                internal_track_id=observation.internal_track_id,
            ))
        return assignment

    def step(self, frame_id: int, frame, active_tracks, kf_states=None):
        """Update identity state and return assignments plus this frame's events."""

        active_tracks = list(active_tracks)
        active_internal_ids = {int(track.track_id) for track in active_tracks}
        events = []

        # Confirmed identities become dormant when their current internal track
        # disappears.  Their memory remains available for long-term comparison.
        for record in self.identities.values():
            internal_id = record.active_internal_track_id
            if internal_id is not None and internal_id not in active_internal_ids:
                record.active_internal_track_id = None
                events.append(self._event(
                    frame_id,
                    "identity_dormant",
                    identity_id=record.identity_id,
                    last_internal_track_id=internal_id,
                ))

        # A provisional track that vanishes before a decision is auditable but
        # does not become a permanent identity by itself.
        for internal_id, provisional in list(self.provisionals.items()):
            if internal_id not in active_internal_ids:
                events.append(self._event(
                    frame_id,
                    "provisional_abandoned",
                    provisional_id=provisional.temporary_id,
                    internal_track_id=internal_id,
                ))
                self.provisionals.pop(internal_id, None)
                self.internal_assignments.pop(internal_id, None)

        assignments = {}
        for track in active_tracks:
            observation = self._track_observation(frame, track, kf_states)
            internal_id = observation.internal_track_id
            assignment = self.internal_assignments.get(internal_id)

            if assignment is None:
                candidates = self._dormant_candidates(frame_id)
                if candidates:
                    assignment = self._create_provisional(observation, frame_id, candidates)
                    events.append(self._event(
                        frame_id,
                        "provisional_created",
                        provisional_id=assignment["provisional_id"],
                        internal_track_id=internal_id,
                        candidate_identity_ids=candidates,
                    ))
                else:
                    assignment = self._create_identity(observation, frame_id, "new_identity")
                    events.append(self._event(
                        frame_id,
                        "identity_created",
                        identity_id=assignment["identity_id"],
                        internal_track_id=internal_id,
                    ))

            if assignment["identity_status"] == "provisional":
                provisional = self.provisionals[internal_id]
                assignment = self._score_and_maybe_resolve(
                    provisional, observation, frame_id, events
                )
            else:
                record = self.identities[assignment["identity_id"]]
                self._update_identity_record(record, observation, frame_id)

            assignments[internal_id] = dict(assignment)

        self.identity_events.extend(events)
        return assignments, events

    def finalize(self, frame_id: int) -> List[dict]:
        """Record provisional tracks that remain unresolved at end of a finite video."""

        events = []
        for internal_id, provisional in list(self.provisionals.items()):
            assignment = self.internal_assignments.get(internal_id)
            if assignment is None:
                continue
            # There is no observation at EOF, so keep an auditable unresolved
            # temporary identity rather than fabricating a permanent match.
            events.append(self._event(
                frame_id,
                "provisional_unresolved_at_end",
                provisional_id=provisional.temporary_id,
                internal_track_id=internal_id,
            ))
        self.identity_events.extend(events)
        return events

    def apply_final_alias(self, track_dict: dict) -> dict:
        """Add final identity fields while retaining the at-frame audit values."""

        result = dict(track_dict)
        display_at_frame = result.get("display_id")
        final_display = self.identity_aliases.get(display_at_frame, display_at_frame)
        result["display_id_at_frame"] = display_at_frame
        result["final_display_id"] = final_display
        if isinstance(final_display, str) and final_display.startswith("ID-"):
            result["final_identity_id"] = int(final_display.split("-", 1)[1])
        else:
            result["final_identity_id"] = result.get("identity_id")
        return result

    def summary(self) -> dict:
        event_counts = {}
        for event in self.identity_events:
            name = event["event"]
            event_counts[name] = event_counts.get(name, 0) + 1
        return {
            "confirmed_identity_count": len(self.identities),
            "temporary_identity_count": self._next_temporary_id - 1,
            "retention_seconds": self.retention_seconds,
            "retention_frames": self.retention_frames,
            "confirmation_frames": self.confirm_frames,
            "max_provisional_frames": self.max_provisional_frames,
            "match_threshold": self.match_threshold,
            "temporal_model": getattr(self.temporal_model, "name", "deterministic_motion_fallback"),
            "identity_aliases": dict(self.identity_aliases),
            "event_counts": event_counts,
        }
