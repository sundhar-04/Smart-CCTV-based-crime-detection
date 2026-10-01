import sys
import os
import json
import hashlib
import time
import base64
import numpy as np
import cv2

# Add smartcctv package parent directory to sys.path
W_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "smartcctv", "w"))
if W_DIR not in sys.path:
    sys.path.insert(0, W_DIR)

try:
    from smartcctv.detector_yolo8 import YoloDetector
    from smartcctv.detector import Detector, MotionGate
    from smartcctv.risk import RiskEngine, WEAPON_CLS
    from smartcctv.evidence import Evidence, Chain, create_video_writer
    from smartcctv.tamper import TamperMonitor
    from smartcctv.run import SimpleIOUTracker, get_detector, HAVE_SUPERVISION
    from smartcctv.pose_violence import PoseViolenceDetector
    from smartcctv.weapon_detector import WeaponDetector
    SMARTCCTV_AVAILABLE = True
except Exception as e:
    print(f"[BRIDGE WARN] Could not import smartcctv modules directly: {e}")
    SMARTCCTV_AVAILABLE = False

if HAVE_SUPERVISION:
    import supervision as sv


def run_video_analysis(video_path: str, output_dir: str, zones_config: dict = None, progress_callback=None, frame_callback=None, max_frames: int = None):
    """
    Executes the exact YOLOv8 + ByteTrack + RiskEngine pipeline on an uploaded video.
    Emits real-time frame-by-frame detections via frame_callback as processing happens.
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
    if max_frames:
        total_frames = min(total_frames, max_frames)
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0

    det, det_name = get_detector(cfg, "yolov8")
    tam = TamperMonitor()

    if HAVE_SUPERVISION:
        trk = sv.ByteTrack(track_activation_threshold=0.25, lost_track_buffer=int(fps * 3),
                           minimum_matching_threshold=0.8, frame_rate=int(fps), minimum_consecutive_frames=1)
    else:
        trk = SimpleIOUTracker(fps=fps)

    meta = {"detector": det_name, "camera": cfg.get("camera_id", "ANALYSIS_CAM")}
    weights_path = os.path.join(output_dir, "weights.json")
    eng = RiskEngine(cfg, fps, weights_path=weights_path)
    ev = Evidence(output_dir, fps, meta=meta)
    pose_detector = PoseViolenceDetector() if SMARTCCTV_AVAILABLE else None
    weapon_detector = WeaponDetector() if SMARTCCTV_AVAILABLE else None

    names = det.names
    frame_idx = 0
    peak_risk_score = 0.0
    generated_alerts = []

    vw = None
    annotated_video_path = os.path.join(output_dir, "annotated_analysis.mp4")

    while True:
        ok, frame = cap.read()
        if not ok or (max_frames and frame_idx >= max_frames):
            break
        
        t = frame_idx / fps
        frame_idx += 1
        ev.push(t, frame)

        for al in tam.update(t, frame):
            ev.start(al)

        # Run detector on frame
        d = det(frame)
        xyxy = np.array([x[:4] for x in d], float).reshape(-1, 4) if d else np.empty((0, 4), float)
        confs = np.array([x[4] for x in d], float) if d else np.empty((0,), float)
        cids = np.array([names.index(x[5]) for x in d], int) if d else np.empty((0,), int)

        if HAVE_SUPERVISION:
            dets = sv.Detections(xyxy=xyxy, confidence=confs, class_id=cids)
        else:
            dets = [(x[:4], names.index(x[5]), x[4]) for x in d]
        
        tr = trk.update_with_detections(dets)
        
        last = []
        for idx, (b, tid, c) in enumerate(zip(tr.xyxy, tr.tracker_id, tr.class_id)):
            track_conf = 0.90
            if getattr(tr, "confidence", None) is not None and len(tr.confidence) > idx and tr.confidence[idx] is not None:
                track_conf = float(tr.confidence[idx])
            elif len(confs) > 0:
                box_arr = np.array(b)
                ious = [
                    max(0, min(box_arr[2], db[2]) - max(box_arr[0], db[0])) * max(0, min(box_arr[3], db[3]) - max(box_arr[1], db[1]))
                    for db in xyxy
                ]
                best_idx = int(np.argmax(ious)) if ious else 0
                track_conf = float(confs[best_idx])
            last.append(dict(id=int(tid), cls=names[int(c)], box=tuple(map(float, b)), conf=round(track_conf, 2)))

        if len(last) >= 2:
            keep = [True] * len(last)
            for ki in range(len(last)):
                if not keep[ki]: continue
                b1, a1 = last[ki]["box"], (last[ki]["box"][2]-last[ki]["box"][0])*(last[ki]["box"][3]-last[ki]["box"][1])
                for kj in range(ki + 1, len(last)):
                    if not keep[kj] or last[ki]["cls"] != last[kj]["cls"]: continue
                    b2, a2 = last[kj]["box"], (last[kj]["box"][2]-last[kj]["box"][0])*(last[kj]["box"][3]-last[kj]["box"][1])
                    dx, dy = min(b1[2], b2[2]) - max(b1[0], b2[0]), min(b1[3], b2[3]) - max(b1[1], b2[1])
                    if dx > 0 and dy > 0 and (dx * dy) / min(a1, a2) > 0.70:
                        if a1 >= a2: keep[kj] = False
                        else: keep[ki] = False; break
            last = [p for p, k in zip(last, keep) if k]

        persons_in_frame = [x for x in last if x["cls"] == "person"]
        for x in persons_in_frame:
            if frame_idx % 3 == 0:
                ev.best_shot(f"{eng.cam}:P{x['id']}", frame, x["box"])

        if pose_detector and persons_in_frame:
            for pev in pose_detector.analyze(frame, t, persons_in_frame):
                pk = f"{eng.cam}:P{pev['track_id']}"
                eng.emit(pk, pev["type"], t)

        # Run dedicated weapon and firearm detector when persons are present
        if weapon_detector and persons_in_frame:
            for wd in weapon_detector.detect(frame, persons_in_frame, t=t):
                last.append(dict(id=900 + len(last), cls=wd["cls"], box=wd["box"], conf=round(float(wd.get("conf", 0.88)), 2)))
                if wd.get("person_id") is not None:
                    pk = f"{eng.cam}:P{wd['person_id']}"
                    z = eng._zone(((wd["box"][0] + wd["box"][2]) / 2, wd["box"][3]))
                    eng.emit(pk, "WEAPON_NEAR_PERSON", t, z)

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

        orig_h, orig_w = frame.shape[:2]

        # Extract structured detections conforming to required schema
        frame_detections = []
        for x in last:
            k = f"{eng.cam}:{'O' if x['cls'] != 'person' else 'P'}{x['id']}"
            sc, sig_types = eng.score(k, t)
            frame_detections.append({
                "track_id": int(x["id"]),
                "class": str(x["cls"]),
                "confidence": float(x.get("conf", 0.90)),
                "bbox": [round(float(v), 1) for v in x["box"]],
                "risk_score": round(float(sc), 1),
                "signals": sorted(sig_types) if sig_types else []
            })

        # Generate base64 streaming preview image (clean frame)
        preview_w = min(orig_w, 720)
        preview_h = int(orig_h * (preview_w / orig_w))
        preview_frame = cv2.resize(frame, (preview_w, preview_h), interpolation=cv2.INTER_AREA) if preview_w < orig_w else frame
        ok_enc, buf = cv2.imencode(".jpg", preview_frame, [cv2.IMWRITE_JPEG_QUALITY, 65])
        b64_img = f"data:image/jpeg;base64,{base64.b64encode(buf).decode('ascii')}" if ok_enc else None

        # Emit real-time frame detection payload
        if frame_callback:
            frame_payload = {
                "frame_index": frame_idx,
                "timestamp": round(t, 2),
                "total_frames": total_frames,
                "orig_w": orig_w,
                "orig_h": orig_h,
                "detections": frame_detections,
                "risk_score": round(float(peak_risk_score), 1),
                "image": b64_img
            }
            frame_callback(frame_payload)

        # Render annotations on copy for output video export
        annotated_frame = frame.copy()
        for z in eng.zones:
            cv2.polylines(annotated_frame, [z["poly"]], True, (0, 0, 255), 2)
        for x in last:
            k = f"{eng.cam}:{'O' if x['cls'] != 'person' else 'P'}{x['id']}"
            sc, sig_types = eng.score(k, t)
            is_weapon = x["cls"] in WEAPON_CLS
            violence_signals = sig_types & {
                "FIGHT_SUSPECTED", "AGGRESSIVE_APPROACH", "PERSON_DOWN",
                "PHYSICAL_STRIKE", "OVERHEAD_STANCE", "VIOLENT_SWING", "KNOCKOUT_FALL"
            }
            has_violence = bool(violence_signals)
            if is_weapon or has_violence:
                col = (50, 50, 255)  # BGR high-alert red
            elif sc >= eng.p["thr"]:
                col = (0, 0, 255)    # red
            elif sc > 15:
                col = (0, 165, 255)  # orange
            else:
                col = (0, 200, 0)    # green
            b = tuple(map(int, x["box"]))
            cv2.rectangle(annotated_frame, b[:2], b[2:], col, 2)
            if is_weapon:
                label = f"WEAPON:{x['cls']} r={sc:.0f}"
            elif has_violence:
                v_name = next(iter(violence_signals))
                label = f"ALERT:{v_name} r={sc:.0f}"
            else:
                label = f"{x['cls']}{x['id']} r={sc:.0f}"
            cv2.putText(annotated_frame, label, (b[0], max(b[1] - 4, 10)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, col, 1, cv2.LINE_AA)

        # Write to annotated output video
        if vw is None:
            vw = create_video_writer(annotated_video_path, fps, (frame.shape[1], frame.shape[0]))
        vw.write(annotated_frame)

        # Save live frame for polling fallback
        if frame_idx % 2 == 0 or frame_idx == 1:
            live_frame_path = os.path.join(output_dir, "live_frame.jpg")
            cv2.imwrite(live_frame_path, preview_frame, [cv2.IMWRITE_JPEG_QUALITY, 70])

        if progress_callback and (frame_idx % 5 == 0 or frame_idx == total_frames):
            live_tracks = [{
                "id": d["track_id"],
                "cls": d["class"],
                "box": [round(v) for v in d["bbox"]],
                "risk_score": d["risk_score"],
                "signals": d["signals"]
            } for d in frame_detections]
            progress_callback(frame_idx, total_frames, peak_risk_score, live_tracks, generated_alerts, frame_detections, orig_w, orig_h)

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
