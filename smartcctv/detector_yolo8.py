"""YOLOv8 detector wrapper matching the Detector interface from detector.py.

Output format: [(x1, y1, x2, y2, conf, name), ...]  same as original Detector.__call__.
KEEP IDs per COCO: person=0, backpack=24, handbag=26, suitcase=43, knife=35.
"""
from typing import List, Tuple
import numpy as np

KEEP = ("person", "backpack", "handbag", "suitcase", "knife")

# COCO ids for the KEEP classes (verified against YOLOv8 COCO names)
_COCO_MAP = {
    "person": 0,
    "backpack": 24,
    "handbag": 26,
    "suitcase": 43,
    "knife": 35,
}


class YoloDetector:
    """Wrapper around ultralytics YOLOv8 with the same __call__ signature as Detector."""
    def __init__(self, weights="yolov8n.pt", imgsz=320, conf=0.25, device=None):
        # Lazy import to avoid GUI dependencies at import time
        from ultralytics import YOLO
        self.m = YOLO(weights)
        self.imgsz = imgsz
        self.conf = conf
        self.device = device
        self.names = [self.m.names[i] for i in range(len(self.m.names))]
        self.calls = 0

    def __call__(self, frame) -> List[Tuple[float, float, float, float, float, str]]:
        """Return [(x1,y1,x2,y2,conf,name), ...] for kept classes only."""
        self.calls += 1
        # Run YOLOv8; classes= keeps only the COCO ids we want
        r = self.m(
            frame,
            imgsz=self.imgsz,
            conf=self.conf,
            classes=list(_COCO_MAP.values()),
            device=self.device,
            verbose=False,
        )[0]

        out = []
        for box, c, k in zip(r.boxes.xyxy.tolist(), r.boxes.conf.tolist(), r.boxes.cls.tolist()):
            name = self.m.names[int(k)]
            if name in KEEP:
                out.append((*map(float, box), float(c), name))
        return out
