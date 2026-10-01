import sys, os, cv2, numpy as np
sys.path.insert(0, r'd:\Doom\Smart-CCTV-based-crime-detection\smartcctv\w')

from smartcctv.detector_yolo8 import YoloDetector
from smartcctv.detector import MotionGate
from smartcctv.risk import RiskEngine, GROUP
from smartcctv.pose_violence import PoseViolenceDetector
from smartcctv.weapon_detector import WeaponDetector
import supervision as sv

def run_clip(clip_path, max_frames=None, det_interval_div=15):
    cap = cv2.VideoCapture(clip_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    limit = min(total_frames, max_frames) if max_frames else total_frames

    det = YoloDetector()
    names = det.names
    gate = MotionGate()
    pose_det = PoseViolenceDetector()
    weapon_det = WeaponDetector()
    eng = RiskEngine({})

    # BUG 1 FIX: minimum_consecutive_frames is kept at 2!
    trk = sv.ByteTrack(track_activation_threshold=0.25, lost_track_buffer=int(fps * 3),
                       minimum_matching_threshold=0.8, frame_rate=int(fps), minimum_consecutive_frames=2)

    last = []
    alerts = []
    frame_logs = []

    det_step = max(1, int(fps / det_interval_div))
    print(f"\n{'='*70}\nRUNNING CLIP: {os.path.basename(clip_path)} ({limit} frames, {fps:.1f} fps, det_step={det_step})\n{'='*70}")

    for f_idx in range(1, limit + 1):
        ok, frame = cap.read()
        if not ok: break
        t = f_idx / fps

        run_det = gate(frame) and (f_idx % det_step == 0 or f_idx == 1)
        if run_det:
            d = det(frame)
            xyxy = np.array([x[:4] for x in d], float).reshape(-1, 4) if d else np.empty((0, 4), float)
            confs = np.array([x[4] for x in d], float) if d else np.empty((0,), float)
            cids = np.array([names.index(x[5]) for x in d], int) if d else np.empty((0,), int)
            dets = sv.Detections(xyxy=xyxy, confidence=confs, class_id=cids)
            
            # BUG 1 FIX: Only update tracker on detection frames
            tr = trk.update_with_detections(dets)
            last = [dict(id=int(tid), cls=names[int(c)], box=tuple(map(float, b)))
                    for b, tid, c in zip(tr.xyxy, tr.tracker_id, tr.class_id)]
            # Filter nested/sub-box duplicate tracks of the same entity
            if len(last) >= 2:
                keep = [True] * len(last)
                for i in range(len(last)):
                    if not keep[i]: continue
                    b1, a1 = last[i]["box"], (last[i]["box"][2]-last[i]["box"][0])*(last[i]["box"][3]-last[i]["box"][1])
                    for j in range(i + 1, len(last)):
                        if not keep[j] or last[i]["cls"] != last[j]["cls"]: continue
                        b2, a2 = last[j]["box"], (last[j]["box"][2]-last[j]["box"][0])*(last[j]["box"][3]-last[j]["box"][1])
                        dx, dy = min(b1[2], b2[2]) - max(b1[0], b2[0]), min(b1[3], b2[3]) - max(b1[1], b2[1])
                        if dx > 0 and dy > 0 and (dx * dy) / min(a1, a2) > 0.70:
                            if a1 >= a2: keep[j] = False
                            else: keep[i] = False; break
                last = [p for p, k in zip(last, keep) if k]

        persons = [x for x in last if x["cls"] == "person"]

        # Run pose model on detection frames with persons
        pose_events = []
        kpts_str = []
        if run_det and persons:
            pose_events = pose_det.analyze(frame, t, persons)
            for pev in pose_events:
                pk = f"{eng.cam}:P{pev['track_id']}"
                eng.emit(pk, pev["type"], t)
                
            # Log raw pose keypoint confidences
            if pose_det.model:
                try:
                    res_p = pose_det.model(frame, imgsz=640, conf=0.25, device=pose_det.device, verbose=False)[0]
                    if res_p.keypoints is not None:
                        confs_k = res_p.keypoints.conf.cpu().numpy() if res_p.keypoints.conf is not None else []
                        for bi, ck in enumerate(confs_k):
                            wl = ck[9] if len(ck) > 9 else 0.0
                            wr = ck[10] if len(ck) > 10 else 0.0
                            hd = ck[0] if len(ck) > 0 else 0.0
                            kpts_str.append(f"body_{bi}(wL={wl:.2f},wR={wr:.2f},hd={hd:.2f})")
                except Exception:
                    pass

        # Run weapon detection on detection frames when persons are present
        if run_det and persons and weapon_det:
            for wd in weapon_det.detect(frame, persons, t=t):
                last.append(dict(id=900 + len(last), cls=wd["cls"], box=wd["box"]))
                if wd.get("person_id") is not None:
                    pk = f"{eng.cam}:P{wd['person_id']}"
                    z = eng._zone(((wd["box"][0] + wd["box"][2]) / 2, wd["box"][3]))
                    eng.emit(pk, "WEAPON_NEAR_PERSON", t, z)

        # Risk update
        curr_alerts = eng.update(t, last)
        for al in curr_alerts:
            alerts.append(al)

        # Log entry for this frame
        p_ids = [p["id"] for p in persons]
        p_boxes = [[round(coord, 1) for coord in p["box"]] for p in persons]

        # Gather risk status per entity
        risk_strs = []
        for p in persons:
            pk = f"{eng.cam}:P{p['id']}"
            sc, types = eng.score(pk, t)
            evs = [e[1] for e in eng.events.get(pk, []) if t - e[0] < 5.0]
            active_groups = {GROUP[x] for x in types}
            risk_strs.append(f"{pk}: sc={sc:.1f} grps={active_groups} evs={evs}")

        entry = (f"[t={t:.2f}s | F{f_idx:03d}] n_persons={len(persons)} ids={p_ids} boxes={p_boxes}\n"
                 f"   pose_events={pose_events} kpts=[{', '.join(kpts_str)}]\n"
                 f"   risk: {'; '.join(risk_strs) if risk_strs else 'no_tracks'}")
        
        if curr_alerts:
            entry += f"\n   >>> ALERTS FIRED: {[{'entity': a['entity'], 'score': a['score'], 'reasons': a['reasons'], 'status': a['status']} for a in curr_alerts]}"

        frame_logs.append(entry)

    cap.release()
    print(f"FINISHED {os.path.basename(clip_path)}. Total frames: {limit}, Total alerts: {len(alerts)}")
    return frame_logs, alerts

if __name__ == "__main__":
    clip1 = r'D:\Doom\Smart-CCTV-based-crime-detection\backend\uploads\JOB-E8807273_Ravi_crime.mp4'
    clip2 = r'D:\Doom\Smart-CCTV-based-crime-detection\smartcctv\w\data\vtest.avi'
    clip3 = r'D:\Doom\Smart-CCTV-based-crime-detection\backend\uploads\JOB-161E10F0_gettyimages-1995820194-640_adpp.mp4'

    print("=== STARTING 3-CLIP VERIFICATION ===")
    logs1, alerts1 = run_clip(clip1, max_frames=240, det_interval_div=15)
    logs2, alerts2 = run_clip(clip2, max_frames=250, det_interval_div=15)
    logs3, alerts3 = run_clip(clip3, max_frames=250, det_interval_div=15)

    with open("clip1_assault_log.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(logs1))

    with open("clip2_vtest_log.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(logs2))

    with open("clip3_pedestrians_log.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(logs3))

    print("\n=== SUMMARY OF ALL 3 RUNS ===")
    print(f"Clip 1 (Assault JOB-E8807273_Ravi_crime.mp4): {len(alerts1)} alerts")
    for a in alerts1:
        print(f"   Alert: {a['entity']} score={a['score']} reasons={a['reasons']}")

    print(f"\nClip 2 (Normal walking vtest.avi): {len(alerts2)} alerts")
    for a in alerts2:
        print(f"   Alert: {a['entity']} score={a['score']} reasons={a['reasons']}")

    print(f"\nClip 3 (Pedestrians gettyimages-1995820194.mp4): {len(alerts3)} alerts")
    for a in alerts3:
        print(f"   Alert: {a['entity']} score={a['score']} reasons={a['reasons']}")
