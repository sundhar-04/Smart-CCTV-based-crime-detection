"""Stage 0 motion gate + Stage 1 coarse detector + Stage 2 full-res crop verification."""
import cv2, numpy as np
KEEP = ("person", "backpack", "handbag", "suitcase", "knife")

class MotionGate:
    """Cheap always-on gate on a tiny frame. Sweeps every N frames so static objects still get seen."""
    def __init__(s, width=160, min_ratio=0.002, sweep_every=15, regions=None):
        s.w, s.min_ratio, s.sweep, s.n = width, min_ratio, sweep_every, 0
        s.bg = cv2.createBackgroundSubtractorMOG2(history=300, varThreshold=25, detectShadows=True)
        s.regions = regions
        s.mask = None
        
    def __call__(s, frame):
        h, w = frame.shape[:2]
        small = cv2.resize(frame, (s.w, int(h * s.w / w)), interpolation=cv2.INTER_AREA)
        
        if s.regions and s.mask is None:
            s.mask = np.zeros((small.shape[0], small.shape[1]), dtype=np.uint8)
            for r in s.regions:
                poly = (np.array(r["poly"], np.float32) * (s.w / w)).astype(np.int32)
                cv2.fillPoly(s.mask, [poly], 255)
                
        fg = s.bg.apply(small)
        if s.mask is not None:
            fg = cv2.bitwise_and(fg, fg, mask=s.mask)
            
        s.n += 1
        return (fg > 200).mean() >= s.min_ratio or s.n % s.sweep == 0 or s.n < 10

class Detector:
    """OpenCV-DNN Darknet backend (works without PyTorch). Same call signature as a YOLOv8 wrapper:
    __call__(frame) -> [(x1,y1,x2,y2,conf,name)]"""
    def __init__(s, model_dir="models", size=320, conf=0.25, nms=0.4, verify_hi=0.5, keep=KEEP):
        net = cv2.dnn.readNetFromDarknet(f"{model_dir}/yolov4-tiny.cfg", f"{model_dir}/yolov4-tiny.weights")
        s.m = cv2.dnn_DetectionModel(net)
        s.m.setInputParams(size=(size, size), scale=1 / 255.0, swapRB=True)
        s.names = open(f"{model_dir}/coco.names").read().split("\n")
        s.conf, s.nms, s.hi, s.keep = conf, nms, verify_hi, set(keep)
        s.calls = s.verify_calls = 0
    def _raw(s, img, conf):
        ids, sc, bx = s.m.detect(img, conf, s.nms)
        if len(ids) == 0: return []
        return [(int(x), int(y), int(x + w), int(y + h), float(c), s.names[int(i)])
                for i, c, (x, y, w, h) in zip(np.array(ids).flatten(), np.array(sc).flatten(), bx)
                if s.names[int(i)] in s.keep]
    def __call__(s, frame):
        s.calls += 1
        out = []
        H, W = frame.shape[:2]
        for (x1, y1, x2, y2, c, n) in s._raw(frame, s.conf):
            if c >= s.hi: out.append((x1, y1, x2, y2, c, n)); continue
            # Stage 2: uncertain -> re-run on a padded FULL-RES crop (real pixels, no interpolation guesswork)
            s.verify_calls += 1
            pw, ph = int(0.3 * (x2 - x1)), int(0.3 * (y2 - y1))
            cx1, cy1, cx2, cy2 = max(0, x1 - pw), max(0, y1 - ph), min(W, x2 + pw), min(H, y2 + ph)
            for (a, b, c2, d, cc, nn) in s._raw(frame[cy1:cy2, cx1:cx2], 0.4):
                if nn == n: out.append((a + cx1, b + cy1, c2 + cx1, d + cy1, max(c, cc), n)); break
        return out
