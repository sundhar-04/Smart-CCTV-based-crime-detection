"""Ring buffer of full-res JPEG frames, evidence clips, best-shot crops, and a tamper-evident cryptographic hash chain."""
import cv2, os, json, hashlib, hmac, numpy as np
from collections import deque

DEFAULT_SECRET = os.getenv("SMARTCCTV_CHAIN_SECRET", "smartcctv-audit-secret-key-2026")

class Chain:
    def __init__(self, path, secret=DEFAULT_SECRET):
        self.path = path
        self.secret = secret.encode() if isinstance(secret, str) else secret
        self.last = "0" * 64
        if os.path.exists(path):
            lines = open(path, encoding="utf-8").read().strip().split("\n")
            if lines and lines[-1]:
                try:
                    self.last = json.loads(lines[-1])["hash"]
                except Exception:
                    pass

    @staticmethod
    def _h(prev, payload, secret=None):
        raw = (prev + json.dumps(payload, sort_keys=True)).encode()
        if secret:
            return hmac.new(secret, raw, hashlib.sha256).hexdigest()
        return hashlib.sha256(raw).hexdigest()

    def append(self, payload):
        rec = {
            "prev": self.last,
            "payload": payload,
            "hash": Chain._h(self.last, payload, self.secret)
        }
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
        self.last = rec["hash"]

    @staticmethod
    def verify(path, secret=DEFAULT_SECRET):
        sec = secret.encode() if isinstance(secret, str) and secret else secret
        prev, n = "0" * 64, 0
        if not os.path.exists(path):
            return True, 0, None
        for i, l in enumerate(open(path, encoding="utf-8").read().strip().split("\n")):
            if not l:
                continue
            r = json.loads(l)
            expected_hmac = Chain._h(prev, r["payload"], sec)
            expected_sha = Chain._h(prev, r["payload"], None)
            if r["prev"] != prev or (r["hash"] != expected_hmac and r["hash"] != expected_sha):
                return False, n, i
            prev, n = r["hash"], n + 1
        return True, n, None

def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()

def create_video_writer(filepath, fps, size):
    """Creates a VideoWriter for evidence / annotated output video."""
    return cv2.VideoWriter(filepath, cv2.VideoWriter_fourcc(*"mp4v"), fps, size)

class Evidence:
    def __init__(self, out, fps, pre=5.0, post=3.0, meta=None):
        self.out, self.fps, self.pre, self.post = out, fps, pre, post
        self.meta = meta or {}
        os.makedirs(f"{out}/clips", exist_ok=True)
        self.ring = deque(maxlen=int(fps * (pre + 1)))
        self.pending = []
        self.best = {}
        self.chain = Chain(f"{out}/alerts.chain.jsonl")

    def push(self, t, frame):
        b = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])[1].tobytes()
        self.ring.append((t, b))
        for p in self.pending:
            p["frames"].append(b)
        for p in [p for p in self.pending if t >= p["until"]]:
            self._finalize(p)
            self.pending.remove(p)

    def best_shot(self, key, frame, box):
        x1, y1, x2, y2 = [max(0, int(v)) for v in box]
        c = frame[y1:y2, x1:x2]
        if c.size == 0:
            return
        q = cv2.Laplacian(cv2.cvtColor(c, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var() * np.sqrt(c.shape[0] * c.shape[1])
        if key not in self.best or q > self.best[key][0]:
            self.best[key] = (q, cv2.imencode(".jpg", c)[1].tobytes())

    def start(self, alert):
        self.pending.append(dict(
            alert=alert,
            until=alert["t"] + self.post,
            frames=[b for (t, b) in self.ring if t >= (alert["t"] - self.pre)]
        ))

    def flush(self):
        for p in self.pending:
            self._finalize(p)
        self.pending = []

    def _finalize(self, p):
        a = p["alert"]
        base = f"{self.out}/clips/{a['id']}"
        imgs = [cv2.imdecode(np.frombuffer(b, np.uint8), 1) for b in p["frames"]]
        if not imgs:
            return
        h, w = imgs[0].shape[:2]
        vw = create_video_writer(base + ".mp4", self.fps, (w, h))
        for im in imgs:
            vw.write(im)
        vw.release()
        
        a["clip"] = os.path.basename(base) + ".mp4"
        a["clip_sha256"] = sha256_file(base + ".mp4")
        if self.meta:
            a["meta"] = self.meta
        if a.get("entity") in self.best:
            open(base + "_best.jpg", "wb").write(self.best[a["entity"]][1])
            a["best_shot"] = os.path.basename(base) + "_best.jpg"
        self.chain.append(a)
