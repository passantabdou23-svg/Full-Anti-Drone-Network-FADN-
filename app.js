/**
 * NATO SAPIENT Counter-UAS Military Command Center Application Logic.
 * Controls Radar PPI scope, Dual EO/IR YOLOv8-OBB Canvas, ByteTrack tracks,
 * Sensor Fusion Engine, Effector Engagement, and SAPIENT Protocol Inspector.
 */

document.addEventListener("DOMContentLoaded", () => {
    // -------------------------------------------------------------------------
    // STATE & VARIABLES
    // -------------------------------------------------------------------------
    let simulationData = null;
    let currentFrameIdx = 0;
    let isNightIRMode = false;
    let fusionMode = "FUSED"; // "EO", "RADAR", "FUSED"
    
    // Canvas Elements
    const cameraCanvas = document.getElementById("camera-canvas");
    const cameraCtx = cameraCanvas.getContext("2d");
    
    const radarCanvas = document.getElementById("radar-canvas");
    const radarCtx = radarCanvas.getContext("2d");
    
    const fusionCanvas = document.getElementById("fusion-map-canvas");
    const fusionCtx = fusionCanvas.getContext("2d");
    
    const rfCanvas = document.getElementById("rf-canvas");
    const rfCtx = rfCanvas.getContext("2d");
    
    const acousticCanvas = document.getElementById("acoustic-canvas");
    const acousticCtx = acousticCanvas.getContext("2d");
    
    // Radar Sweep Angle
    let radarSweepAngle = 0;
    
    // Effector Beam Simulation
    let activeLaserTarget = null;
    let activeJammerPulse = 0;

    // -------------------------------------------------------------------------
    // INITIALIZATION & FETCH DATA
    // -------------------------------------------------------------------------
    async function initSystem() {
        startClock();
        setupEventListeners();
        
        try {
            const response = await fetch('simulation_feed.json');
            simulationData = await response.json();
            console.log("Loaded simulation feed:", simulationData);
        } catch (e) {
            console.warn("Using inline fallback simulation dataset:", e);
            simulationData = generateFallbackDataset();
        }

        // Start render loops
        requestAnimationFrame(renderLoop);
        setInterval(advanceFrame, 1200); // 1.2s per frame step
        setInterval(renderAuxWaveforms, 50); // 20 FPS waveform animation
    }

    // -------------------------------------------------------------------------
    // CLOCK & EVENT LISTENERS
    // -------------------------------------------------------------------------
    function startClock() {
        setInterval(() => {
            const now = new Date();
            document.getElementById("utc-clock").textContent = 
                now.toISOString().substring(11, 19) + " UTC";
        }, 1000);
    }

    function setupEventListeners() {
        // EO/IR Toggle
        document.getElementById("btn-mode-rgb").addEventListener("click", (e) => {
            isNightIRMode = false;
            document.getElementById("btn-mode-rgb").classList.add("active");
            document.getElementById("btn-mode-ir").classList.remove("active");
            document.getElementById("camera-feed-label").textContent = "EO CAMERA 01 (RGB DAY) • 1080p60";
        });
        
        document.getElementById("btn-mode-ir").addEventListener("click", (e) => {
            isNightIRMode = true;
            document.getElementById("btn-mode-ir").classList.add("active");
            document.getElementById("btn-mode-rgb").classList.remove("active");
            document.getElementById("camera-feed-label").textContent = "IR CAMERA 01 (FLIR THERMAL) • 60 FPS";
        });

        // Fusion Mode Switch
        document.getElementById("btn-eo-only").addEventListener("click", () => setFusionMode("EO"));
        document.getElementById("btn-radar-only").addEventListener("click", () => setFusionMode("RADAR"));
        document.getElementById("btn-fused-mode").addEventListener("click", () => setFusionMode("FUSED"));

        // Effectors
        document.getElementById("btn-effect-ew").addEventListener("click", triggerEWJammer);
        document.getElementById("btn-effect-laser").addEventListener("click", triggerLaserNeutralize);
        document.getElementById("btn-effect-kinetic").addEventListener("click", triggerKineticInterceptor);

        // Tabs
        document.getElementById("tab-benchmarks").addEventListener("click", () => {
            document.getElementById("tab-benchmarks").classList.add("active");
            document.getElementById("tab-sapient-xml").classList.remove("active");
            document.getElementById("content-benchmarks").classList.add("active");
            document.getElementById("content-sapient-xml").classList.remove("active");
        });
        
        document.getElementById("tab-sapient-xml").addEventListener("click", () => {
            document.getElementById("tab-sapient-xml").classList.add("active");
            document.getElementById("tab-benchmarks").classList.remove("active");
            document.getElementById("content-sapient-xml").classList.add("active");
            document.getElementById("content-benchmarks").classList.remove("active");
        });
    }

    function setFusionMode(mode) {
        fusionMode = mode;
        document.querySelectorAll(".btn-fusion").forEach(btn => btn.classList.remove("active"));
        if (mode === "EO") document.getElementById("btn-eo-only").classList.add("active");
        if (mode === "RADAR") document.getElementById("btn-radar-only").classList.add("active");
        if (mode === "FUSED") document.getElementById("btn-fused-mode").classList.add("active");

        const farElem = document.getElementById("far-rate");
        if (mode === "EO") farElem.textContent = "14.2% (HIGH UNFILTERED FAR)";
        if (mode === "RADAR") farElem.textContent = "8.6% (CLUTTER NOISE)";
        if (mode === "FUSED") farElem.textContent = "1.8% (SAPIENT EKF FILTERED)";
        
        logMessage(`Fusion mode switched to: ${mode}`, "sys");
    }

    function advanceFrame() {
        if (!simulationData || !simulationData.frames) return;
        currentFrameIdx = (currentFrameIdx + 1) % simulationData.frames.length;
        updateUIForFrame(simulationData.frames[currentFrameIdx]);
    }

    // -------------------------------------------------------------------------
    // RENDER LOOP (CANVAS ANIMATIONS)
    // -------------------------------------------------------------------------
    function renderLoop() {
        radarSweepAngle = (radarSweepAngle + 0.03) % (Math.PI * 2);
        
        const frameData = (simulationData && simulationData.frames) ? 
            simulationData.frames[currentFrameIdx] : null;

        drawEOIRCamera(frameData);
        drawRadarScope(frameData);
        drawFusionMap(frameData);

        requestAnimationFrame(renderLoop);
    }

    // -------------------------------------------------------------------------
    // CANVAS 1: DUAL EO/IR CAMERA FEED (YOLOv8-OBB & BYTE TRACK)
    // -------------------------------------------------------------------------
    function drawEOIRCamera(frameData) {
        const w = cameraCanvas.width;
        const h = cameraCanvas.height;

        // Clear Background
        if (isNightIRMode) {
            // FLIR Thermal IR Palette (Dark blue/black background with bright thermal targets)
            const grad = cameraCtx.createLinearGradient(0, 0, 0, h);
            grad.addColorStop(0, '#02050e');
            grad.addColorStop(1, '#081226');
            cameraCtx.fillStyle = grad;
            cameraCtx.fillRect(0, 0, w, h);
            
            // Thermal Noise Grain
            cameraCtx.fillStyle = "rgba(0, 243, 255, 0.03)";
            for (let i = 0; i < 40; i++) {
                cameraCtx.fillRect(Math.random()*w, Math.random()*h, 2, 2);
            }
        } else {
            // Day RGB Mode (Sky, horizon, cloud layers)
            const grad = cameraCtx.createLinearGradient(0, 0, 0, h);
            grad.addColorStop(0, '#1a2942');
            grad.addColorStop(0.7, '#2c3e55');
            grad.addColorStop(1, '#111923');
            cameraCtx.fillStyle = grad;
            cameraCtx.fillRect(0, 0, w, h);
            
            // Horizon Line
            cameraCtx.strokeStyle = "rgba(255, 255, 255, 0.15)";
            cameraCtx.lineWidth = 1;
            cameraCtx.beginPath();
            cameraCtx.moveTo(0, h * 0.75);
            cameraCtx.lineTo(w, h * 0.75);
            cameraCtx.stroke();
        }

        // Draw HUD Crosshair
        cameraCtx.strokeStyle = "rgba(0, 243, 255, 0.3)";
        cameraCtx.lineWidth = 1;
        cameraCtx.beginPath();
        cameraCtx.moveTo(w/2 - 20, h/2); cameraCtx.lineTo(w/2 + 20, h/2);
        cameraCtx.moveTo(w/2, h/2 - 20); cameraCtx.lineTo(w/2, h/2 + 20);
        cameraCtx.stroke();

        if (!frameData || !frameData.eoir_detections) return;

        // Draw Oriented Bounding Boxes (YOLOv8-OBB) & ByteTrack Tracks
        frameData.bytetrack_tracks.forEach((track, idx) => {
            const obb = track.obb;
            const cx = obb.x_center;
            const cy = obb.y_center;
            const bw = obb.width;
            const bh = obb.height;
            const angleRad = (obb.angle_deg * Math.PI) / 180;

            // Draw Trajectory History
            if (track.trajectory && track.trajectory.length > 1) {
                cameraCtx.strokeStyle = isNightIRMode ? "rgba(255, 255, 255, 0.6)" : "rgba(0, 243, 255, 0.6)";
                cameraCtx.lineWidth = 2;
                cameraCtx.setLineDash([4, 4]);
                cameraCtx.beginPath();
                track.trajectory.forEach((pt, i) => {
                    if (i === 0) cameraCtx.moveTo(pt.x, pt.y);
                    else cameraCtx.lineTo(pt.x, pt.y);
                });
                cameraCtx.stroke();
                cameraCtx.setLineDash([]);
            }

            // Draw Drone Thermal Hotspot in IR Mode
            if (isNightIRMode) {
                const glowGrad = cameraCtx.createRadialGradient(cx, cy, 2, cx, cy, bw);
                glowGrad.addColorStop(0, '#ffffff');
                glowGrad.addColorStop(0.4, '#ffaa00');
                glowGrad.addColorStop(1, 'transparent');
                cameraCtx.fillStyle = glowGrad;
                cameraCtx.beginPath();
                cameraCtx.arc(cx, cy, bw * 0.8, 0, Math.PI * 2);
                cameraCtx.fill();
            }

            // ROTATED ORIENTED BOUNDING BOX (OBB)
            cameraCtx.save();
            cameraCtx.translate(cx, cy);
            cameraCtx.rotate(angleRad);

            // Box Stroke
            cameraCtx.strokeStyle = isNightIRMode ? '#ffaa00' : '#00f3ff';
            cameraCtx.lineWidth = 2;
            cameraCtx.strokeRect(-bw/2, -bh/2, bw, bh);
            
            // Box Corner Accents
            cameraCtx.fillStyle = isNightIRMode ? '#ffffff' : '#00ff88';
            cameraCtx.fillRect(-bw/2 - 2, -bh/2 - 2, 5, 5);
            cameraCtx.fillRect(bw/2 - 3, -bh/2 - 2, 5, 5);
            cameraCtx.fillRect(bw/2 - 3, bh/2 - 3, 5, 5);
            cameraCtx.fillRect(-bw/2 - 2, bh/2 - 3, 5, 5);

            cameraCtx.restore();

            // OBB Label Tag (ByteTrack ID + YOLO Class + Conf + Angle)
            cameraCtx.fillStyle = "rgba(0, 0, 0, 0.75)";
            cameraCtx.fillRect(cx - bw/2, cy - bh/2 - 22, 160, 18);
            cameraCtx.strokeStyle = isNightIRMode ? '#ffaa00' : '#00f3ff';
            cameraCtx.strokeRect(cx - bw/2, cy - bh/2 - 22, 160, 18);

            cameraCtx.font = "bold 10px Orbitron, monospace";
            cameraCtx.fillStyle = isNightIRMode ? '#ffaa00' : '#00ff88';
            cameraCtx.fillText(
                `#TRK-${track.track_id} ${obb.class_name.toUpperCase()} ${(obb.confidence*100).toFixed(0)}% [${obb.angle_deg.toFixed(0)}°]`,
                cx - bw/2 + 4, cy - bh/2 - 9
            );
        });

        // Draw Active Directed Energy Laser Effect if Triggered
        if (activeLaserTarget) {
            cameraCtx.strokeStyle = '#ff3355';
            cameraCtx.lineWidth = 4;
            cameraCtx.shadowColor = '#ff3355';
            cameraCtx.shadowBlur = 15;
            cameraCtx.beginPath();
            cameraCtx.moveTo(w/2, h);
            cameraCtx.lineTo(activeLaserTarget.x, activeLaserTarget.y);
            cameraCtx.stroke();
            cameraCtx.shadowBlur = 0;
        }

        // Draw EW Jamming Pulse Effect
        if (activeJammerPulse > 0) {
            cameraCtx.strokeStyle = `rgba(255, 170, 0, ${activeJammerPulse})`;
            cameraCtx.lineWidth = 3;
            cameraCtx.beginPath();
            cameraCtx.arc(w/2, h/2, (1.0 - activeJammerPulse) * w * 0.8, 0, Math.PI * 2);
            cameraCtx.stroke();
            activeJammerPulse -= 0.05;
        }
    }

    // -------------------------------------------------------------------------
    // CANVAS 2: 3D PULSE-DOPPLER RADAR PPI SCOPE
    // -------------------------------------------------------------------------
    function drawRadarScope(frameData) {
        const w = radarCanvas.width;
        const h = radarCanvas.height;
        const cx = w / 2;
        const cy = h / 2;
        const radius = w / 2 - 12;

        // Dark Background
        radarCtx.fillStyle = '#020a05';
        radarCtx.fillRect(0, 0, w, h);

        // Range Rings (10km, 5km, 2.5km)
        radarCtx.strokeStyle = 'rgba(0, 255, 136, 0.25)';
        radarCtx.lineWidth = 1;
        
        [0.33, 0.66, 1.0].forEach(factor => {
            radarCtx.beginPath();
            radarCtx.arc(cx, cy, radius * factor, 0, Math.PI * 2);
            radarCtx.stroke();
        });

        // Angular Grid Lines
        for (let a = 0; a < 360; a += 45) {
            const rad = (a * Math.PI) / 180;
            radarCtx.beginPath();
            radarCtx.moveTo(cx, cy);
            radarCtx.lineTo(cx + Math.sin(rad) * radius, cy - Math.cos(rad) * radius);
            radarCtx.stroke();
        }

        // Rotating Sweep Beam
        radarCtx.save();
        radarCtx.translate(cx, cy);
        radarCtx.rotate(radarSweepAngle);
        
        const sweepGrad = radarCtx.createConicGradient(0, 0, 0);
        sweepGrad.addColorStop(0, 'rgba(0, 255, 136, 0.4)');
        sweepGrad.addColorStop(0.15, 'rgba(0, 255, 136, 0.05)');
        sweepGrad.addColorStop(1, 'transparent');
        
        radarCtx.fillStyle = sweepGrad;
        radarCtx.beginPath();
        radarCtx.arc(0, 0, radius, -0.4, 0);
        radarCtx.lineTo(0, 0);
        radarCtx.fill();
        radarCtx.restore();

        // Draw Radar Blips & Targets
        if (frameData && frameData.radar_detections) {
            frameData.radar_detections.forEach(r => {
                const azRad = (r.azimuth_deg * Math.PI) / 180;
                const distFactor = r.range_m / 2500.0;
                const bx = cx + Math.sin(azRad) * (radius * distFactor);
                const by = cy - Math.cos(azRad) * (radius * distFactor);

                // Blip Glow
                radarCtx.fillStyle = '#00ff88';
                radarCtx.shadowColor = '#00ff88';
                radarCtx.shadowBlur = 10;
                radarCtx.beginPath();
                radarCtx.arc(bx, by, 5, 0, Math.PI * 2);
                radarCtx.fill();
                radarCtx.shadowBlur = 0;

                // Radar Tag (RCS + Velocity)
                radarCtx.font = "9px Orbitron, monospace";
                radarCtx.fillStyle = '#00ff88';
                radarCtx.fillText(`${r.radar_id} [RCS:${r.rcs_sqm}m²]`, bx + 8, by + 3);
            });
        }

        // Outer Border Ring
        radarCtx.strokeStyle = '#00ff88';
        radarCtx.lineWidth = 2;
        radarCtx.beginPath();
        radarCtx.arc(cx, cy, radius, 0, Math.PI * 2);
        radarCtx.stroke();
    }

    // -------------------------------------------------------------------------
    // CANVAS 3: UNIFIED SENSOR FUSION TACTICAL MAP
    // -------------------------------------------------------------------------
    function drawFusionMap(frameData) {
        const w = fusionCanvas.width;
        const h = fusionCanvas.height;

        fusionCtx.fillStyle = '#030712';
        fusionCtx.fillRect(0, 0, w, h);

        // Tactical Grid Lines
        fusionCtx.strokeStyle = 'rgba(0, 243, 255, 0.1)';
        fusionCtx.lineWidth = 1;
        for (let x = 0; x < w; x += 40) {
            fusionCtx.beginPath(); fusionCtx.moveTo(x, 0); fusionCtx.lineTo(x, h); fusionCtx.stroke();
        }
        for (let y = 0; y < h; y += 40) {
            fusionCtx.beginPath(); fusionCtx.moveTo(0, y); fusionCtx.lineTo(w, y); fusionCtx.stroke();
        }

        if (!frameData || !frameData.fused_threat_picture) return;

        // Render Fused Unified Threat Picture Tracks
        frameData.fused_threat_picture.forEach((utp, idx) => {
            const tx = 100 + idx * 240 + Math.sin(currentFrameIdx * 0.3) * 20;
            const ty = 80 + Math.cos(currentFrameIdx * 0.2) * 15;

            // Draw Correlated Sensor Rays
            if (fusionMode === "FUSED" || fusionMode === "EO") {
                fusionCtx.strokeStyle = 'rgba(0, 243, 255, 0.5)';
                fusionCtx.beginPath();
                fusionCtx.moveTo(40, h - 20); // EO Camera Origin
                fusionCtx.lineTo(tx, ty);
                fusionCtx.stroke();
            }

            if (fusionMode === "FUSED" || fusionMode === "RADAR") {
                fusionCtx.strokeStyle = 'rgba(0, 255, 136, 0.5)';
                fusionCtx.beginPath();
                fusionCtx.moveTo(w - 40, h - 20); // Radar Origin
                fusionCtx.lineTo(tx, ty);
                fusionCtx.stroke();
            }

            // Target Node Diamond Icon
            fusionCtx.fillStyle = '#ff3355';
            fusionCtx.beginPath();
            fusionCtx.moveTo(tx, ty - 10);
            fusionCtx.lineTo(tx + 10, ty);
            fusionCtx.lineTo(tx, ty + 10);
            fusionCtx.lineTo(tx - 10, ty);
            fusionCtx.closePath();
            fusionCtx.fill();

            // UTP Label
            fusionCtx.font = "bold 10px Orbitron, monospace";
            fusionCtx.fillStyle = '#ffffff';
            fusionCtx.fillText(`${utp.fused_id}: ${utp.classification}`, tx - 40, ty - 14);
            
            fusionCtx.font = "9px Orbitron, monospace";
            fusionCtx.fillStyle = 'var(--primary-cyan)';
            fusionCtx.fillText(`CONF: ${(utp.confidence_score*100).toFixed(1)}% | SENSORS: [${utp.sensor_sources.join('+')}]`, tx - 40, ty + 24);
        });
    }

    // -------------------------------------------------------------------------
    // AUX SENSOR WAVEFORM ANIMATIONS
    // -------------------------------------------------------------------------
    function renderAuxWaveforms() {
        // RF Waveform
        const rfw = rfCanvas.width;
        const rfh = rfCanvas.height;
        rfCtx.fillStyle = '#02060d';
        rfCtx.fillRect(0, 0, rfw, rfh);
        
        rfCtx.strokeStyle = '#ffaa00';
        rfCtx.lineWidth = 1.5;
        rfCtx.beginPath();
        for (let x = 0; x < rfw; x += 3) {
            const y = rfh/2 + Math.sin(x * 0.1 + Date.now() * 0.01) * 12 * Math.random();
            if (x === 0) rfCtx.moveTo(x, y); else rfCtx.lineTo(x, y);
        }
        rfCtx.stroke();

        // Acoustic Waveform
        const aw = acousticCanvas.width;
        const ah = acousticCanvas.height;
        acousticCtx.fillStyle = '#02060d';
        acousticCtx.fillRect(0, 0, aw, ah);
        
        acousticCtx.strokeStyle = '#00ff88';
        acousticCtx.lineWidth = 1.5;
        acousticCtx.beginPath();
        for (let x = 0; x < aw; x += 3) {
            const y = ah/2 + Math.cos(x * 0.15 + Date.now() * 0.012) * 10;
            if (x === 0) acousticCtx.moveTo(x, y); else acousticCtx.lineTo(x, y);
        }
        acousticCtx.stroke();
    }

    // -------------------------------------------------------------------------
    // UPDATE DYNAMIC UI PANELS & TABLES
    // -------------------------------------------------------------------------
    function updateUIForFrame(frameData) {
        if (!frameData) return;

        // FPS / Speed Tag
        document.getElementById("fps-counter").textContent = `60 FPS | ${frameData.inference_speed_ms} ms`;

        // Update Matrix Table
        const tbody = document.getElementById("fusion-table-body");
        tbody.innerHTML = "";

        if (frameData.fused_threat_picture) {
            frameData.fused_threat_picture.forEach(utp => {
                const rangeDisplay = (utp.pos_3d && utp.pos_3d.y_m != null) ? `${utp.pos_3d.y_m} m` : "N/A (no georeferencing)";
                const tr = document.createElement("tr");
                tr.innerHTML = `
                    <td style="color:var(--primary-cyan); font-weight:700;">${utp.fused_id}</td>
                    <td>${utp.sensor_sources.join(" + ")}</td>
                    <td>${rangeDisplay}</td>
                    <td>${utp.speed_px_per_frame != null ? utp.speed_px_per_frame + " px/frame" : "N/A"}</td>
                    <td>${utp.radar_rcs != null ? utp.radar_rcs + " m\u00b2" : "N/A (no radar)"}</td>
                    <td style="color:var(--radar-green); font-weight:700;">${(utp.confidence_score*100).toFixed(1)}%</td>
                    <td><span class="badge-pct high">${utp.sensor_sources.length > 1 ? "CORRELATED" : "SINGLE-SENSOR"}</span></td>
                `;
                tbody.appendChild(tr);
            });
            
            document.getElementById("fused-count").textContent = `${frameData.fused_threat_picture.length} ACTIVE`;

            // Active Threat Card
            if (frameData.fused_threat_picture.length > 0) {
                const topUtp = frameData.fused_threat_picture[0];
                const topRangeDisplay = (topUtp.pos_3d && topUtp.pos_3d.y_m != null) ? `${topUtp.pos_3d.y_m} m` : "N/A";
                document.getElementById("threat-title").textContent = topUtp.classification;
                document.getElementById("threat-track-id").textContent = topUtp.fused_id;
                document.getElementById("threat-range").textContent = topRangeDisplay;
                document.getElementById("threat-conf").textContent = `${(topUtp.confidence_score*100).toFixed(1)}%`;
                document.getElementById("threat-bytetrack").textContent = `#TRK-${topUtp.eo_track_id || "01"}`;
            }
        }

        // Update SAPIENT (STANREC 4869 / BSI Flex 335) JSON Viewer
        if (frameData.sapient_hlm) {
            document.getElementById("sapient-json-display").textContent = 
                JSON.stringify(frameData.sapient_hlm, null, 2);
        }
    }

    // -------------------------------------------------------------------------
    // EFFECTOR ACTIONS (EW JAMMER, LASER, KINETIC)
    // -------------------------------------------------------------------------
    function triggerEWJammer() {
        activeJammerPulse = 1.0;
        logMessage("[EFFECTOR TASKED] Electronic Warfare (RF Soft-Kill Jamming 2.4/5.8GHz) Initiated. Control telemetry severed.", "warn");
    }

    function triggerLaserNeutralize() {
        activeLaserTarget = { x: 320, y: 140 };
        logMessage("[EFFECTOR TASKED] High-Energy Laser (HEL) Fired. Thermal target destruction confirmed.", "critical");
        setTimeout(() => { activeLaserTarget = null; }, 2500);
    }

    function triggerKineticInterceptor() {
        logMessage("[EFFECTOR TASKED] Counter-UAS Kinetic Interceptor Missile Launched. Vector locked to target UTP-TRK-101.", "critical");
    }

    function logMessage(msg, type = "sys") {
        const box = document.getElementById("engagement-log-box");
        const entry = document.createElement("div");
        entry.className = `log-entry ${type}`;
        const timeStr = new Date().toISOString().substring(11, 19);
        entry.textContent = `[${timeStr}] ${msg}`;
        box.appendChild(entry);
        box.scrollTop = box.scrollHeight;
    }

    function generateFallbackDataset() {
        return {
            frames: [
                {
                    frame_id: 1,
                    inference_speed_ms: 13.2,
                    bytetrack_tracks: [{ track_id: 1, obb: { x_center: 240, y_center: 140, width: 44, height: 28, angle_deg: 14, confidence: 0.94, class_name: "drone" }, trajectory: [{x:240,y:140}] }],
                    radar_detections: [{ radar_id: "RAD-101", azimuth_deg: 45, range_m: 1420, rcs_sqm: 0.018 }],
                    fused_threat_picture: [{ fused_id: "UTP-TRK-101", classification: "MILITARY MICRO-DRONE (QUADROTOR)", confidence_score: 0.948, sensor_sources: ["EO/IR", "RADAR", "RF"], pos_3d: { y_m: 1420 }, eo_track_id: 1 }]
                }
            ]
        };
    }

    // Launch
    initSystem();
});
