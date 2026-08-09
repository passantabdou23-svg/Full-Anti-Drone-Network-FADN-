# Temporary identity reconciliation

## Why this layer exists

The low-level tracker can retain an ID through a short interruption. Once its
lost-track timeout expires, a returning detection correctly starts a new
*internal* track. Reusing or mutating that internal ID would damage the audit
trail, so the pipeline now adds a separate operator-facing identity layer.

The two identifiers have different jobs:

| Field | Meaning |
|---|---|
| `internal_track_id` | Immutable ID created by the low-level tracker |
| `display_id` | ID shown at that frame: `TEMP-n` or confirmed `ID-n` |
| `final_display_id` | Resolved identity after the finite video is complete |
| `identity_id` | Confirmed numeric identity, or `null` while provisional |

## State flow

1. A track with no plausible dormant candidates receives a permanent `ID-n`.
2. When that track disappears, its identity becomes dormant for 10 seconds by
   default.
3. A new internal track that appears while a dormant candidate exists receives
   `TEMP-n` immediately; detection and display are never delayed.
4. The resolver collects 8 frames of evidence by default.
5. A strict, unambiguous match restores the old `ID-n`.
6. If no match is accepted within 24 frames, `TEMP-n` is promoted to a new
   permanent `ID-n`.
7. If a provisional track vanishes before a decision, the event is recorded as
   abandoned. If the video ends first, it remains explicitly unresolved.

## Evidence and decision

The current hybrid cost is:

```text
C = 0.35 d_motion + 0.35 d_appearance + 0.15 d_size + 0.15 d_time
```

- `d_motion`: distance from the short-term predicted position, normalized by
  box scale, time gap, speed, and uncertainty.
- `d_appearance`: cosine distance between compact colour/brightness histograms
  extracted from the real image crops.
- `d_size`: logarithmic change in bounding-box diagonal.
- `d_time`: fraction of the dormant retention window already consumed.

The best candidate must satisfy the match threshold, the minimum appearance
gate, and an ambiguity margin over the second-best candidate. A decision uses
the mean evidence across the confirmation window, not a single frame.

This is supporting visual evidence, not a learned person/drone ReID network.
Very small drones, illumination changes, and similar-looking drones can still
produce ambiguous appearance evidence.

## LSTM status

`TemporalMotionModel` is an extension point for a future trained LSTM. It can
replace the deterministic motion-distance term while appearance, size, time,
and ambiguity gates remain active. No random or untrained LSTM is enabled:
doing so would create numerical scores without learned identity information.

A production LSTM requires identity-labelled trajectories with disappearances,
re-entries, multiple drones, camera motion, and hard negative examples. Its
acceptance criterion should be lower ID-switch and false-revival rates on a
held-out set than this deterministic baseline.

## JSON audit trail

Each frame contains `identity_events` and enriched `tracks`. The top-level
`identity_summary` reports counts, configuration, temporal-model name, aliases,
and event totals. Historical provisional frames retain
`display_id_at_frame=TEMP-n`; when resolved, `final_display_id` points to the
confirmed identity.

SAPIENT-formatted detection reports use the at-frame operator identity. Thus a
provisional report remains visibly provisional and later reports use the
reconciled permanent identity.

## Measured regression video

The approved 373-frame, 23.976 FPS test video produced:

| Result | Value |
|---|---:|
| Immutable internal tracks | 2 |
| Confirmed operator identities | 1 |
| Temporary identities created | 1 |
| Successful re-identifications | 1 |
| Provisional interval | frames 169-175 |
| Old ID restored | frame 176 |
| Processing throughput | 35.6 FPS |

The first internal track ended before the second began; the resolver preserved
that history while mapping `TEMP-1` to `ID-1`. Throughput is a single observed
GPU run, not a general performance guarantee.

## Verification commands

```powershell
python -m unittest discover -s tests -v

python detect_and_track_video.py `
  --video ".\input.mp4" `
  --weights ".\models\best.pt" `
  --out ".\video_results" `
  --device 0
```

For a comparison run only:

```powershell
python detect_and_track_video.py `
  --video ".\input.mp4" `
  --weights ".\models\best.pt" `
  --out ".\raw_tracker_results" `
  --device 0 `
  --disable_identity_resolver
```
