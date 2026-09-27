"""Camera-integrity monitor: blur/defocus, covered/blinded lens, view shift. Bypasses the alert budget."""
import cv2, numpy as np

class TamperMonitor:
    def __init__(s, every=5, need=3, shift_frac=0.06):
        s.every, s.need, s.sf, s.n = every, need, shift_frac, 0
        s.base_sharp = None; s.ref = None; s.cnt = {"BLURRED": 0, "COVERED": 0, "MOVED": 0}; s.active = set()
    def update(s, t, frame):
        s.n += 1
        if s.n % s.every: return []
        g = cv2.cvtColor(cv2.resize(frame, (320, int(frame.shape[0] * 320 / frame.shape[1]))), cv2.COLOR_BGR2GRAY)
        sharp = cv2.Laplacian(g, cv2.CV_64F).var(); flags = set()
        if g.mean() < 12 or g.std() < 5: flags.add("COVERED")
        elif s.base_sharp is not None and sharp < 0.2 * s.base_sharp: flags.add("BLURRED")
        gf = np.float32(g)
        if s.ref is None: s.ref = gf
        elif "COVERED" not in flags:
            (dx, dy), resp = cv2.phaseCorrelate(s.ref, gf)
            if resp > 0.05 and max(abs(dx), abs(dy)) > s.sf * 320: flags.add("MOVED")
        if not flags:
            s.base_sharp = sharp if s.base_sharp is None else 0.95 * s.base_sharp + 0.05 * sharp
        out = []
        for k in s.cnt:
            s.cnt[k] = s.cnt[k] + 1 if k in flags else 0
            if s.cnt[k] == s.need and k not in s.active:
                s.active.add(k); out.append(dict(id=f"tamper-{k}-{int(t * 1000)}", type="TAMPER", kind=k, t=round(t, 2),
                                                 status="CRITICAL_SYSTEM_ALERT", score=999, entity="camera", reasons=[k], types=[k], box=None, zone=None))
            if s.cnt[k] == 0: s.active.discard(k)
        return out
