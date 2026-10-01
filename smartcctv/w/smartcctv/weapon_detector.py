"""Dedicated Weapon and Firearm Detector using trained YOLO models:
- best.pt (Firearm / Gun detector)
- best (3).pt (General Weapon detector)
"""
import os, math
from collections import defaultdict
import numpy as np

try:
    import torch
    from ultralytics import YOLO
    _HAS_YOLO = True
except ImportError:
    _HAS_YOLO = False

class WeaponDetector:
    """Cascade detector combining dedicated firearm (Gun) and multi-class weapon models."""
    def __init__(self,
                 gun_weights=r"d:\Doom\best.pt",
                 weapon_weights=r"d:\Doom\best (3).pt",
                 conf_gun=0.60,
                 conf_weapon=0.65,
                 device=None):
        if not _HAS_YOLO:
            raise ImportError("ultralytics and torch are required for WeaponDetector.")
        
        if device is None:
            device = "cuda:0" if (torch.cuda.is_available()) else "cpu"
        self.device = device
        self.conf_gun = conf_gun
        self.conf_weapon = conf_weapon

        self.person_hits = defaultdict(int)
        self.person_last_t = defaultdict(float)

        # Resolve weights with fallback to repository models directory
        models_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "models"))
        if not os.path.exists(gun_weights):
            local_gun = os.path.join(models_dir, "best.pt")
            if os.path.exists(local_gun):
                gun_weights = local_gun
        if not os.path.exists(weapon_weights):
            local_weapon = os.path.join(models_dir, "best (3).pt")
            if os.path.exists(local_weapon):
                weapon_weights = local_weapon

        self.gun_model = None
        if os.path.exists(gun_weights):
            try:
                self.gun_model = YOLO(gun_weights)
            except Exception as e:
                print(f"[WeaponDetector] Warning: failed to load gun model from {gun_weights}: {e}")

        self.weapon_model = None
        if os.path.exists(weapon_weights):
            try:
                self.weapon_model = YOLO(weapon_weights)
            except Exception as e:
                print(f"[WeaponDetector] Warning: failed to load weapon model from {weapon_weights}: {e}")

    def detect(self, frame, persons=None, t=0.0):
        """Run full-frame weapon inference and associate verified weapons with nearby individuals.
        Returns: list of dicts: [{'box': (x1, y1, x2, y2), 'conf': float, 'cls': 'Gun'|'Weapon', 'person_id': int}]
        """
        if not persons:
            return []

        detections = []

        # 1. Gun Model Inference
        if self.gun_model is not None:
            res_g = self.gun_model(frame, imgsz=640, conf=self.conf_gun, device=self.device, verbose=False)[0]
            if res_g.boxes is not None and len(res_g.boxes) > 0:
                for b, c in zip(res_g.boxes.xyxy.cpu().numpy(), res_g.boxes.conf.cpu().numpy()):
                    detections.append({
                        "box": (float(b[0]), float(b[1]), float(b[2]), float(b[3])),
                        "conf": float(c),
                        "cls": "Gun"
                    })

        # 2. General Weapon Model Inference
        if self.weapon_model is not None:
            res_w = self.weapon_model(frame, imgsz=640, conf=self.conf_weapon, device=self.device, verbose=False)[0]
            if res_w.boxes is not None and len(res_w.boxes) > 0:
                for b, c in zip(res_w.boxes.xyxy.cpu().numpy(), res_w.boxes.conf.cpu().numpy()):
                    wx1, wy1, wx2, wy2 = b
                    is_dup = False
                    for prev in detections:
                        px1, py1, px2, py2 = prev["box"]
                        dx = min(wx2, px2) - max(wx1, px1)
                        dy = min(wy2, py2) - max(wy1, py1)
                        if dx > 0 and dy > 0:
                            inter = dx * dy
                            min_a = min((wx2-wx1)*(wy2-wy1), (px2-px1)*(py2-py1))
                            if inter / max(min_a, 1.0) > 0.5:
                                is_dup = True
                                break
                    if not is_dup:
                        detections.append({
                            "box": (float(b[0]), float(b[1]), float(b[2]), float(b[3])),
                            "conf": float(c),
                            "cls": "Weapon"
                        })

        # Only keep detections held by or on a tracked person
        matched = []
        for det in detections:
            wb = det["box"]
            wc = ((wb[0] + wb[2]) / 2.0, (wb[1] + wb[3]) / 2.0)
            ww = max(wb[2] - wb[0], 1.0)
            wh = max(wb[3] - wb[1], 1.0)
            wa = ww * wh

            for p in persons:
                pb = p["box"]
                pw = max(pb[2] - pb[0], 1.0)
                ph = max(pb[3] - pb[1], 1.0)
                pa = max(pw * ph, 1.0)

                # A handheld weapon (gun, knife) cannot exceed 20% of person area or 35% of person height
                if (wa / pa > 0.20) or (wh > 0.35 * ph) or (ww > 0.45 * pw):
                    continue  # Human body / torso / desk misdetection

                # Weapon must be held by the person (within or directly touching the body box)
                if (pb[0] - 0.15 * pw <= wc[0] <= pb[2] + 0.15 * pw) and (pb[1] - 0.10 * ph <= wc[1] <= pb[3] + 0.10 * ph):
                    det["person_id"] = p["id"]
                    matched.append(det)
                    break

        # Temporal persistence filter: weapon must be sustained across >= 2 detection frames within 1.5s
        verified_matched = []
        for det in matched:
            pid = det["person_id"]
            last_t = self.person_last_t[pid]
            if t - last_t <= 1.5:
                self.person_hits[pid] += 1
            else:
                self.person_hits[pid] = 1
            self.person_last_t[pid] = t
            # Verify on high confidence (>= 0.65) or on 2nd frame persistence
            if det["conf"] >= 0.65 or self.person_hits[pid] >= 2:
                verified_matched.append(det)

        return verified_matched
