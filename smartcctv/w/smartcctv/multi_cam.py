"""SmartCCTV Multi-Camera Runner:
Concurrent multi-camera stream processing with blind-spot transit tracking and risk propagation.
Run: python -m smartcctv.multi_cam --config smartcctv/multi_config.json
"""
import argparse, json, os, time, threading, cv2, numpy as np
import supervision as sv
from .detector import Detector, MotionGate
from .risk import RiskEngine
from .evidence import Evidence, Chain
from .tamper import TamperMonitor
from .xcam import CrossCam, embed
from .run import get_detector

class MultiCameraOrchestrator:
    def __init__(self, config_path, out_dir="out_multi", detector_type=None, max_frames=0):
        self.cfg = json.load(open(config_path, encoding="utf-8"))
        self.out_dir = out_dir
        self.detector_type = detector_type
        self.max_frames = max_frames
        os.makedirs(out_dir, exist_ok=True)

        # Build topology dictionary: (cam_a, cam_b) -> (mu, sigma)
        edges = {}
        for edge in self.cfg.get("topology", []):
            edges[(edge[0], edge[1])] = (float(edge[2]), float(edge[3]))
        
        self.xcam = CrossCam(edges=edges, use_topology=True)
        self.lock = threading.Lock()
        self.global_alerts = []
        self.global_chain = Chain(f"{out_dir}/multi_alerts.chain.jsonl")

    def run_camera(self, cam_cfg):
        cam_id = cam_cfg["id"]
        source = cam_cfg["source"]
        cap = cv2.VideoCapture(source)
        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        
        det, det_name = get_detector(cam_cfg, self.detector_type)
        gate = MotionGate(regions=list(cam_cfg.get("zones", {}).values()))
        tam = TamperMonitor()
        trk = sv.ByteTrack(track_activation_threshold=0.25, lost_track_buffer=int(fps * 3),
                           minimum_matching_threshold=0.8, frame_rate=int(fps), minimum_consecutive_frames=2)
        
        eng = RiskEngine(cam_cfg, fps)
        cam_out = f"{self.out_dir}/{cam_id}"
        os.makedirs(cam_out, exist_ok=True)
        ev = Evidence(cam_out, fps, meta={"camera": cam_id, "detector": det_name})

        active_gids = {}  # local_tid -> global_gid
        last_seen = {}
        i = 0
        
        print(f"[{cam_id}] Stream thread active (Source: {source})")

        while True:
            ok, frame = cap.read()
            if not ok or (self.max_frames and i >= self.max_frames):
                break
            
            t = i / fps
            i += 1
            ev.push(t, frame)

            for al in tam.update(t, frame):
                ev.start(al)
                with self.lock:
                    self.global_chain.append(al)

            run_det = gate(frame) and (i % max(1, int(fps / 10)) == 0)
            if run_det:
                d = det(frame)
                xyxy = np.array([x[:4] for x in d], float).reshape(-1, 4) if d else np.empty((0, 4), float)
                confs = np.array([x[4] for x in d], float) if d else np.empty((0,), float)
                cids = np.array([det.names.index(x[5]) for x in d], int) if d else np.empty((0,), int)
                
                dets = sv.Detections(xyxy=xyxy, confidence=confs, class_id=cids)
            else:
                dets = sv.Detections.empty()
                
            tr = trk.update_with_detections(dets)
            tracks = [dict(id=int(tid), cls=det.names[int(c)], box=tuple(map(float, b)))
                      for b, tid, c in zip(tr.xyxy, tr.tracker_id, tr.class_id)]

            # Process cross-camera linking for persons
            current_tids = set()
            for trk_obj in tracks:
                tid = trk_obj["id"]
                current_tids.add(tid)
                last_seen[tid] = t

                if trk_obj["cls"] == "person":
                    if tid not in active_gids:
                        emb = embed(frame, trk_obj["box"])
                        with self.lock:
                            gid, post, gap = self.xcam.on_appear(cam_id, t, emb)
                        active_gids[tid] = gid
                        
                        if gap:
                            # Re-identify gap dwell anomaly in blind spot
                            print(f"[{cam_id}] [BLIND SPOT ALERT] Entity {gid} exceeded expected transit time (+{gap['excess_s']}s)")
                            eng.emit(f"{cam_id}:P{tid}", "GAP_DWELL", t)
                    
                    if i % 3 == 0:
                        ev.best_shot(f"{eng.cam}:P{tid}", frame, trk_obj["box"])

            # Check departed tracks to register exit ghosts
            departed = [tid for tid in list(active_gids.keys()) if tid not in current_tids and (t - last_seen.get(tid, t)) > 1.5]
            for tid in departed:
                gid = active_gids.pop(tid)
                # Register exit into blind spot
                with self.lock:
                    self.xcam.on_exit(gid, cam_id, t, np.zeros(96, dtype=np.float32))

            for al in eng.update(t, tracks):
                if al["status"] == "SUPPRESSED_BY_BUDGET":
                    continue
                ev.start(al)
                local_tid = int(al["entity"].split(":")[-1][1:])
                gid = active_gids.get(local_tid, "Unknown")
                al["global_identity"] = gid
                
                with self.lock:
                    self.global_alerts.append(al)
                    self.global_chain.append(al)
                print(f"[{cam_id}] [ALERT] t={t:.1f}s ID={gid} score={al['score']} {al['reasons']} zone={al['zone']}")

        ev.flush()
        cap.release()
        print(f"[{cam_id}] Stream finished ({i} frames processed).")

    def run_all(self):
        threads = []
        for cam in self.cfg["cameras"]:
            t = threading.Thread(target=self.run_camera, args=(cam,))
            threads.append(t)
            t.start()
        
        for t in threads:
            t.join()

        ok, n, _ = Chain.verify(f"{self.out_dir}/multi_alerts.chain.jsonl")
        print(f"\n[Multi-Camera] All streams completed. Total alerts recorded: {n}, Chain Verified: {ok}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="smartcctv/multi_config.json")
    ap.add_argument("--out", default="out_multi")
    ap.add_argument("--detector", choices=["yolov8", "darknet"], default="yolov8")
    ap.add_argument("--max-frames", type=int, default=200)
    args = ap.parse_args()

    orchestrator = MultiCameraOrchestrator(
        config_path=args.config,
        out_dir=args.out,
        detector_type=args.detector,
        max_frames=args.max_frames
    )
    orchestrator.run_all()

if __name__ == "__main__":
    main()
