"""Track-level risk accumulation with alert budget (Risk-Based Alerting adapted from SOC practice)."""
import math, json, os, datetime as dt
from collections import defaultdict, deque
import numpy as np, cv2

BASE_W = {"ZONE_ENTER": 35, "ZONE_DWELL": 10, "LOITER": 15, "RUNNING": 10, "UNATTENDED": 45, "GAP_DWELL": 20, "ATYPICAL_PATH": 8, "RARE_DWELL": 12}
OBJ = {"backpack", "handbag", "suitcase"}
GROUP = {"ZONE_ENTER": "zone", "ZONE_DWELL": "zone", "LOITER": "loiter", "RUNNING": "motion", "UNATTENDED": "object", "GAP_DWELL": "gap", "ATYPICAL_PATH": "path", "RARE_DWELL": "path"}
P = dict(tau=30, thr=60, alert_budget_per_hour=6, cooldown=60, loiter_s=10, loiter_frac=0.5, run_hps=1.5, dwell_s=5,
         stat_s=8, away_s=8, emit_gap=2, night=[22, 6], night_mult=1.5, start="2026-01-01T12:00:00", div_bonus=0.4, min_groups=2)

class RiskEngine:
    def __init__(s, cfg, fps=25.0, weights_path=None):
        s.cam = cfg.get("camera_id", "cam1"); s.fps = fps
        s.p = {**P, **cfg.get("params", {})}
        bad = set(cfg.get("params", {})) - set(P)
        if bad: raise ValueError(f"unknown params (typo?): {bad}")
        s.zones = [dict(name=n, poly=np.array(z["poly"], np.int32), crit=z.get("crit", 1.0),
                        restricted=z.get("restricted", True)) for n, z in cfg.get("zones", {}).items()]
        s.events = defaultdict(list); s.hist = defaultdict(deque); s.zstate = {}; s.last_emit = {}
        s.ost = {}; s.atimes = deque(); s.alerted = {}; s.lastbox = {}; s.touched = set()
        s.scale = {}; s.wpath = weights_path; s._wm = 0; s._wcheck = -1e9
        
        s.heatmap_size = (36, 64) # Grid size (H, W) for 640x360 scaled down by 10
        s.dwell_heatmap = np.ones(s.heatmap_size, dtype=np.float32)
        s.path_heatmap = np.ones(s.heatmap_size, dtype=np.float32)
        s.heat_frames = 0
    # ---- helpers
    def _zone(s, pt):
        for z in s.zones:
            if cv2.pointPolygonTest(z["poly"], (float(pt[0]), float(pt[1])), False) >= 0: return z
        return None
    def _tprior(s, t):
        h = (dt.datetime.fromisoformat(s.p["start"]) + dt.timedelta(seconds=t)).hour
        a, b = s.p["night"]
        return s.p["night_mult"] if (h >= a or h < b) else 1.0
    def _reload(s, t):
        if not s.wpath or t - s._wcheck < 5: return
        s._wcheck = t
        try:
            m = os.path.getmtime(s.wpath)
            if m != s._wm: s._wm = m; s.scale = json.load(open(s.wpath)).get("scale", {})
        except Exception: pass
    def emit(s, key, ty, t, zone=None, throttle=True):
        last = s.last_emit.get((key, ty))
        if throttle and last is not None and t - last < s.p["emit_gap"]: return
        s.last_emit[(key, ty)] = t
        w = BASE_W[ty] * s.scale.get(ty, 1.0) * (zone["crit"] if zone else 1.0) * s._tprior(t)
        s.events[key].append((t, ty, w, zone["name"] if zone else None)); s.touched.add(key)
    def score(s, key, t):
        sc, types = 0.0, set()
        for (te, ty, w, _) in s.events.get(key, []):
            d = w * math.exp(-(t - te) / s.p["tau"]); sc += d
            if d > 2: types.add(ty)
        return sc * (1 + s.p["div_bonus"] * max(len({GROUP[x] for x in types}) - 1, 0)), types
    def merge(s, old, new):
        s.events[new] += s.events.pop(old, []); s.touched.add(new)
    # ---- main
    def update(s, t, tracks):
        s._reload(t); s.touched = set(); p = s.p
        s.heat_frames += 1
        persons = [x for x in tracks if x["cls"] == "person"]
        for x in persons:
            key = f"{s.cam}:P{x['id']}"; x1, y1, x2, y2 = x["box"]
            feet = ((x1 + x2) / 2, y2); h = max(y2 - y1, 1); s.lastbox[key] = x["box"]
            H = s.hist[key]; H.append((t, feet[0], feet[1], h))
            while len(H) > 1 and H[0][0] < t - 20: H.popleft()
            z = s._zone(feet); zn = z["name"] if z and z["restricted"] else None
            zs = s.zstate.get(key, {})
            
            # Simple online heatmap model for Paths and Dwell
            grid_y, grid_x = min(s.heatmap_size[0]-1, int(feet[1]/10)), min(s.heatmap_size[1]-1, int(feet[0]/10))
            
            if zn and zs.get("zone") != zn:
                s.zstate[key] = {"zone": zn, "since": t, "last_in": t}; s.emit(key, "ZONE_ENTER", t, z, throttle=False)
            elif zn:
                zs["last_in"] = t
                if t - zs["since"] >= p["dwell_s"]: s.emit(key, "ZONE_DWELL", t, z)
            elif zs and t - zs.get("last_in", -1e9) > 1.5: s.zstate[key] = {}  # hysteresis vs. box jitter
            
            w = [q for q in H if q[0] >= t - p["loiter_s"]]
            is_dwelling = False
            if H[0][0] <= t - p["loiter_s"] * 0.9 and len(w) > 3:
                pts = np.array([[q[1], q[2]] for q in w]); mh = np.mean([q[3] for q in w])
                if np.abs(pts - pts.mean(0)).max() < p["loiter_frac"] * mh: 
                    s.emit(key, "LOITER", t, z)
                    is_dwelling = True
                    
            r = [q for q in H if q[0] >= t - 1.0]
            is_running = False
            if len(r) > 2 and r[-1][0] - r[0][0] >= 0.6:
                d = math.hypot(r[-1][1] - r[0][1], r[-1][2] - r[0][2]) / (r[-1][0] - r[0][0]) / np.mean([q[3] for q in r])
                if d > p["run_hps"]: 
                    s.emit(key, "RUNNING", t, z)
                    is_running = True
            
            # Heatmap update and rare event checks
            s.path_heatmap[grid_y, grid_x] += 1
            if is_dwelling:
                s.dwell_heatmap[grid_y, grid_x] += 1
                
            # If we've observed enough frames, evaluate rarity
            if s.heat_frames > 500:
                if not is_dwelling and not is_running:
                    # Normal walking path rarity
                    path_prob = s.path_heatmap[grid_y, grid_x] / s.path_heatmap.max()
                    if path_prob < 0.05:
                        s.emit(key, "ATYPICAL_PATH", t, z)
                elif is_dwelling:
                    # Dwell rarity
                    dwell_prob = s.dwell_heatmap[grid_y, grid_x] / s.dwell_heatmap.max()
                    if dwell_prob < 0.05:
                        s.emit(key, "RARE_DWELL", t, z)
        for o in [x for x in tracks if x["cls"] in OBJ]:
            key = f"{s.cam}:O{o['id']}"; x1, y1, x2, y2 = o["box"]; c = ((x1 + x2) / 2, (y1 + y2) / 2)
            size = max(x2 - x1, y2 - y1); s.lastbox[key] = o["box"]
            st = s.ost.setdefault(key, dict(anchor=c, t0=t, near=t))
            if math.dist(c, st["anchor"]) > max(20, 0.6 * size): st["anchor"] = c; st["t0"] = t
            for q in persons:
                a, b, cc, d = q["box"]
                if math.dist(c, ((a + cc) / 2, (b + d) / 2)) < 1.0 * (d - b): st["near"] = t; break
            if t - st["t0"] >= p["stat_s"] and t - st["near"] >= p["away_s"]:
                s.emit(key, "UNATTENDED", t, s._zone(c))
        out = []
        for key in s.touched:
            s.events[key] = [e for e in s.events[key] if t - e[0] < 5 * p["tau"]]
            sc, types = s.score(key, t)
            groups = {GROUP[x] for x in types}
            strong = sc >= 2.0 * p["thr"] or "object" in groups  # abandoned object is a self-contained episode
            if sc < p["thr"] or t - s.alerted.get(key, -1e9) < p["cooldown"]: continue
            if len(groups) < p["min_groups"] and not strong: continue  # one weak signal type never alerts alone
            while s.atimes and s.atimes[0] < t - 3600: s.atimes.popleft()
            if len(s.atimes) < p["alert_budget_per_hour"]: status = "PENDING_CONFIRMATION"; s.atimes.append(t)
            elif sc >= 2.5 * p["thr"]: status = "PENDING_CONFIRMATION"; s.atimes.append(t)  # critical override only
            else: status = "SUPPRESSED_BY_BUDGET"
            s.alerted[key] = t
            cnt = defaultdict(int)
            for e in s.events[key]: cnt[e[1]] += 1
            out.append(dict(id=f"{s.cam}-{int(t * 1000)}-{key.split(':')[1]}", camera=s.cam, t=round(t, 2), entity=key,
                            score=round(sc, 1), severity=round(sc / p["thr"], 2), status=status, types=sorted(types),
                            reasons=[f"{k} x{v}" for k, v in sorted(cnt.items())], box=s.lastbox.get(key),
                            zone=next((e[3] for e in reversed(s.events[key]) if e[3]), None)))
        return sorted(out, key=lambda a: -a["score"])
