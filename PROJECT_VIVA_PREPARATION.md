# FADN Project Viva and Discussion Preparation

Use this document to explain the project exactly as implemented. The central rule is simple: separate measured evidence, implemented software, and future architecture.

## 1. The 90-second opening answer

The Full Anti-Drone Network project is currently a research EO/IR video pipeline, not a deployed multi-sensor counter-UAS weapon system. It uses a fine-tuned YOLOv8s model to detect one class, drone, then a custom ByteTrack-style tracker associates detections over time. A per-track linear Kalman filter estimates smoothed image-plane position and velocity. The pipeline produces an annotated MP4, auditable JSON and a browser dashboard.

Our most important engineering finding was an identity-continuity bug. In a real 373-frame test, the drone disappeared for 125 frames while the low-level tracker retained lost tracks for only 90 frames. The old internal track therefore expired, and the returning drone correctly received a new immutable internal track ID. To avoid confusing the operator, we added a separate identity resolver. A returning track first receives a temporary ID, such as `TEMP-1`, while motion, Kalman, appearance, size and elapsed-time evidence are collected. If the match is accepted, the old operator identity is restored; otherwise, the temporary ID becomes a new permanent identity. In the test, `TEMP-1` appeared during frames 169-175 and was restored to `ID-1` at frame 176. The system retained two internal track histories but one confirmed drone identity.

The detector achieved precision 0.956, recall 0.868, mAP50 0.907 and mAP50-95 0.577 on its validation split. The final video run processed at 47.2 FPS on an NVIDIA RTX 2000 Ada GPU. These are measured results for their stated tests, not universal field-performance guarantees.

## 2. Ten-minute presentation route

1. **Problem:** small drones are difficult visual targets and interruptions create operational identity confusion.
2. **Scope:** the working system is EO/IR video; radar, RF, acoustic fusion, georeferencing and effectors are future work.
3. **Dataset:** DUT Anti-UAV, 10,000 images, 10,109 boxes, one class, axis-aligned VOC annotations.
4. **Detection:** YOLOv8s, horizontal boxes, confidence threshold 0.25 in the demonstrated run.
5. **Tracking:** custom ByteTrack-style two-stage association and finite lost-track memory.
6. **Kalman:** image-plane state `[px, py, vx, vy]`; it smooths motion but does not provide physical range or speed.
7. **Bug:** 125 missing frames exceeded the 90-frame tracker memory.
8. **Fix:** keep immutable internal tracks, add temporary operator IDs and reconcile against dormant identities.
9. **Evidence:** two internal tracks, one confirmed identity, re-identification at frame 176, 47.2 FPS.
10. **Roadmap:** identity-labelled videos, deep appearance embeddings and a trained LSTM, then tracking metrics such as IDF1, HOTA and MOTA.

## 3. Architecture you should draw from memory

```text
Input MP4
  -> YOLOv8s HBB detections
  -> custom ByteTrack-style association
  -> per-track linear Kalman filter
  -> hybrid identity resolver
       active identities
       dormant memory
       temporary identity
       motion + appearance + size + time score
  -> annotated MP4 + detections_tracks.json
  -> real EO/IR dashboard feed
  -> SAPIENT-inspired educational JSON
```

There are two different identity layers:

```text
Internal track ID: immutable engineering history; never rewritten.
Display identity: operator-facing logical identity; may be TEMP-1, ID-1, and later recovered ID-1.
```

This separation is the key design decision. It preserves auditability while improving continuity for the operator.

## 4. Critical formulas

### Horizontal box conversion

`cx = (x1 + x2) / 2`, `cy = (y1 + y2) / 2`, `w = x2 - x1`, `h = y2 - y1`.

### Detection metrics

`Precision = TP / (TP + FP)`

`Recall = TP / (TP + FN)`

`IoU = intersection area / union area`

`mAP50` is mean Average Precision at IoU 0.50. `mAP50-95` averages AP across IoU thresholds 0.50 to 0.95.

### Linear Kalman filter

State: `x = [px, py, vx, vy]^T`

Prediction: `x- = F x` and `P- = F P F^T + Q`

Correction: `K = P- H^T (H P- H^T + R)^-1`

Updated state: `x = x- + K(z - Hx-)`

### Hybrid identity score

`C = 0.35 d_motion + 0.35 d_appearance + 0.15 d_size + 0.15 d_time`

A lower cost is better. Acceptance also uses individual gates and an ambiguity margin; the weighted score is not the only safety check.

### MOTA

`MOTA = 1 - sum(FN + FP + IDSW) / sum(GT)`

We did not report MOTA because the project does not yet have independent, frame-by-frame tracking ground truth with persistent identities. Computing it from the system output itself would be invalid.

