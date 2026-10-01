"""Robust real-time tracker for CCTV surveillance.
Designed specifically for high-velocity motion (running, sudden sprinting, strikes)
where conventional IoU-only trackers (like standard ByteTrack) lose track association.
Combines linear velocity projection, normalized center-distance, scale consistency, and IoU.
"""
import math
import numpy as np
from scipy.optimize import linear_sum_assignment

class RobustRealtimeTracker:
    def __init__(self, max_lost: int = 25, match_dist_thresh: float = 1.15):
        self.max_lost = max_lost
        self.match_dist_thresh = match_dist_thresh
        self.tracks = {}  # tid -> dict(box, cls, last_seen, vel, hits, age, conf)
        self.next_id = 1
        self.frame_count = 0

    def update(self, detections: list) -> list:
        """
        detections: list of dict(box=[x1, y1, x2, y2], cls=str, conf=float) or tuples (x1, y1, x2, y2, conf, cls)
        Returns: list of dict(id=int, cls=str, box=tuple(x1, y1, x2, y2))
        """
        self.frame_count += 1
        
        # Normalize input detections
        normalized_dets = []
        for d in detections:
            if isinstance(d, dict):
                box = list(map(float, d["box"]))
                cls_name = str(d.get("cls", "person"))
                conf = float(d.get("conf", 1.0))
            elif isinstance(d, (list, tuple)) and len(d) >= 6:
                box = [float(d[0]), float(d[1]), float(d[2]), float(d[3])]
                conf = float(d[4])
                cls_name = str(d[5])
            else:
                continue
            normalized_dets.append({"box": box, "cls": cls_name, "conf": conf})

        # Predict current locations using smoothed velocity
        for tid, tr in list(self.tracks.items()):
            tr["age"] += 1
            vx, vy = tr.get("vel", (0.0, 0.0))
            b = tr["box"]
            # Damp velocity slightly if track hasn't been seen recently
            decay = 0.95 ** tr.get("time_since_seen", 0)
            tr["pred_box"] = [
                b[0] + vx * decay,
                b[1] + vy * decay,
                b[2] + vx * decay,
                b[3] + vy * decay
            ]

        matched_dets = set()
        matched_tracks = set()
        tids = list(self.tracks.keys())

        if tids and normalized_dets:
            cost_matrix = []
            for tid in tids:
                tr = self.tracks[tid]
                pb = tr.get("pred_box", tr["box"])
                pcx = (pb[0] + pb[2]) / 2.0
                pcy = (pb[1] + pb[3]) / 2.0
                ph = max(pb[3] - pb[1], 10.0)
                pw = max(pb[2] - pb[0], 10.0)

                row = []
                for d in normalized_dets:
                    # Class gate: only match detections of the same class
                    if d["cls"] != tr["cls"]:
                        row.append(1e6)
                        continue

                    db = d["box"]
                    dcx = (db[0] + db[2]) / 2.0
                    dcy = (db[1] + db[3]) / 2.0
                    dh = max(db[3] - db[1], 10.0)
                    dw = max(db[2] - db[0], 10.0)

                    # Normalized center distance (in units of track height)
                    dist_norm = math.hypot(dcx - pcx, dcy - pcy) / ph
                    
                    # Scale consistency penalty
                    scale_diff = abs(dh - ph) / max(ph, 1.0) + abs(dw - pw) / max(pw, 1.0)

                    # IoU overlap bonus
                    ix1, iy1 = max(pb[0], db[0]), max(pb[1], db[1])
                    ix2, iy2 = min(pb[2], db[2]), min(pb[3], db[3])
                    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
                    union = max(pw * ph + dw * dh - inter, 1.0)
                    iou = inter / union

                    # Combined association cost: lower is better
                    cost = dist_norm * 0.75 + scale_diff * 0.25 - iou * 0.5
                    row.append(cost)
                cost_matrix.append(row)

            cost_mat = np.array(cost_matrix)
            row_ind, col_ind = linear_sum_assignment(cost_mat)

            for r, c in zip(row_ind, col_ind):
                if cost_mat[r, c] < self.match_dist_thresh:
                    tid = tids[r]
                    d = normalized_dets[c]
                    prev_box = self.tracks[tid]["box"]
                    new_box = d["box"]
                    
                    # Compute instantaneous velocity (dx, dy of center)
                    new_cx = (new_box[0] + new_box[2]) / 2.0
                    new_cy = (new_box[1] + new_box[3]) / 2.0
                    prev_cx = (prev_box[0] + prev_box[2]) / 2.0
                    prev_cy = (prev_box[1] + prev_box[3]) / 2.0
                    
                    inst_vx = new_cx - prev_cx
                    inst_vy = new_cy - prev_cy

                    # Exponential moving average for velocity smoothing
                    old_vx, old_vy = self.tracks[tid].get("vel", (0.0, 0.0))
                    smooth_vx = inst_vx * 0.65 + old_vx * 0.35
                    smooth_vy = inst_vy * 0.65 + old_vy * 0.35

                    self.tracks[tid]["vel"] = (smooth_vx, smooth_vy)
                    self.tracks[tid]["box"] = new_box
                    self.tracks[tid]["conf"] = d["conf"]
                    self.tracks[tid]["hits"] += 1
                    self.tracks[tid]["time_since_seen"] = 0
                    matched_tracks.add(tid)
                    matched_dets.add(c)

        # Initialize new tracks for unmatched detections
        for i, d in enumerate(normalized_dets):
            if i not in matched_dets:
                tid = self.next_id
                self.next_id += 1
                self.tracks[tid] = {
                    "box": d["box"],
                    "cls": d["cls"],
                    "conf": d["conf"],
                    "hits": 1,
                    "age": 1,
                    "time_since_seen": 0,
                    "vel": (0.0, 0.0)
                }
                matched_tracks.add(tid)

        # Update and purge expired tracks
        for tid in list(self.tracks.keys()):
            if tid not in matched_tracks:
                self.tracks[tid]["time_since_seen"] = self.tracks[tid].get("time_since_seen", 0) + 1
                if self.tracks[tid]["time_since_seen"] > self.max_lost:
                    del self.tracks[tid]

        # Return currently visible tracks
        results = []
        for tid, tr in self.tracks.items():
            if tr["time_since_seen"] == 0:
                results.append({
                    "id": tid,
                    "cls": tr["cls"],
                    "box": tuple(tr["box"])
                })

        return results
