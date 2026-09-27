"""Cross-camera identity linking and intra-camera track repair through blind spots:
Appearance embedding + Transit-time topology prior + Bayesian posterior estimation.
"""
import math, random, cv2, numpy as np

try:
    import torch
    from boxmot.appearance.reid_model_factory import get_model
    _REID_MODEL = get_model("osnet_x0_25", "cuda:0" if torch.cuda.is_available() else "cpu")
    _REID_MODEL.eval()
    _HAS_BOXMOT = True
except ImportError:
    _HAS_BOXMOT = False

def embed(frame, box):
    """Extracts a normalized upper/lower body feature representation with color and gradient cues,
    or a deep OSNet embedding if boxmot is installed."""
    x1, y1, x2, y2 = [max(0, int(v)) for v in box]
    c = frame[y1:y2, x1:x2]
    if c.size == 0:
        return np.zeros(96 if not _HAS_BOXMOT else 512, dtype=np.float32)
    
    if _HAS_BOXMOT:
        # OSNet expects RGB input, typically resized to 256x128
        img = cv2.cvtColor(c, cv2.COLOR_BGR2RGB)
        img = cv2.resize(img, (128, 256))
        # Convert to tensor and normalize (standard ImageNet normalization or similar)
        # boxmot's get_model usually returns a model that takes (B, C, H, W) normalized
        img = img.transpose(2, 0, 1).astype(np.float32) / 255.0
        img = np.expand_dims(img, 0)
        with torch.no_grad():
            tensor = torch.from_numpy(img).to(_REID_MODEL.device)
            feat = _REID_MODEL(tensor)
            feat = feat.cpu().numpy()[0]
        # Normalize the embedding
        norm = np.linalg.norm(feat)
        return (feat / norm) if norm > 1e-9 else feat

    hh = max(1, c.shape[0] // 2)
    parts = []
    for part in (c[:hh], c[hh:]):
        if part.size == 0:
            parts.append(np.zeros(48, dtype=np.float32))
            continue
        hsv = cv2.cvtColor(part, cv2.COLOR_BGR2HSV)
        hist = cv2.calcHist([hsv], [0, 1], None, [12, 4], [0, 180, 0, 256]).flatten()
        norm = hist.sum() + 1e-9
        parts.append((hist / norm).astype(np.float32))
    
    return np.concatenate(parts) / 2.0

def sim(a, b):
    """Computes similarity in [0, 1] across histogram and feature vector representations."""
    if a is None or b is None or len(a) == 0 or len(b) == 0:
        return 0.0
    na = np.linalg.norm(a)
    nb = np.linalg.norm(b)
    cos = float(np.dot(a, b) / (na * nb)) if (na > 1e-9 and nb > 1e-9) else 0.0
    bhat = float(np.sqrt(np.maximum(0, a * b)).sum())
    return max(0.0, min(1.0, max(cos, bhat)))

class LocalTrackReID:
    """Intra-camera ID repair to prevent risk splitting during brief tracker occlusions."""
    def __init__(self, max_gap_s=4.0, sim_thr=0.75):
        self.max_gap = max_gap_s
        self.sim_thr = sim_thr
        self.recent_lost = {}  # tid -> (t_lost, emb, last_box)

    def on_lost(self, tid, t, emb, box):
        self.recent_lost[tid] = (t, emb, box)

    def match_new(self, t, emb, box):
        """Attempts to re-associate a newly appeared track with a recently lost track."""
        stale = [k for k, (tl, _, _) in self.recent_lost.items() if t - tl > self.max_gap]
        for k in stale:
            del self.recent_lost[k]

        best_tid, best_s = None, 0.0
        for tid, (tl, old_emb, old_box) in self.recent_lost.items():
            s = sim(emb, old_emb)
            if s > self.sim_thr and s > best_s:
                best_s = s
                best_tid = tid

        if best_tid is not None:
            del self.recent_lost[best_tid]
            return best_tid, best_s
        return None, 0.0

class CrossCam:
    """Bayesian cross-camera tracking over non-overlapping blind spots with travel-time topology."""
    def __init__(self, edges=None, use_topology=True, new_prior=0.15, alpha=4.0, rng=None):
        self.edges = edges or {}  # (cam_from, cam_to) -> (mu_seconds, sigma_seconds)
        self.topo = use_topology
        self.new_prior = new_prior
        self.alpha = alpha
        self.ghosts = []
        self.next = 0
        self.rng = rng or random.Random(0)
        self.transit_history = []

    def on_exit(self, gid, cam, t, emb):
        """Register a track exiting camera coverage into the blind spot."""
        self.ghosts.append(dict(gid=gid, cam=cam, t=t, emb=emb))

    def _gid(self):
        self.next += 1
        return f"G{self.next}"

    def on_appear(self, cam, t, emb):
        """Matches a new appearance to blind-spot ghosts. Returns (global_id, posterior, gap_event_or_None)."""
        liks = []
        for g in self.ghosts:
            if g["cam"] == cam:
                liks.append(0.0)
                continue
            
            # Appearance likelihood
            a = sim(g["emb"], emb) ** self.alpha
            
            # Topological transit-time prior
            if self.topo:
                mu, sg = self.edges.get((g["cam"], cam), (None, None))
                if mu is not None and sg is not None:
                    tt = t - g["t"]
                    a *= math.exp(-0.5 * ((tt - mu) / sg) ** 2)
                else:
                    a *= 0.02
            liks.append(a)

        Z = sum(liks) + self.new_prior
        if not liks or max(liks) == 0:
            return self._gid(), 0.0, None

        best = max(liks)
        cands = [i for i, l in enumerate(liks) if abs(l - best) < 1e-9]
        i = self.rng.choice(cands)
        post = liks[i] / Z

        if post < 0.4:
            return self._gid(), post, None

        g = self.ghosts.pop(i)
        gap = None
        mu, sg = self.edges.get((g["cam"], cam), (None, None))
        if mu is not None and sg is not None:
            dt = t - g["t"]
            z = (dt - mu) / sg
            self.transit_history.append((g["cam"], cam, dt))
            # If excessive dwell in blind spot -> trigger GAP_DWELL anomaly
            if z > 2.0:
                gap = dict(
                    type="GAP_DWELL",
                    w_scale=min(z / 2.0, 3.0),
                    gid=g["gid"],
                    excess_s=round(dt - mu, 1)
                )

        return g["gid"], post, gap

    def belief(self, gid, t):
        """Returns P(next_camera) for an unaccounted subject currently in transit."""
        g = next((g for g in self.ghosts if g["gid"] == gid), None)
        if not g:
            return {}
        sc = {}
        for (a, b), (mu, sg) in self.edges.items():
            if a != g["cam"]:
                continue
            tt = t - g["t"]
            sc[b] = 0.5 * math.erfc((tt - mu) / (sg * math.sqrt(2))) + 0.05
        Z = sum(sc.values()) or 1
        return {k: round(v / Z, 3) for k, v in sc.items()}

    def calibrate_topology(self, min_samples=3):
        """Learn transit time distributions (mu, sigma) from verified historical transitions."""
        by_edge = {}
        for c1, c2, dt in self.transit_history:
            by_edge.setdefault((c1, c2), []).append(dt)
        for edge, samples in by_edge.items():
            if len(samples) >= min_samples:
                mu = float(np.mean(samples))
                sg = float(max(1.0, np.std(samples)))
                self.edges[edge] = (round(mu, 1), round(sg, 1))
