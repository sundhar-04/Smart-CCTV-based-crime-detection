"""python -m smartcctv.run --config smartcctv/config.json"""
import argparse, json, os, time, cv2, numpy as np, supervision as sv
from .detector import Detector, MotionGate
from .risk import RiskEngine
from .evidence import Evidence, Chain
from .tamper import TamperMonitor
from .notify import dispatch
try:
    from .detector_yolo8 import YoloDetector
except ImportError:  # headless / CI without libGL
    YoloDetector = None  # type: ignore

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="smartcctv/config.json"); ap.add_argument("--source"); ap.add_argument("--out", default="out")
    ap.add_argument("--max-frames", type=int, default=0); ap.add_argument("--no-video", action="store_true")
    a = ap.parse_args(); cfg = json.load(open(a.config)); os.makedirs(a.out, exist_ok=True)
    cap = cv2.VideoCapture(a.source or cfg["source"]); fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    detector_type = cfg.get("detector", "opencv")
    if detector_type == "yolov8" and YoloDetector is not None:
        det = YoloDetector(weights=cfg.get("model_dir", "models"),
                           imgsz=cfg.get("yolov8_imgsz", 320),
                           conf=cfg.get("yolov8_conf", 0.25))
    else:
        det = Detector(cfg.get("model_dir", "models")); gate = MotionGate()
    trk = sv.ByteTrack(track_activation_threshold=0.25, lost_track_buffer=int(fps * 3), minimum_matching_threshold=0.8,
                       frame_rate=int(fps), minimum_consecutive_frames=2)
    eng = RiskEngine(cfg, fps, weights_path=f"{a.out}/weights.json"); ev = Evidence(a.out, fps)
    names = det.names; last = []; i = skipped = 0; vw = None; nalerts = nsupp = 0; t_det = 0.0
    while True:
        ok, frame = cap.read()
        if not ok or (a.max_frames and i >= a.max_frames): break
        t = i / fps; i += 1; ev.push(t, frame)
        for al in tam.update(t, frame):
            ev.start(al); print(f"[TAMPER] t={t:.1f}s {al['kind']}"); dispatch(al, a.out)
        if gate(frame):
            t0 = time.time(); d = det(frame); t_det += time.time() - t0
            xyxy = np.array([x[:4] for x in d], float).reshape(-1, 4)
            dets = sv.Detections(xyxy=xyxy, confidence=np.array([x[4] for x in d], float),
                                 class_id=np.array([names.index(x[5]) for x in d], int))
            tr = trk.update_with_detections(dets)
            last = [dict(id=int(tid), cls=names[int(c)], box=tuple(map(float, b)))
                    for b, tid, c in zip(tr.xyxy, tr.tracker_id, tr.class_id)]
        else: skipped += 1  # no motion: state unchanged, detector skipped
        for x in last:
            if x["cls"] == "person" and i % 3 == 0: ev.best_shot(f"{eng.cam}:P{x['id']}", frame, x["box"])
        for al in eng.update(t, last):
            if al["status"] == "SUPPRESSED_BY_BUDGET":
                nsupp += 1; ev.chain.append(al); continue
            nalerts += 1; ev.start(al); print(f"[ALERT] t={t:.1f}s score={al['score']} {al['entity']} {al['reasons']} zone={al['zone']}")
        if not a.no_video:
            for z in eng.zones: cv2.polylines(frame, [z["poly"]], True, (0, 0, 255), 2)
            for x in last:
                k = f"{eng.cam}:{'O' if x['cls'] != 'person' else 'P'}{x['id']}"; sc = eng.score(k, t)[0]
                col = (0, 0, 255) if sc >= eng.p["thr"] else (0, 165, 255) if sc > 15 else (0, 200, 0)
                b = tuple(map(int, x["box"])); cv2.rectangle(frame, b[:2], b[2:], col, 2)
                cv2.putText(frame, f"{x['cls']}{x['id']} r={sc:.0f}", (b[0], b[1] - 4), 0, 0.5, col, 1)
            if vw is None: vw = cv2.VideoWriter(f"{a.out}/annotated.mp4", cv2.VideoWriter_fourcc(*"mp4v"), fps, frame.shape[1::-1])
            vw.write(frame)
    ev.flush()
    if vw: vw.release()
    ok, n, bad = Chain.verify(f"{a.out}/alerts.chain.jsonl")
    s = dict(frames=i, detector_skipped_pct=round(100 * skipped / max(i, 1), 1), detector_calls=det.calls, stage2_verifications=det.verify_calls,
             avg_detector_ms=round(1000 * t_det / max(det.calls, 1), 1), alerts_raised=nalerts, suppressed_by_budget=nsupp, chain_ok=ok, chain_len=n)
    json.dump(s, open(f"{a.out}/summary.json", "w"), indent=1); print(s)

if __name__ == "__main__": main()
