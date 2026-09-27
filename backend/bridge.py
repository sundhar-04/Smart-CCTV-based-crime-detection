import sys
import os
import json
import hashlib
import time
import numpy as np
import cv2

# Add smartcctv package parent directory to sys.path
W_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "smartcctv", "w"))
if W_DIR not in sys.path:
    sys.path.insert(0, W_DIR)

try:
    from smartcctv.detector_yolo8 import YoloDetector
    from smartcctv.detector import Detector, MotionGate
    from smartcctv.risk import RiskEngine
    from smartcctv.evidence import Evidence, Chain, create_video_writer
    from smartcctv.tamper import TamperMonitor
    from smartcctv.run import SimpleIOUTracker, get_detector, HAVE_SUPERVISION
    SMARTCCTV_AVAILABLE = True
except Exception as e:
    print(f"[BRIDGE WARN] Could not import smartcctv modules directly: {e}")
    SMARTCCTV_AVAILABLE = False

if HAVE_SUPERVISION:
    import supervision as sv

def run_video_analysis(video_path: str, output_dir: str, zones_config: dict = None, progress_callback=None):
    """
    Executes the exact YOLOv8 + RiskEngine + EvidenceChain pipeline on an uploaded video.
    Returns summary result dictionary with real peak_risk_score, no_alert_reason, and alerts list.
    """
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video file not found: {video_path}")

    os.makedirs(output_dir, exist_ok=True)
    
    # Load base config
    config_path = os.path.join(W_DIR, "smartcctv", "config.json")
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    else:
        cfg = {"source": video_path, "camera_id": "ANALYSIS_CAM", "thr": 35}

    if zones_config:
        cfg["zones"] = zones_config

    cap = cv2.VideoCapture(video_path)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0

    det, det_name = get_detector(cfg, "yolov8")
    gate = MotionGate(regions=list(cfg.get("zones", {}).values()))
    tam = TamperMonitor()

    if HAVE_SUPERVISION:
        trk = sv.ByteTrack(track_activation_threshold=0.25, lost_track_buffer=int(fps * 3),
                           minimum_matching_threshold=0.8, frame_rate=int(fps), minimum_consecutive_frames=2)
    else:
        trk = SimpleIOUTracker(fps=fps)

    meta = {"detector": det_name, "camera": cfg.get("camera_id", "ANALYSIS_CAM")}
    weights_path = os.path.join(output_dir, "weights.json")
    eng = RiskEngine(cfg, fps, weights_path=weights_path)
    ev = Evidence(output_dir, fps, meta=meta)

    names = det.names
    frame_idx = 0
    skipped = 0
    peak_risk_score = 0.0
    generated_alerts = []

    vw = None
    annotated_video_path = os.path.join(output_dir, "annotated_analysis.mp4")

    while True:
        ok, frame = cap.read()
        if not ok:
            break
        
        t = frame_idx / fps
        frame_idx += 1
        ev.push(t, frame)

        for al in tam.update(t, frame):
            ev.start(al)

        run_det = gate(frame) and (frame_idx % max(1, int(fps / 10)) == 0)
        if run_det:
            d = det(frame)
            xyxy = np.array([x[:4] for x in d], float).reshape(-1, 4) if d else np.empty((0, 4), float)
            confs = np.array([x[4] for x in d], float) if d else np.empty((0,), float)
            cids = np.array([names.index(x[5]) for x in d], int) if d else np.empty((0,), int)

            if HAVE_SUPERVISION:
                dets = sv.Detections(xyxy=xyxy, confidence=confs, class_id=cids)
            else:
                dets = [(x[:4], names.index(x[5]), x[4]) for x in d]
        else:
            if HAVE_SUPERVISION:
                dets = sv.Detections.empty()
            else:
                dets = []
            if not gate(frame):
                skipped += 1

        tr = trk.update_with_detections(dets)
        last = [dict(id=int(tid), cls=names[int(c)], box=tuple(map(float, b)))
                for b, tid, c in zip(tr.xyxy, tr.tracker_id, tr.class_id)]

        for x in last:
            if x["cls"] == "person" and frame_idx % 3 == 0:
                ev.best_shot(f"{eng.cam}:P{x['id']}", frame, x["box"])

        current_alerts = eng.update(t, last)
        for al in current_alerts:
            if al["status"] != "SUPPRESSED_BY_BUDGET":
                ev.start(al)
                generated_alerts.append(al)

        # Track peak score across all tracked entities
        for k in list(eng.events.keys()):
            sc, _ = eng.score(k, t)
            if sc > peak_risk_score:
                peak_risk_score = sc

        # Render annotated frame
        for z in eng.zones:
            cv2.polylines(frame, [z["poly"]], True, (0, 0, 255), 2)
        for x in last:
            k = f"{eng.cam}:{'O' if x['cls'] != 'person' else 'P'}{x['id']}"
            sc = eng.score(k, t)[0]
            col = (0, 0, 255) if sc >= eng.p["thr"] else (0, 165, 255) if sc > 15 else (0, 200, 0)
            b = tuple(map(int, x["box"]))
            cv2.rectangle(frame, b[:2], b[2:], col, 2)
            cv2.putText(frame, f"{x['cls']}{x['id']} r={sc:.0f}", (b[0], b[1] - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.5, col, 1)

        if vw is None:
            vw = create_video_writer(annotated_video_path, fps, (frame.shape[1], frame.shape[0]))
        vw.write(frame)

        if progress_callback and frame_idx % 5 == 0:
            progress_callback(frame_idx, total_frames, peak_risk_score, last)

    ev.flush()
    if vw:
        vw.release()
    cap.release()

    # Determine clear reason if no alert was triggered
    has_zones = bool(zones_config and len(zones_config) > 0)
    thr = cfg.get("thr", 35)

    if not generated_alerts:
        if not has_zones:
            no_alert_reason = f"No restricted zone was drawn, so zone intrusion signals were skipped. Tracked individuals reached a peak risk score of {peak_risk_score:.1f} out of {thr} threshold from movement signals alone."
        else:
            no_alert_reason = f"No alert threshold was reached. Highest risk score observed: {peak_risk_score:.1f} out of {thr} threshold. See risk timeline above."
    else:
        no_alert_reason = f"Alerts generated: {len(generated_alerts)} incident(s) detected crossing risk threshold {thr}."

    return {
        "total_frames": total_frames,
        "peak_risk_score": round(peak_risk_score, 1),
        "alerts": generated_alerts,
        "no_alert_reason": no_alert_reason,
        "annotated_video_path": annotated_video_path,
        "chain_file": os.path.join(output_dir, "alerts.chain.jsonl")
    }
