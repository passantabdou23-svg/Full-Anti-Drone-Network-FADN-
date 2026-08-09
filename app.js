"use strict";

document.addEventListener("DOMContentLoaded", () => {
    const state = { feed: null, index: 0, playing: true, timer: null, events: [] };
    const byId = id => document.getElementById(id);
    const canvas = byId("camera-canvas");
    const ctx = canvas.getContext("2d");

    const fmtPct = value => value == null ? "N/A" : `${(Number(value) * 100).toFixed(1)}%`;
    const fmtNum = (value, digits = 1) => value == null ? "N/A" : Number(value).toFixed(digits);
    const escapeHtml = value => String(value ?? "").replace(/[&<>'"]/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[char]));

    async function loadFeed() {
        try {
            const response = await fetch("simulation_feed.json");
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            state.feed = await response.json();
            state.events = state.feed.frames.flatMap(frame =>
                (frame.identity_events || []).map(event => ({ ...event, frame_id: event.frame_id ?? frame.frame_id }))
            );
            configureDashboard();
            const firstTrack = state.feed.frames.findIndex(frame => (frame.bytetrack_tracks || []).length > 0);
            state.index = Math.max(firstTrack, 0);
            byId("frame-slider").max = Math.max(state.feed.frames.length - 1, 0);
            byId("frame-slider").value = state.index;
            render();
            state.timer = setInterval(stepReplay, 130);
        } catch (error) {
            byId("data-mode-value").textContent = "LOAD ERROR";
            byId("data-source-summary").textContent = `Feed could not be loaded: ${error.message}`;
            byId("run-state").textContent = "ERROR";
        }
    }

    function configureDashboard() {
        const meta = state.feed.metadata || {};
        const caps = meta.capabilities || {};
        const summary = state.feed.identity_summary || {};
        const real = meta.feed_type === "real_eoir";

        byId("data-mode-value").textContent = real ? "REAL EO/IR OUTPUT" : "SIMULATION";
        byId("sensor-mode-value").textContent = caps.eoir && !caps.multi_sensor_fusion ? "EO/IR ONLY" : "DECLARED FEED";
        byId("coordinate-status").textContent = caps.georeferencing ? "GEOREFERENCED" : "NO GEOREFERENCE";
        byId("model-value").textContent = meta.model || "YOLOv8s";
        byId("video-name").textContent = meta.original_video || "Processed video result";
        byId("run-state").textContent = "RESULT REPLAY";
        byId("data-source-summary").textContent = `${meta.source || "Local result"} · ${meta.original_video || "unknown video"}`;

        byId("confirmed-count").textContent = summary.confirmed_identity_count ?? meta.unique_confirmed_identities ?? 0;
        byId("temporary-count").textContent = summary.temporary_identity_count ?? 0;
        byId("internal-count").textContent = meta.unique_internal_tracks ?? 0;
        byId("reid-count").textContent = summary.event_counts?.identity_reidentified ?? 0;
        byId("resolver-mode").textContent = String(summary.temporal_model || "deterministic hybrid").replaceAll("_", " ").toUpperCase();
        byId("retention-value").textContent = summary.retention_seconds != null ? `${summary.retention_seconds}s / ${summary.retention_frames} frames` : "N/A";
        byId("confirmation-value").textContent = summary.confirmation_frames != null ? `${summary.confirmation_frames} frames` : "N/A";

        byId("total-frames").textContent = meta.total_frames ?? state.feed.frames.length;
        byId("total-detections").textContent = meta.total_detections ?? "N/A";
        byId("processing-fps").textContent = meta.processing_fps != null ? `${meta.processing_fps.toFixed(1)} FPS` : "N/A";
        const aliases = Object.entries(summary.identity_aliases || {});
        byId("alias-result").textContent = aliases.length ? aliases.map(([a, b]) => `${a} -> ${b}`).join(", ") : "No alias";

        byId("radar-status").textContent = caps.radar ? "Radar data" : "NO RADAR DATA";
        byId("rf-status").textContent = caps.rf ? "RF sensor data" : "NO RF SENSOR DATA";
        byId("acoustic-status").textContent = caps.acoustic ? "Acoustic sensor data" : "NO ACOUSTIC SENSOR DATA";
    }

    function stepReplay() {
        if (!state.playing || !state.feed?.frames.length) return;
        state.index = (state.index + 1) % state.feed.frames.length;
        byId("frame-slider").value = state.index;
        render();
    }

    function render() {
        const frame = state.feed.frames[state.index];
        renderCanvas(frame);
        renderSelectedTrack(frame);
        renderTable(frame);
        renderTimeline(frame.frame_id);
        byId("frame-counter").textContent = `FRAME ${frame.frame_id} / ${state.feed.frames.length}`;
        byId("fps-counter").textContent = `${fmtNum(state.feed.metadata?.processing_fps)} FPS`;
        byId("inference-value").textContent = `Inference ${fmtNum(frame.inference_speed_ms)} ms`;
        byId("sapient-json-display").textContent = JSON.stringify(frame.sapient_asm_eoir || frame.sapient_hlm || {}, null, 2);
    }

    function renderCanvas(frame) {
        const w = canvas.width, h = canvas.height;
        ctx.clearRect(0, 0, w, h);
        const gradient = ctx.createLinearGradient(0, 0, 0, h);
        gradient.addColorStop(0, "#091b2d"); gradient.addColorStop(1, "#020812");
        ctx.fillStyle = gradient; ctx.fillRect(0, 0, w, h);
        ctx.strokeStyle = "rgba(80,150,200,.13)"; ctx.lineWidth = 1;
        for (let x = 0; x <= w; x += 80) { ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, h); ctx.stroke(); }
        for (let y = 0; y <= h; y += 60) { ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke(); }
        ctx.fillStyle = "#7891aa"; ctx.font = "12px Segoe UI";
        ctx.fillText("IMAGE-PLANE GEOMETRY · PIXELS ONLY · NO RANGE / ALTITUDE CLAIM", 18, 25);

        const tracks = frame.bytetrack_tracks || [];
        tracks.forEach(track => {
            const box = track.obb || {};
            const sx = w / 1920, sy = h / 1080;
            const x = (box.x_center - box.width / 2) * sx;
            const y = (box.y_center - box.height / 2) * sy;
            const bw = box.width * sx, bh = box.height * sy;
            const provisional = track.identity_status === "provisional";
            const color = provisional ? "#ffad4d" : "#35d4f4";

            if ((track.trajectory || []).length > 1) {
                ctx.beginPath(); ctx.strokeStyle = "rgba(82,212,156,.72)"; ctx.lineWidth = 2;
                track.trajectory.forEach((point, index) => {
                    const px = point.x * sx, py = point.y * sy;
                    if (index === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
                });
                ctx.stroke();
            }
            ctx.strokeStyle = color; ctx.lineWidth = 3; ctx.strokeRect(x, y, bw, bh);
            ctx.fillStyle = color; ctx.fillRect(x, Math.max(0, y - 25), Math.max(172, bw), 24);
            ctx.fillStyle = "#041019"; ctx.font = "bold 13px Segoe UI";
            const label = `${track.display_id_at_frame || track.display_id || `TRK-${track.track_id}`} · INT-${track.internal_track_id ?? track.track_id} · ${fmtPct(box.confidence)}`;
            ctx.fillText(label, x + 6, Math.max(16, y - 8));

            const kalman = frame.kalman_filter_states?.[String(track.internal_track_id ?? track.track_id)];
            if (kalman) {
                ctx.beginPath(); ctx.fillStyle = "#52d49c"; ctx.arc(kalman.x * sx, kalman.y * sy, 5, 0, Math.PI * 2); ctx.fill();
                ctx.strokeStyle = "#52d49c"; ctx.beginPath(); ctx.moveTo(kalman.x * sx, kalman.y * sy); ctx.lineTo((kalman.x + kalman.vx * 2) * sx, (kalman.y + kalman.vy * 2) * sy); ctx.stroke();
            }
        });
        if (!tracks.length) {
            ctx.fillStyle = "#8ea6bf"; ctx.font = "bold 24px Segoe UI"; ctx.textAlign = "center";
            ctx.fillText("NO ACTIVE DETECTION IN THIS FRAME", w / 2, h / 2); ctx.textAlign = "left";
        }
    }

    function renderSelectedTrack(frame) {
        const track = (frame.bytetrack_tracks || [])[0];
        if (!track) {
            byId("selected-display-id").textContent = "NO ACTIVE IDENTITY";
            byId("selected-status").textContent = "IDLE";
            byId("selected-status").className = "state-pill";
            ["selected-internal-id", "selected-confidence", "selected-identity-confidence", "selected-final-id", "selected-velocity", "selected-uncertainty"].forEach(id => byId(id).textContent = "N/A");
            byId("evidence-label").textContent = "No provisional comparison active";
            byId("evidence-fill").style.width = "0%";
            return;
        }
        const display = track.display_id_at_frame || track.display_id || `TRK-${track.track_id}`;
        const status = track.identity_status || "unresolved";
        const internal = track.internal_track_id ?? track.track_id;
        const kalman = frame.kalman_filter_states?.[String(internal)] || {};
        byId("selected-display-id").textContent = display;
        byId("selected-status").textContent = status.toUpperCase();
        byId("selected-status").className = `state-pill ${status}`;
        byId("selected-internal-id").textContent = `INT-${internal}`;
        byId("selected-confidence").textContent = fmtPct(track.obb?.confidence ?? track.score);
        byId("selected-identity-confidence").textContent = fmtPct(track.identity_confidence);
        byId("selected-final-id").textContent = track.final_display_id || display;
        byId("selected-velocity").textContent = kalman.vx == null ? `${fmtNum(track.speed_px_per_frame)} px/frame` : `${fmtNum(kalman.vx)} / ${fmtNum(kalman.vy)} px/frame`;
        byId("selected-uncertainty").textContent = kalman.position_uncertainty_px == null ? "N/A" : `${fmtNum(kalman.position_uncertainty_px)} px`;
        if (status === "provisional") {
            const confidence = Math.max(0, Math.min(1, Number(track.identity_confidence || 0)));
            byId("evidence-label").textContent = `Comparing with candidate ${track.candidate_identity_id ? `ID-${track.candidate_identity_id}` : "identity"} · cost ${fmtNum(track.candidate_cost, 4)}`;
            byId("evidence-fill").style.width = `${confidence * 100}%`;
        } else {
            byId("evidence-label").textContent = status === "confirmed" ? "Permanent operator identity confirmed" : "No provisional comparison active";
            byId("evidence-fill").style.width = status === "confirmed" ? "100%" : "0%";
        }
    }

    function renderTable(frame) {
        const tracks = frame.bytetrack_tracks || [];
        byId("track-table-note").textContent = tracks.length ? `${tracks.length} active track${tracks.length === 1 ? "" : "s"}` : "No active tracks";
        byId("identity-table-body").innerHTML = tracks.length ? tracks.map(track => {
            const status = track.identity_status || "unresolved";
            const display = track.display_id_at_frame || track.display_id || `TRK-${track.track_id}`;
            return `<tr><td><strong>${escapeHtml(display)}</strong></td><td>INT-${escapeHtml(track.internal_track_id ?? track.track_id)}</td><td><span class="status-text ${escapeHtml(status)}">${escapeHtml(status.toUpperCase())}</span></td><td>${fmtPct(track.obb?.confidence ?? track.score)}</td><td>${fmtPct(track.identity_confidence)}</td><td>${fmtNum(track.speed_px_per_frame)} px/frame</td><td>${escapeHtml(track.final_display_id || display)}</td></tr>`;
        }).join("") : '<tr><td colspan="7" class="muted">No active identity in this frame.</td></tr>';
    }

    function renderTimeline(frameId) {
        const visible = state.events.filter(event => Number(event.frame_id) <= Number(frameId)).slice(-8).reverse();
        byId("event-timeline").innerHTML = visible.length ? visible.map(event => {
            const title = String(event.event || "identity_event").replaceAll("_", " ").toUpperCase();
            const detail = event.provisional_id && event.identity_id ? `${event.provisional_id} -> ID-${event.identity_id}` : event.provisional_id || (event.identity_id ? `ID-${event.identity_id}` : "Resolver state changed");
            return `<article class="event ${escapeHtml(event.event)}"><time>FRAME ${escapeHtml(event.frame_id)}</time><div><strong>${escapeHtml(title)}</strong><small>${escapeHtml(detail)}</small></div></article>`;
        }).join("") : '<p class="empty">No identity events have occurred yet.</p>';
    }

    byId("play-button").addEventListener("click", () => {
        state.playing = !state.playing;
        byId("play-button").textContent = state.playing ? "Pause replay" : "Resume replay";
        byId("run-state").textContent = state.playing ? "RESULT REPLAY" : "PAUSED";
    });
    byId("frame-slider").addEventListener("input", event => {
        state.index = Number(event.target.value); state.playing = false;
        byId("play-button").textContent = "Resume replay"; byId("run-state").textContent = "PAUSED"; render();
    });
    setInterval(() => { byId("utc-clock").textContent = `${new Date().toISOString().slice(11, 19)} UTC`; }, 1000);
    loadFeed();
});
