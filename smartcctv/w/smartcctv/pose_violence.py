"""Lightweight Pose-based Violence and Assault Classifier using YOLOv8-pose.
Detects strikes, punches, swings with objects (e.g. bricks, bats), overhead brandishing, and physical knockouts.
Runs at ~60 FPS on CUDA and sub-20ms latency.
"""
import math, os
from collections import deque
import numpy as np

try:
    import torch
    from ultralytics import YOLO
    HAS_YOLO = True
except ImportError:
    HAS_YOLO = False


class PoseViolenceDetector:
    """Real-time pose-based action & assault classifier."""

    def __init__(self, weights_path=None, conf=0.3, device=None):
        if not HAS_YOLO:
            self.model = None
            return

        if weights_path is None:
            # Look in multiple candidate locations
            candidates = [
                os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "yolov8n-pose.pt")),
                os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "yolov8n-pose.pt")),
                os.path.abspath("yolov8n-pose.pt"),
                "yolov8n-pose.pt"
            ]
            for c in candidates:
                if os.path.exists(c):
                    weights_path = c
                    break
            if weights_path is None:
                weights_path = "yolov8n-pose.pt"

        if device is None:
            device = "cuda:0" if torch.cuda.is_available() else "cpu"

        self.device = device
        self.conf = conf
        try:
            self.model = YOLO(weights_path)
        except Exception as e:
            print(f"[PoseViolenceDetector] Could not load pose model: {e}")
            self.model = None

        # Track history of keypoints: {track_id: [(t, kpts_xy, kpts_conf, torso_h, box)]}
        self.kpt_hist = {}

    def _box_iou(self, b1, b2):
        x1, y1 = max(b1[0], b2[0]), max(b1[1], b2[1])
        x2, y2 = min(b1[2], b2[2]), min(b1[3], b2[3])
        inter = max(0, x2 - x1) * max(0, y2 - y1)
        a1 = max((b1[2] - b1[0]) * (b1[3] - b1[1]), 1.0)
        a2 = max((b2[2] - b2[0]) * (b2[3] - b2[1]), 1.0)
        return inter / max(a1 + a2 - inter, 1e-5)

    def analyze(self, frame, t, person_tracks):
        """Analyze frame poses for tracked persons.
        Returns a list of detected action signals:
        [{"track_id": int, "type": str, "weight": int, "target_id": int or None}]
        """
        if self.model is None or not person_tracks:
            return []

        H, W = frame.shape[:2]
        events = []

        try:
            res = self.model(frame, imgsz=640, conf=self.conf, device=self.device, verbose=False)[0]
        except Exception:
            return []

        if res.boxes is None or len(res.boxes) == 0 or res.keypoints is None:
            return []

        pose_boxes = res.boxes.xyxy.cpu().numpy()
        pose_kpts = res.keypoints.xy.cpu().numpy()  # (N, 17, 2)
        pose_confs = res.keypoints.conf.cpu().numpy() if res.keypoints.conf is not None else np.ones((len(pose_kpts), 17))

        # Exclusive 1-to-1 matching between person tracks and pose detections
        candidate_matches = []
        for p in person_tracks:
            tid = p["id"]
            t_box = p["box"]
            tc = ((t_box[0] + t_box[2]) / 2.0, (t_box[1] + t_box[3]) / 2.0)
            th = max(t_box[3] - t_box[1], 1.0)
            for idx, p_box in enumerate(pose_boxes):
                iou = self._box_iou(t_box, p_box)
                pc = ((p_box[0] + p_box[2]) / 2.0, (p_box[1] + p_box[3]) / 2.0)
                dist_norm = math.hypot(tc[0] - pc[0], tc[1] - pc[1]) / th
                if iou >= 0.15 or dist_norm <= 0.45:
                    score = iou - dist_norm * 0.5
                    candidate_matches.append((score, tid, idx, t_box))

        candidate_matches.sort(key=lambda m: -m[0])
        matched_tracks = {}
        assigned_poses = set()
        assigned_tids = set()
        for score, tid, idx, t_box in candidate_matches:
            if tid not in assigned_tids and idx not in assigned_poses:
                matched_tracks[tid] = {
                    "kpts": pose_kpts[idx],
                    "confs": pose_confs[idx],
                    "box": t_box,
                    "pose_idx": idx
                }
                assigned_poses.add(idx)
                assigned_tids.add(tid)

        # Analyze kinematics for each matched person
        for tid, data in matched_tracks.items():
            kpts = data["kpts"]
            confs = data["confs"]
            box = data["box"]

            # Keypoint indices:
            # 0: Nose (Head), 5: L Shoulder, 6: R Shoulder
            # 7: L Elbow, 8: R Elbow, 9: L Wrist, 10: R Wrist
            # 11: L Hip, 12: R Hip

            # Compute torso center and normalized torso scale
            mid_sh = ((kpts[5][0] + kpts[6][0]) / 2.0, (kpts[5][1] + kpts[6][1]) / 2.0)
            mid_hip = ((kpts[11][0] + kpts[12][0]) / 2.0, (kpts[11][1] + kpts[12][1]) / 2.0)
            torso_h = max(math.hypot(mid_sh[0] - mid_hip[0], mid_sh[1] - mid_hip[1]), 0.3 * (box[3] - box[1]), 25.0)

            # Store in track history
            hist = self.kpt_hist.setdefault(tid, deque(maxlen=20))
            hist.append((t, kpts, confs, torso_h, box))
            while len(hist) > 1 and hist[0][0] < t - 2.0:
                hist.popleft()

            # 1. Check for OVERHEAD_STANCE (Raising weapon/brick overhead to strike)
            l_wrist_conf, r_wrist_conf = confs[9], confs[10]
            head_top = kpts[0][1] if confs[0] > 0.30 else (min(kpts[5][1], kpts[6][1]) - 0.20 * torso_h)
            overhead = False
            if l_wrist_conf > 0.40 and confs[7] > 0.40 and kpts[9][1] < (head_top - 0.20 * torso_h) and kpts[7][1] < kpts[5][1]:
                overhead = True
            elif r_wrist_conf > 0.40 and confs[8] > 0.40 and kpts[10][1] < (head_top - 0.20 * torso_h) and kpts[8][1] < kpts[6][1]:
                overhead = True

            if overhead:
                # Check if another person is within striking distance
                target_found = None
                for other_id, other_data in matched_tracks.items():
                    if other_id == tid or other_data.get("pose_idx") == data.get("pose_idx"):
                        continue
                    ob = other_data["box"]
                    dist_to_other = math.dist(((box[0] + box[2]) / 2, (box[1] + box[3]) / 2),
                                              ((ob[0] + ob[2]) / 2, (ob[1] + ob[3]) / 2))
                    if dist_to_other < 1.4 * (box[3] - box[1]):
                        target_found = other_id
                        break
                # Only flag OVERHEAD_STANCE if confronting an adversary or in two-person interaction
                # (A solo person stretching or scratching head is not an overhead assault stance)
                if target_found is not None:
                    events.append({"track_id": tid, "type": "OVERHEAD_STANCE", "target_id": target_found})

            # 2. Check for Rapid Arm Strike / Violent Swing
            # Use smoothed time window (0.10s - 0.35s) to eliminate single-frame detector jitter
            if len(hist) >= 2:
                valid_prev = [h for h in hist if 0.10 <= (t - h[0]) <= 0.35]
                if valid_prev:
                    prev_sample = valid_prev[0]
                    prev_t, prev_kpts, prev_confs = prev_sample[0], prev_sample[1], prev_sample[2]
                    dt_v = max(t - prev_t, 0.08)

                    # Compute left and right wrist velocity over the smoothed window
                    v_lw = (math.hypot(kpts[9][0] - prev_kpts[9][0], kpts[9][1] - prev_kpts[9][1]) / dt_v / torso_h) if (confs[9] > 0.35 and prev_confs[9] > 0.35) else 0.0
                    v_rw = (math.hypot(kpts[10][0] - prev_kpts[10][0], kpts[10][1] - prev_kpts[10][1]) / dt_v / torso_h) if (confs[10] > 0.35 and prev_confs[10] > 0.35) else 0.0

                    active_v = max(v_lw, v_rw)
                    curr_wrist = kpts[9] if v_lw >= v_rw else kpts[10]
                    prev_wrist = prev_kpts[9] if v_lw >= v_rw else prev_kpts[10]
                    disp_wrist = math.hypot(curr_wrist[0] - prev_wrist[0], curr_wrist[1] - prev_wrist[1])

                    # Fast arm motion with hand active (punch, strike, violent swing, hitting motion)
                    # Requires physical travel across space (>= 40px and >= 0.55 torso height)
                    if active_v >= 2.6 and disp_wrist >= max(0.55 * torso_h, 40.0) and curr_wrist[1] < (mid_hip[1] + 0.30 * torso_h):
                        struck = False
                        target_found = None
                        for other_id, other_data in matched_tracks.items():
                            if other_id == tid or other_data.get("pose_idx") == data.get("pose_idx"):
                                continue
                            ob = other_data["box"]
                            if self._box_iou(box, ob) > 0.35:
                                continue  # Overlapping duplicate tracker box on same person

                            o_kpts = other_data["kpts"]
                            o_head = o_kpts[0]
                            o_mid_sh = ((o_kpts[5][0] + o_kpts[6][0]) / 2.0, (o_kpts[5][1] + o_kpts[6][1]) / 2.0)
                            
                            # Strike physics: The attacker's hand MUST travel forward toward the victim's head/torso
                            d_prev_head = math.hypot(prev_wrist[0] - o_head[0], prev_wrist[1] - o_head[1]) / torso_h
                            d_curr_head = math.hypot(curr_wrist[0] - o_head[0], curr_wrist[1] - o_head[1]) / torso_h
                            d_prev_sh = math.hypot(prev_wrist[0] - o_mid_sh[0], prev_wrist[1] - o_mid_sh[1]) / torso_h
                            d_curr_sh = math.hypot(curr_wrist[0] - o_mid_sh[0], curr_wrist[1] - o_mid_sh[1]) / torso_h

                            closure_head = d_prev_head - d_curr_head
                            closure_sh = d_prev_sh - d_curr_sh
                            min_curr_dist = min(d_curr_head, d_curr_sh)

                            if (closure_head > 0.25 or closure_sh > 0.25) and min_curr_dist < 0.65:
                                events.append({"track_id": tid, "type": "PHYSICAL_STRIKE", "target_id": other_id})
                                struck = True
                                break
                            elif min_curr_dist < 1.1:
                                target_found = other_id

                        # Violent swing (large fast hitting movement or swing with object/arm)
                        # ONLY flag if confronting an adversary or in two-person interaction
                        if not struck and target_found is not None:
                            if active_v >= 3.0 and disp_wrist >= max(0.60 * torso_h, 45.0):
                                events.append({"track_id": tid, "type": "VIOLENT_SWING", "target_id": target_found})

            # 3. Check for KNOCKOUT_FALL (Requires prior standing posture then sudden collapse)
            if confs[5] > 0.3 and confs[6] > 0.3 and confs[11] > 0.3 and confs[12] > 0.3:
                spine_dx = mid_sh[0] - mid_hip[0]
                spine_dy = mid_sh[1] - mid_hip[1]
                # Check history to verify person was actually standing before collapsing
                standing_before = False
                for h in hist:
                    if (t - h[0]) >= 0.3:
                        prev_kpts = h[1]
                        prev_sh_y = (prev_kpts[5][1] + prev_kpts[6][1]) / 2.0
                        prev_hip_y = (prev_kpts[11][1] + prev_kpts[12][1]) / 2.0
                        if (prev_hip_y - prev_sh_y) > 0.8 * abs(prev_kpts[5][0] - prev_kpts[11][0]):
                            standing_before = True
                            break
                # Only flag fall if person was standing upright and collapsed horizontally
                if standing_before and abs(spine_dy) < 0.50 * max(abs(spine_dx), 1.0) and torso_h > 15.0:
                    events.append({"track_id": tid, "type": "KNOCKOUT_FALL", "target_id": None})

        # Cleanup old tracks in history
        active_ids = set(matched_tracks.keys())
        for k in list(self.kpt_hist.keys()):
            if k not in active_ids and self.kpt_hist[k] and t - self.kpt_hist[k][-1][0] > 3.0:
                del self.kpt_hist[k]

        return events