## 5. Core technical questions and strong answers

### Q1. What exactly is implemented?

YOLOv8s EO/IR detection, custom temporal association, track lifecycle management, per-track linear Kalman estimation, temporary/dormant identity reconciliation, annotated-video output, JSON output, tests, dashboard export and SAPIENT-inspired educational JSON.

### Q2. What is not implemented?

Real radar, RF or acoustic hardware; genuine multi-sensor fusion; metric geolocation; operational effectors; a trained LSTM; deep ReID; certified or Protocol-Buffer-compatible SAPIENT networking.

### Q3. Why YOLOv8s?

It is a practical small detector with a good speed/accuracy balance, a mature training toolchain and direct support for the selected single-class dataset. The choice is supported by the measured validation result, not by a claim that it is universally best.

### Q4. Is the detector OBB?

No. It is a horizontal bounding-box detector. The shared data structure contains an angle field, but the adapter sets it to zero.

### Q5. Why not convert the dataset to OBB?

The annotations contain only `xmin`, `ymin`, `xmax`, `ymax`. They do not contain orientation or four ordered corners. Setting all angles to zero or estimating angles automatically would create pseudo-labels, not measured OBB ground truth. That would weaken scientific validity.

### Q6. When would OBB become justified?

When genuine rotated annotations are manually produced or obtained from a dataset with consistent corner ordering or orientation angles, and when the expected localization benefit is validated against the additional annotation and inference cost.

### Q7. Is this official ByteTrack?

No. It is a simplified custom ByteTrack-style tracker. It borrows the idea of associating high- and lower-confidence detections but uses project-specific motion and lifecycle logic.

### Q8. Why does the tracker have finite memory?

Unlimited retention creates stale tracks, increasing incorrect associations and memory use. A finite lifecycle is correct low-level tracker behavior. Long-term identity is handled in a separate resolver.

### Q9. What caused the same drone to receive a second ID?

The drone was absent for 125 frames, but the tracker retained lost tracks for 90 frames. The old internal track expired before the drone returned, so a new internal track was created.

### Q10. Why not simply increase `max_time_lost` above 125?

That fixes one video but is fragile. Long tracker retention increases the chance of matching a new drone to a stale track, and the correct value depends on frame rate and scene density. The resolver keeps longer logical memory without corrupting low-level history.

### Q11. Why keep the old and new internal IDs?

They record what the tracker actually did. Rewriting them would hide an expiration and make debugging, metrics and forensic review unreliable.

### Q12. What is a temporary ID?

An immediate operator-facing label assigned when a new internal track may correspond to a dormant identity. Detection is displayed immediately; only the identity decision is pending.

### Q13. Why wait eight frames?

One frame is vulnerable to blur, scale changes and accidental visual similarity. Eight frames provide a short evidence sequence. At 24 FPS, eight frames are approximately 0.33 seconds.

### Q14. What if it is not the old drone?

If no acceptable dormant match is confirmed before the provisional limit, the temporary identity is promoted to a new permanent ID. It is not forced into an old identity.

### Q15. What was the result in the approved video?

373 frames, 240 detections, two immutable internal tracks, one temporary identity, one confirmed operator identity, one successful re-identification, `TEMP-1` on frames 169-175 and `ID-1` restored at frame 176.

### Q16. What evidence caused the restoration?

The accepted hybrid cost was 0.2404 and appearance similarity was 0.9953, together with motion, Kalman, box-size and time evidence over the configured confirmation window.

### Q17. Does high appearance similarity prove the same identity?

No. It is supporting evidence. Similar drones can look alike, especially at low resolution. That is why appearance is combined with motion, size, elapsed time and acceptance gates.

### Q18. What appearance descriptor is used?

A compact normalized hue/saturation and brightness histogram from the detected crop. It is not a trained deep ReID embedding.

### Q19. Why use Kalman filtering?

It smooths noisy center measurements, estimates velocity and predicts short gaps. Its uncertainty also helps interpret how trustworthy the motion prediction is.

### Q20. Does Kalman identify the drone?

No. Kalman predicts state, not semantic identity. It is one input to association and reconciliation.

### Q21. Is the reported velocity physical?

No. It is pixels per frame. Without camera calibration, pose, depth or range, it cannot be converted defensibly into metres per second.

### Q22. What is the difference between tracker memory and identity retention?

Tracker memory governs revival of the same low-level track. Identity retention keeps a dormant operator identity available for a higher-level comparison after the internal track has expired.

### Q23. Why is identity retention expressed in seconds?

Seconds are portable across video frame rates. The implementation converts the configured duration to frames using the actual video FPS.

### Q24. What happens at the end of a finite video with an unresolved TEMP ID?

It is recorded as unresolved or abandoned according to the final state. The system does not silently invent a permanent identity.

