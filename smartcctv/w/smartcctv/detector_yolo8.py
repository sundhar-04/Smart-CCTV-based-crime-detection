"""YOLOv8 detector backend with Stage 2 high-res crop verification.
Matches the exact Detector call signature: __call__(frame) -> [(x1, y1, x2, y2, conf, name)]
"""
import numpy as np

try:
    import torch
    from ultralytics import YOLO
    _HAS_YOLO8 = True
except ImportError:
    _HAS_YOLO8 = False

# COCO Class IDs: person (0), backpack (24), handbag (26), suitcase (28), knife (43)
KEEP_COCO_IDS = [0, 24, 26, 28, 43]
KEEP_NAMES = {"person", "backpack", "handbag", "suitcase", "knife"}

class YoloDetector:
    """YOLOv8 Detector backend with automatic device selection and Stage 2 crop verification."""
    def __init__(self, weights="yolov8n.pt", imgsz=640, conf=0.25, verify_hi=0.5, device=None, keep=KEEP_NAMES):
        if not _HAS_YOLO8:
            raise ImportError("ultralytics/torch is required for YoloDetector. Install with `pip install ultralytics`")
        
        if device is None:
            device = "cuda:0" if (torch.cuda.is_available()) else "cpu"
        
        self.device = device
        self.imgsz = imgsz
        self.conf = conf
        self.hi = verify_hi
        self.keep = set(keep)
        self.m = YOLO(weights)
        self.names = list(self.m.names.values()) if isinstance(self.m.names, dict) else list(self.m.names)
        self.calls = 0
        self.verify_calls = 0

    def _raw(self, img, conf, imgsz=None):
        imgsz = imgsz or self.imgsz
        res = self.m(img, imgsz=imgsz, conf=conf, device=self.device, verbose=False)[0]
        if res.boxes is None or len(res.boxes) == 0:
            return []
        
        boxes = res.boxes.xyxy.cpu().numpy()
        confs = res.boxes.conf.cpu().numpy()
        clses = res.boxes.cls.cpu().numpy().astype(int)
        
        out = []
        for (x1, y1, x2, y2), c, k in zip(boxes, confs, clses):
            name = self.m.names[k]
            if name in self.keep:
                out.append((float(x1), float(y1), float(x2), float(y2), float(c), str(name)))
        return out

    def __call__(self, frame):
        self.calls += 1
        out = []
        H, W = frame.shape[:2]
        
        raw_dets = self._raw(frame, self.conf)
        for (x1, y1, x2, y2, c, n) in raw_dets:
            if c >= self.hi:
                out.append((x1, y1, x2, y2, c, n))
                continue
            
            # Stage 2: Uncertain detection -> re-run on a padded full-resolution crop
            self.verify_calls += 1
            pw, ph = int(0.3 * (x2 - x1)), int(0.3 * (y2 - y1))
            cx1, cy1 = max(0, int(x1 - pw)), max(0, int(y1 - ph))
            cx2, cy2 = min(W, int(x2 + pw)), min(H, int(y2 + ph))
            crop = frame[cy1:cy2, cx1:cx2]
            
            if crop.size == 0:
                continue
                
            verified = False
            for (a, b, c2, d, cc, nn) in self._raw(crop, 0.4, imgsz=max(self.imgsz, 640)):
                if nn == n:
                    out.append((a + cx1, b + cy1, c2 + cx1, d + cy1, max(c, cc), n))
                    verified = True
                    break
            
            # If verification crop didn't match, still retain original if confidence was moderately close
            if not verified and c >= (self.conf + 0.05):
                out.append((x1, y1, x2, y2, c, n))
                
        return out
