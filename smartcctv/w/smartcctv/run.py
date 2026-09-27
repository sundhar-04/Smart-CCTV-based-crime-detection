"""python -m smartcctv.run --config smartcctv/config.json [--detector yolov8|darknet]"""
import argparse, json, os, time, cv2, numpy as np, hashlib
from .detector import Detector, MotionGate
from .risk import RiskEngine
from .evidence import Evidence, Chain, create_video_writer
from .tamper import TamperMonitor
from .notify import dispatch

try:
    import supervision as sv
    HAVE_SUPERVISION = True
except Exception as e:
    HAVE_SUPERVISION = False
    print(f"[WARN] Failed to import supervision ({e}). Using built-in IOU tracker.")

class TrackResult:
    def __init__(self, xyxy, tracker_id, class_id):
        self.xyxy = np.array(xyxy, float).reshape(-1, 4) if len(xyxy) else np.empty((0, 4), float)
        self.tracker_id = np.array(tracker_id, int) if len(tracker_id) else np.empty((0,), int)
        self.class_id = np.array(class_id, int) if len(class_id) else np.empty((0,), int)

class SimpleIOUTracker:
    def __init__(self, fps=25.0):
        self.next_id = 1
        self.tracks = {}
        self.max_lost = int(fps * 3)

    def _iou(self, b1, b2):
        x1, y1 = max(b1[0], b2[0]), max(b1[1], b2[1])
        x2, y2 = min(b1[2], b2[2]), min(b1[3], b2[3])
        inter = max(0, x2 - x1) * max(0, y2 - y1)
        area1 = max(0, b1[2] - b1[0]) * max(0, b1[3] - b1[1])
        area2 = max(0, b2[2] - b2[0]) * max(0, b2[3] - b2[1])
        union = area1 + area2 - inter
        return inter / union if union > 0 else 0.0

    def update_with_detections(self, raw_dets):
        for t in self.tracks.values():
            t["lost"] += 1
            
        matched_dets = set()
        if self.tracks and raw_dets:
            for tid, t in self.tracks.items():
                best_iou = 0.2
                best_idx = -1
                for idx, d in enumerate(raw_dets):
                    if idx in matched_dets:
                        continue
                    iou = self._iou(t["box"], d[0])
                    if iou > best_iou:
                        best_iou = iou
                        best_idx = idx
                if best_idx != -1:
                    matched_dets.add(best_idx)
                    d = raw_dets[best_idx]
                    self.tracks[tid]["box"] = d[0]
                    self.tracks[tid]["cls"] = d[1]
                    self.tracks[tid]["lost"] = 0

        for idx, d in enumerate(raw_dets):
            if idx not in matched_dets:
                self.tracks[self.next_id] = {"box": d[0], "cls": d[1], "lost": 0}
                self.next_id += 1

        self.tracks = {tid: t for tid, t in self.tracks.items() if t["lost"] <= self.max_lost}
        active = [(t["box"], tid, t["cls"]) for tid, t in self.tracks.items() if t["lost"] == 0]
        if not active:
            return TrackResult([], [], [])
        return TrackResult([x[0] for x in active], [x[1] for x in active], [x[2] for x in active])

def get_detector(cfg, detector_type=None):
    dtype = detector_type or cfg.get("detector", "yolov8")
    if dtype.lower() == "yolov8":
        try:
            from .detector_yolo8 import YoloDetector
            weights = cfg.get("yolo_weights", "yolov8n.pt")
            imgsz = cfg.get("imgsz", 640)
            return YoloDetector(weights=weights, imgsz=imgsz, conf=cfg.get("detector_conf", 0.25)), "yolov8"
        except Exception as e:
            print(f"[WARN] Failed to initialize YoloDetector ({e}). Falling back to Darknet.")
    
    return Detector(cfg.get("model_dir", "models")), "darknet"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="smartcctv/config.json")
    ap.add_argument("--source")
    ap.add_argument("--out", default="out")
    ap.add_argument("--detector", choices=["yolov8", "darknet"])
    ap.add_argument("--max-frames", type=int, default=0)
    ap.add_argument("--no-video", action="store_true")
    a = ap.parse_args()

    cfg = json.load(open(a.config, encoding="utf-8"))
    os.makedirs(a.out, exist_ok=True)
    
    cfg_hash = hashlib.sha256(open(a.config, "rb").read()).hexdigest()[:16]
    cap = cv2.VideoCapture(a.source or cfg["source"])
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    
    det, det_name = get_detector(cfg, a.detector)
    gate = MotionGate(regions=list(cfg.get("zones", {}).values()))
    tam = TamperMonitor()
    
    # Tracking setup
    if HAVE_SUPERVISION:
        trk = sv.ByteTrack(track_activation_threshold=0.25, lost_track_buffer=int(fps * 3),
                           minimum_matching_threshold=0.8, frame_rate=int(fps), minimum_consecutive_frames=2)
    else:
        trk = SimpleIOUTracker(fps=fps)

    
    meta = {"detector": det_name, "config_hash": cfg_hash, "camera": cfg.get("camera_id", "cam1")}
    eng = RiskEngine(cfg, fps, weights_path=f"{a.out}/weights.json")
    ev = Evidence(a.out, fps, meta=meta)
    
    names = det.names
    last = []
    i = skipped = 0
    vw = None
    nalerts = nsupp = 0
    t_det = 0.0

    print(f"[SmartCCTV] Engine started with {det_name.upper()} detector on {cfg.get('camera_id', 'cam1')} (Source: {a.source or cfg['source']})")

    while True:
        ok, frame = cap.read()
        if not ok or (a.max_frames and i >= a.max_frames):
            break
        
        t = i / fps
        i += 1
        ev.push(t, frame)
        
        for al in tam.update(t, frame):
            ev.start(al)
            print(f"[TAMPER] t={t:.1f}s {al['kind']}")
            dispatch(al, a.out)
            
        run_det = gate(frame) and (i % max(1, int(fps / 10)) == 0)
        if run_det:
            t0 = time.time()
            d = det(frame)
            t_det += time.time() - t0
            
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
            if x["cls"] == "person" and i % 3 == 0:
                ev.best_shot(f"{eng.cam}:P{x['id']}", frame, x["box"])
                
        for al in eng.update(t, last):
            if al["status"] == "SUPPRESSED_BY_BUDGET":
                nsupp += 1
                ev.chain.append(al)
                continue
            nalerts += 1
            ev.start(al)
            print(f"[ALERT] t={t:.1f}s score={al['score']} {al['entity']} {al['reasons']} zone={al['zone']}")
            
        if not a.no_video:
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
                vw = create_video_writer(f"{a.out}/annotated.mp4", fps, (frame.shape[1], frame.shape[0]))
            vw.write(frame)
            
    ev.flush()
    if vw:
        vw.release()
        
    ok, n, bad = Chain.verify(f"{a.out}/alerts.chain.jsonl")
    summary = dict(
        frames=i,
        detector=det_name,
        detector_skipped_pct=round(100 * skipped / max(i, 1), 1),
        detector_calls=det.calls,
        stage2_verifications=det.verify_calls,
        avg_detector_ms=round(1000 * t_det / max(det.calls, 1), 1),
        alerts_raised=nalerts,
        suppressed_by_budget=nsupp,
        chain_ok=ok,
        chain_len=n
    )
    json.dump(summary, open(f"{a.out}/summary.json", "w", encoding="utf-8"), indent=1)
    print("\n=== Run Summary ===")
    print(json.dumps(summary, indent=2))

if __name__ == "__main__":
    main()