### Q25. Is LSTM currently used in the measured result?

No trained LSTM is enabled. The system defines a temporal-model interface and uses a deterministic motion fallback. Calling the present result “LSTM-based” would be inaccurate.

### Q26. Why not enable an untrained LSTM?

Random weights produce meaningless scores and may make the system appear more advanced while reducing validity. A temporal network should be enabled only after training and independent validation.

### Q27. What data are needed to train an LSTM?

Identity-labelled trajectories containing correct persistent IDs across visibility, disappearance, re-entry, motion changes, multiple drones and hard negative pairs. Training and evaluation videos must be separated to avoid leakage.

### Q28. What would the LSTM predict?

Preferably a temporal motion embedding or future-state distribution used as one evidence term. It should not make an unconstrained final identity decision by itself.

### Q29. What would deep ReID add?

A learned appearance embedding that is more robust than color histograms to lighting, scale and viewpoint. Small-drone resolution may still limit its value, so it must be experimentally validated.

### Q30. How do you avoid choosing between two similar dormant drones?

Use individual evidence gates, a combined-cost threshold and an ambiguity margin between the best and second-best candidates. If the evidence is ambiguous, keep the temporary identity or create a new one instead of forcing a match.

### Q31. What do precision and recall mean here?

Precision 0.956 means most retained validation detections were correct. Recall 0.868 means most ground-truth drones were found, with remaining misses. Both refer to detector validation.

### Q32. Why is mAP50-95 lower than mAP50?

The stricter metric requires increasingly precise box localization across higher IoU thresholds. Small objects make localization error proportionally more significant.

### Q33. Are the detector metrics tracking metrics?

No. Detection AP cannot measure ID switches, fragmentation or long-term identity preservation.

### Q34. Why was MOTA not used?

MOTA needs independent persistent ground-truth identities across frames. The selected dataset provides detection boxes, and the demonstration video has no verified tracking annotation.

### Q35. What should be reported once tracking ground truth exists?

MOTA, IDF1, HOTA, identity switches, fragmentation, mostly tracked/lost, and re-identification precision/recall. Identity metrics should accompany MOTA because MOTA is strongly influenced by FP and FN.

### Q36. Could you annotate the current video and compute MOTA?

Yes, if every frame is independently annotated with boxes, persistent IDs, visibility and entry/exit rules, and the annotation is not derived from the predictions. One video would still be a case study, not a general benchmark.

### Q37. What does 47.2 FPS mean?

It is the measured average full-pipeline processing rate for this 373-frame run on the stated RTX 2000 Ada machine. It does not guarantee the same result on other videos, resolutions or hardware.

### Q38. How many video frames can be processed per minute at 47.2 FPS?

Approximately `47.2 x 60 = 2,832` frames per processing minute. For a 24 FPS source, one minute of video contains 1,440 frames, so this measured run was faster than real time.

### Q39. Why did earlier runs show a different FPS?

Timing varies with warm-up, I/O, model loading, output encoding, GPU state and code version. Every speed claim must name the exact run and hardware.

### Q40. What is SAPIENT in this project?

The output is educational JSON inspired by SAPIENT concepts and identifies the standard reference. It is not Protocol Buffers wire compatibility, node registration, conformance certification or NATO deployment approval.

### Q41. Why use a SAPIENT-inspired structure at all?

It encourages explicit timestamps, node IDs, report types, object IDs, coordinates and classifications, making later integration easier while preserving an honest capability boundary.

### Q42. What is wrong with claiming real fusion?

Only EO/IR data are available. Multiple software stages are not multiple sensors. Fusion requires independent sensor observations, calibration, timing and uncertainty models.

### Q43. Why are radar, RF and acoustic shown in the dashboard?

Only as explicit unavailable capability boundaries and roadmap items. They are not animated or populated with fabricated operational measurements.

### Q44. Does the dashboard display the raw video?

The current static dashboard replays the structured geometry and identity results from the exported JSON. The annotated MP4 is a separate output. Future work can synchronize the video element and JSON timeline.

### Q45. Why export both MP4 and JSON?

The MP4 is useful for human visual inspection. JSON supports audit, metrics, dashboard replay, integration and reproducibility.

### Q46. How is deployment kept clean?

Environment validation, unit tests, a documented single-video command, deterministic output directories, a dashboard conversion step and a PR-based Git workflow. Models and large user videos are managed separately from source changes when appropriate.

### Q47. What are the main failure modes?

Missed detections, false positives, similar drone appearances, abrupt motion, long disappearances, multiple candidate identities, severe scale/view changes, camera motion and domain shift.

### Q48. What is the most important current limitation?

The identity result is validated on one approved video without independent identity ground truth. It demonstrates that the designed behavior works for that case, not general re-identification accuracy.

### Q49. What is the next scientifically correct experiment?

Build a labelled suite with same-drone returns and different-drone negative cases, define identity metrics, freeze thresholds, evaluate blind test videos and report uncertainty and failure cases.

### Q50. What is the project’s strongest contribution?

It discovered a real lifecycle failure and corrected it without hiding low-level history: immediate temporary identity, auditable multi-frame evidence, conservative reconciliation and honest capability reporting.

## 6. Difficult challenge questions

### “Your system changed ID first, so is the bug really solved?”

The internal tracker ID still changes by design after expiry. The operator identity is the part being repaired. During uncertainty, the system visibly says `TEMP-1`; after evidence, it restores `ID-1`. This is safer than pretending certainty in the first returning frame.

### “Why should I trust one successful re-identification?”

You should trust that this test case behaves as reported because the event log, frame labels and JSON agree. You should not infer population-level re-identification accuracy. That requires a labelled evaluation suite.

### “Why not just call the new track ID-1 immediately?”

Immediate restoration can merge a genuinely new drone with an old identity. Temporary labelling exposes uncertainty and permits evidence accumulation.

### “Is a color histogram enough?”

No for a general operational system. It is a lightweight, real, deterministic signal that worked in this controlled case. Deep ReID and better data are planned, but should be enabled only after validation.

### “Does the project detect military intent?”

No. It detects a visual drone class. Intent, payload and threat classification are outside the implemented evidence.

### “Can it neutralize a drone?”

No. There is no effector control. The project is detection, tracking, state estimation, identity reconciliation and structured reporting.

## 7. Live demonstration checklist

1. Open PowerShell in the project directory.
2. Run `python check_environment.py` and show Python 3.12, OpenCV, Torch, Ultralytics and CUDA.
3. Run `python -m unittest discover -s tests -v`; do not continue if any test fails.
4. Confirm the input MP4 and `models/best.pt` with `Get-Item -LiteralPath`.
5. Run the documented `detect_and_track_video.py` command with a new output directory.
6. Show the terminal summary: 373 frames, 2 internal tracks, 1 confirmed identity, 1 re-identification.
7. Open the annotated MP4 and point out `TEMP-1` at re-entry and restored `ID-1` after confirmation.
8. Inspect `detections_tracks.json` for `provisional_created` and `identity_reidentified`.
9. Convert the JSON using `export_for_dashboard.py`.
10. Serve the folder over HTTP and open the dashboard. Pause at frame 170, then frame 176.
11. Explain that the dashboard is displaying pixels, not physical metres.
12. Keep the original video, baseline output and identity-resolver output available for the three-way comparison.

## 8. What not to claim

- Do not say the current system uses a trained LSTM.
- Do not call the detector OBB.
- Do not call the custom tracker the official ByteTrack implementation.
- Do not call the JSON certified or wire-compatible SAPIENT.
- Do not claim real radar, RF, acoustic fusion, geolocation or effectors.
- Do not convert pixel velocity into metres per second.
- Do not describe detector mAP as tracking accuracy.
- Do not report MOTA without independent tracking ground truth.
- Do not generalize one video’s 47.2 FPS or re-identification result to all scenes.
- Do not claim the system recognizes intent, payload or military status.

## 9. Abbreviation glossary

- **AI:** Artificial Intelligence
- **C-UAS:** Counter-Unmanned Aircraft System
- **EO/IR:** Electro-Optical / Infrared
- **FADN:** Full Anti-Drone Network
- **FN / FP / TP:** False Negative / False Positive / True Positive
- **FPS:** Frames Per Second
- **GNSS:** Global Navigation Satellite System
- **HBB:** Horizontal Bounding Box
- **HOTA:** Higher Order Tracking Accuracy
- **IDF1:** Identity F1 Score
- **IDSW:** Identity Switch
- **IoU:** Intersection over Union
- **JSON:** JavaScript Object Notation
- **LSTM:** Long Short-Term Memory
- **mAP:** mean Average Precision
- **MOTA:** Multiple Object Tracking Accuracy
- **OBB:** Oriented Bounding Box
- **RF:** Radio Frequency
- **ReID:** Re-Identification
- **SAPIENT:** Sensing for Asset Protection with Integrated Electronic Networked Technology
- **STANREC:** NATO Standardization Recommendation
- **UAS / UAV:** Unmanned Aircraft System / Unmanned Aerial Vehicle
- **VOC:** Visual Object Classes annotation format
- **YOLO:** You Only Look Once

## 10. Final one-sentence defense

“The project is valuable because it turns a real identity failure into an auditable, conservative and testable design, while clearly separating what is measured today from what requires future sensors, labels and trained temporal models.”
