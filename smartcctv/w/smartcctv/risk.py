"""Track-level risk accumulation with alert budget (Risk-Based Alerting adapted from SOC practice)."""
import math, json, os, datetime as dt
from collections import defaultdict, deque
import numpy as np, cv2

BASE_W = {
    "ZONE_ENTER": 35,
    "ZONE_DWELL": 10,
    "LOITER": 15,
    "RUNNING": 45,
    "SUDDEN_SPRINT": 65,
    "AGGRESSIVE_APPROACH": 65,
    "FIGHT_SUSPECTED": 65,
    "PHYSICAL_STRIKE": 85,
    "OVERHEAD_STANCE": 60,
    "VIOLENT_SWING": 70,
    "KNOCKOUT_FALL": 75,
    "PERSON_DOWN": 65,
    "UNATTENDED": 45,
    "GAP_DWELL": 20,
    "ATYPICAL_PATH": 8,
    "RARE_DWELL": 12,
    "WEAPON_NEAR_PERSON": 65,
}
OBJ = {"backpack", "handbag", "suitcase"}
WEAPON_CLS = {"knife", "baseball bat", "Gun", "gun", "Weapon", "weapon", "firearm", "pistol"}
GROUP = {
    "ZONE_ENTER": "zone",
    "ZONE_DWELL": "zone",
    "LOITER": "loiter",
    "RUNNING": "motion",
    "SUDDEN_SPRINT": "motion",
    "AGGRESSIVE_APPROACH": "motion",
    "FIGHT_SUSPECTED": "motion",
    "PHYSICAL_STRIKE": "violence",
    "OVERHEAD_STANCE": "violence",
    "VIOLENT_SWING": "violence",
    "KNOCKOUT_FALL": "violence",
    "PERSON_DOWN": "posture",
    "UNATTENDED": "object",
    "GAP_DWELL": "gap",
    "ATYPICAL_PATH": "path",
    "RARE_DWELL": "path",
    "WEAPON_NEAR_PERSON": "weapon",
}
P = dict(
    tau=30,
    thr=35,
    alert_budget_per_hour=1000,
    cooldown=4,
    loiter_s=10,
    loiter_frac=0.5,
    run_hps=0.35,
    dwell_s=5,
    stat_s=8,
    away_s=8,
    emit_gap=1.0,
    night=[22, 6],
    night_mult=1.5,
    start="2026-01-01T12:00:00",
    div_bonus=0.4,
    min_groups=2,
)

def classify_risk_level(score: float, types=None, reasons=None) -> str:
    """
    Classify incident threat level accurately:
    - CRITICAL: Direct life-threatening strikes (PHYSICAL_STRIKE, KNOCKOUT_FALL),
                or armed weapon brandished during a fight/swing, or score >= 350.
    - HIGH: Direct scuffle / active confrontation (FIGHT_SUSPECTED), VIOLENT_SWING,
            OVERHEAD_STANCE (confronting adversary), weapon with aggressive motion, or score >= 120.
    - ELEVATED: Warning indicators like isolated WEAPON_NEAR_PERSON alone, SUDDEN_SPRINT,
                RUNNING, AGGRESSIVE_APPROACH alone, or moderate composite score >= 45.
    - LOW: Sub-threshold or routine movement (score < 45).
    """
    all_signals = set()
    for t in (types or []):
        all_signals.add(str(t).strip().upper())
    for r in (reasons or []):
        parts = str(r).strip().split()
        if parts:
            all_signals.add(parts[0].upper())
        r_up = str(r).upper()
        for kw in [
            "KNOCKOUT_FALL", "PHYSICAL_STRIKE", "OVERHEAD_STANCE", "VIOLENT_SWING",
            "FIGHT_SUSPECTED", "WEAPON_NEAR_PERSON", "SUDDEN_SPRINT", "AGGRESSIVE_APPROACH", "RUNNING"
        ]:
            if kw in r_up:
                all_signals.add(kw)

    critical_strike_signals = {"KNOCKOUT_FALL", "PHYSICAL_STRIKE"}
    has_critical_strike = bool(all_signals & critical_strike_signals)
    has_violent_swing = bool(all_signals & {"VIOLENT_SWING", "OVERHEAD_STANCE"})
    has_fight = "FIGHT_SUSPECTED" in all_signals
    has_weapon = "WEAPON_NEAR_PERSON" in all_signals or "WEAPON" in all_signals
    has_motion = bool(all_signals & {"SUDDEN_SPRINT", "RUNNING", "AGGRESSIVE_APPROACH"})

    # 1. CRITICAL: Confirmed severe physical strikes, knockouts, armed assault
    if has_critical_strike:
        return "CRITICAL"
    if has_weapon and (has_fight or has_violent_swing):
        return "CRITICAL"
    if score >= 350:
        return "CRITICAL"

    # 2. HIGH: Violent swings, overhead stances, active scuffle/fight, or weapon with motion
    if has_violent_swing or has_fight:
        return "HIGH"
    if has_weapon and has_motion:
        return "HIGH"
    if score >= 120:
        return "HIGH"

    # 3. ELEVATED: Pre-assault indicators, isolated weapon proximity, sprint alone
    if has_weapon or has_motion:
        return "ELEVATED"
    if score >= 45:
        return "ELEVATED"

    # 4. LOW: Routine movement or sub-threshold
    return "LOW"

class RiskEngine:
    def __init__(s, cfg, fps=25.0, weights_path=None):
        s.cam = cfg.get("camera_id", "cam1")
        s.fps = fps
        s.p = {**P, **cfg.get("params", {})}
        bad = set(cfg.get("params", {})) - set(P)
        if bad:
            raise ValueError(f"unknown params (typo?): {bad}")
        s.zones = [
            dict(
                name=n,
                poly=np.array(z["poly"], np.int32),
                crit=z.get("crit", 1.0),
                restricted=z.get("restricted", True),
            )
            for n, z in cfg.get("zones", {}).items()
        ]
        s.events = defaultdict(list)
        s.hist = defaultdict(deque)
        s.zstate = {}
        s.last_emit = {}
        s.ost = {}
        s.atimes = deque()
        s.alerted = {}
        s.alerted_time = {}
        s.alerted_threats = defaultdict(set)
        s.lastbox = {}
        s.touched = set()
        s.scale = {}
        s.wpath = weights_path
        s._wm = 0
        s._wcheck = -1e9

        # Pairwise person interaction history for assault / violent approach detection
        s.pair_hist = defaultdict(deque)
        s.pair_contact = {}
        # Tracking person aspect ratio / posture for fall / person down detection
        s.person_posture = {}

        s.heatmap_size = (36, 64)  # Grid size (H, W) for 640x360 scaled down by 10
        s.dwell_heatmap = np.ones(s.heatmap_size, dtype=np.float32)
        s.path_heatmap = np.ones(s.heatmap_size, dtype=np.float32)
        s.heat_frames = 0
        s.last_cam_alert_time = -1e9
        s.last_cam_alert_score = 0.0

    # ---- helpers
    def _zone(s, pt):
        for z in s.zones:
            if cv2.pointPolygonTest(z["poly"], (float(pt[0]), float(pt[1])), False) >= 0:
                return z
        return None

    def _tprior(s, t):
        h = (dt.datetime.fromisoformat(s.p["start"]) + dt.timedelta(seconds=t)).hour
        a, b = s.p["night"]
        return s.p["night_mult"] if (h >= a or h < b) else 1.0

    def _reload(s, t):
        if not s.wpath or t - s._wcheck < 5:
            return
        s._wcheck = t
        try:
            m = os.path.getmtime(s.wpath)
            if m != s._wm:
                s._wm = m
                s.scale = json.load(open(s.wpath)).get("scale", {})
        except Exception:
            pass

    def emit(s, key, ty, t, zone=None, throttle=True):
        last = s.last_emit.get((key, ty))
        if throttle and last is not None and t - last < s.p["emit_gap"]:
            return
        s.last_emit[(key, ty)] = t
        w = BASE_W[ty] * s.scale.get(ty, 1.0) * (zone["crit"] if zone else 1.0) * s._tprior(t)
        s.events[key].append((t, ty, w, zone["name"] if zone else None))
        s.touched.add(key)

    def score(s, key, t):
        type_weights = defaultdict(float)
        types = set()
        for te, ty, w, _ in s.events.get(key, []):
            d = w * math.exp(-(t - te) / s.p["tau"])
            if d > 1.5:
                type_weights[ty] += d
                types.add(ty)

        # Passive background signals (sitting, loitering, routine paths) strictly capped at 15.0 max
        passive_sigs = {"LOITER", "ZONE_DWELL", "ATYPICAL_PATH", "RARE_DWELL", "GAP_DWELL"}
        passive_sum = sum(type_weights[k] for k in passive_sigs if k in type_weights)

        active_sum = 0.0
        active_types = types - passive_sigs
        for ty, val in type_weights.items():
            if ty in passive_sigs:
                continue
            active_sum += min(val, BASE_W.get(ty, 50) * 1.2)

        # Diversity bonus applies ONLY to active threat groups, never passive loitering
        active_groups = {GROUP[x] for x in active_types if x in GROUP}
        div_mult = 1.0 + s.p["div_bonus"] * max(len(active_groups) - 1, 0) if active_types else 1.0
        composite = (active_sum * div_mult) + min(passive_sum, 15.0)

        max_cap = 150.0 if ({"PHYSICAL_STRIKE", "KNOCKOUT_FALL"} & types) else 100.0
        return min(composite, max_cap), types

    def merge(s, old, new):
        s.events[new] += s.events.pop(old, [])
        s.touched.add(new)

    def inherit_events(s, key, past_events, t):
        """Inherit prior risk events from another camera handoff or linked track."""
        if not past_events:
            return
        for item in past_events:
            if isinstance(item, (list, tuple)) and len(item) >= 4:
                te, ty, w, zn = item[0], item[1], item[2], item[3]
                s.events[key].append((te, ty, w, zn))
        s.touched.add(key)
        # Suppress re-alerting for inherited cross-camera events!
        # The previous camera already handled or logged this activity.
        inherited_types = {item[1] for item in past_events if isinstance(item, (list, tuple)) and len(item) >= 2}
        s.alerted_time[key] = t + 30.0
        s.alerted_threats[key] = set(inherited_types)
        s.last_cam_alert_time = t + 30.0

    # ---- main
    def update(s, t, tracks):
        s._reload(t)
        p = s.p
        s.heat_frames += 1
        persons = [x for x in tracks if x["cls"] == "person"]

        # Track single person kinematics and posture
        for x in persons:
            key = f"{s.cam}:P{x['id']}"
            s.touched.add(key)
            x1, y1, x2, y2 = x["box"]
            cx, cy = ((x1 + x2) / 2.0, (y1 + y2) / 2.0)
            feet = (cx, y2)
            h = max(y2 - y1, 1.0)
            w_box = max(x2 - x1, 1.0)
            s.lastbox[key] = x["box"]
            H = s.hist[key]
            # Store timestamp, center_x, center_y, feet_y, height, width
            H.append((t, cx, cy, feet[1], h, w_box))
            while len(H) > 1 and H[0][0] < t - 20:
                H.popleft()

            z = s._zone(feet)
            zn = z["name"] if z and z["restricted"] else None
            zs = s.zstate.get(key, {})

            # Heatmap grid coordinate
            grid_y = min(s.heatmap_size[0] - 1, max(0, int(feet[1] / 10)))
            grid_x = min(s.heatmap_size[1] - 1, max(0, int(feet[0] / 10)))

            if zn and zs.get("zone") != zn:
                s.zstate[key] = {"zone": zn, "since": t, "last_in": t}
                s.emit(key, "ZONE_ENTER", t, z, throttle=False)
            elif zn:
                zs["last_in"] = t
                if t - zs["since"] >= p["dwell_s"]:
                    s.emit(key, "ZONE_DWELL", t, z)
            elif zs and t - zs.get("last_in", -1e9) > 1.5:
                s.zstate[key] = {}

            # Loiter detection (using robust body centroid)
            w = [q for q in H if q[0] >= t - p["loiter_s"]]
            is_dwelling = False
            if H[0][0] <= t - p["loiter_s"] * 0.9 and len(w) > 3:
                pts = np.array([[q[1], q[2]] for q in w])
                mh = np.mean([q[4] for q in w])
                if np.abs(pts - pts.mean(0)).max() < p["loiter_frac"] * mh:
                    s.emit(key, "LOITER", t, z)
                    is_dwelling = True

            # Running / sprint / fast movement detection (multi-window: short burst + sustained)
            is_running = False
            mh = max(np.mean([q[4] for q in H]), 1.0)

            # Person must have a plausible height and not be slumped/seated in a chair
            # Running/sprinting humans have upright aspect ratio (h / w_box >= 1.25)
            is_upright = (h / w_box) >= 1.25
            not_edge_clipped = (x1 > 20 and x2 < 620 and y1 > 10 and y2 < 355)
            # Track must be stable across at least 5 frames to prevent occlusion pop-in false triggers
            if len(H) >= 5 and mh >= 75 and h >= 75 and is_upright and not_edge_clipped:
                # 1. Immediate fast-burst / sudden sprint detection over short window (last 0.20s - 0.50s)
                r_short = [q for q in H if q[0] >= t - 0.50]
                if len(r_short) >= 4:
                    dt_short = r_short[-1][0] - r_short[0][0]
                    if dt_short >= 0.15:
                        d_cx = r_short[-1][1] - r_short[0][1]
                        d_cy = r_short[-1][2] - r_short[0][2]
                        disp_short = math.hypot(d_cx, d_cy)
                        v_short = disp_short / dt_short / mh
                        # Scale stability: reject boxes expanding/doubling from disocclusion
                        h_start, h_end = r_short[0][4], r_short[-1][4]
                        scale_change = abs(h_end - h_start) / max(h_start, 1.0)

                        # True sprint: person must physically traverse across the room horizontally
                        # Net horizontal displacement >= 60px AND >= 0.40 * height, with stable bounding box
                        if scale_change < 0.30 and abs(d_cx) >= max(0.40 * mh, 60.0):
                            if 1.25 <= v_short <= 4.2:
                                s.emit(key, "SUDDEN_SPRINT", t, z)
                                is_running = True
                            elif 0.80 <= v_short <= 4.2:
                                s.emit(key, "RUNNING", t, z)
                                is_running = True

                # 2. Sustained running & acceleration burst over wider window (up to 1.2s)
                r = [q for q in H if q[0] >= t - 1.2]
                if len(r) > 4 and r[-1][0] - r[0][0] >= 0.25:
                    dt_run = r[-1][0] - r[0][0]
                    d_cx = r[-1][1] - r[0][1]
                    d_cy = r[-1][2] - r[0][2]
                    disp = math.hypot(d_cx, d_cy)
                    d = disp / dt_run / mh
                    h_start, h_end = r[0][4], r[-1][4]
                    scale_change = abs(h_end - h_start) / max(h_start, 1.0)

                    if scale_change < 0.30 and abs(d_cx) >= max(0.45 * mh, 65.0) and (0.75 <= d <= 4.2):
                        s.emit(key, "RUNNING", t, z)
                        is_running = True

                    # Sudden sprint / burst acceleration detection
                    if len(r) >= 5 and abs(d_cx) >= max(0.50 * mh, 70.0):
                        m_idx = len(r) // 2
                        dt_early = max(r[m_idx][0] - r[0][0], 0.08)
                        dt_late = max(r[-1][0] - r[m_idx][0], 0.08)

                        disp_early = math.hypot(r[m_idx][1] - r[0][1], r[m_idx][2] - r[0][2])
                        disp_late = math.hypot(r[-1][1] - r[m_idx][1], r[-1][3] - r[m_idx][3])
                        d_early = disp_early / dt_early / mh
                        d_late = disp_late / dt_late / mh
                        if ((d_late - d_early) > 0.25 and 0.90 <= d_late <= 4.2) or (1.20 <= d <= 4.2):
                            s.emit(key, "SUDDEN_SPRINT", t, z)

            # Person down / collapse detection
            aspect = w_box / h
            posture = s.person_posture.setdefault(key, deque(maxlen=25))
            posture.append((t, aspect, h))
            if len(posture) >= 5:
                base_h = max([pt[2] for pt in posture])
                # True collapse: person was previously standing and collapsed to < 0.6 of standing height
                standing_before = any(pt[1] < 0.85 for pt in list(posture)[:-3])
                recent_fallen = [pt for pt in list(posture)[-3:] if standing_before and pt[1] > 1.25 and pt[2] < 0.6 * base_h]
                if standing_before and len(recent_fallen) >= 3:
                    s.emit(key, "PERSON_DOWN", t, z)

            # Heatmap update
            s.path_heatmap[grid_y, grid_x] += 1
            if is_dwelling:
                s.dwell_heatmap[grid_y, grid_x] += 1

            if s.heat_frames > 500:
                if not is_dwelling and not is_running:
                    path_prob = s.path_heatmap[grid_y, grid_x] / max(s.path_heatmap.max(), 1.0)
                    if path_prob < 0.05:
                        s.emit(key, "ATYPICAL_PATH", t, z)
                elif is_dwelling:
                    dwell_prob = s.dwell_heatmap[grid_y, grid_x] / max(s.dwell_heatmap.max(), 1.0)
                    if dwell_prob < 0.05:
                        s.emit(key, "RARE_DWELL", t, z)

        # Multi-person interaction analysis: assault, violent approach, scuffle / fight
        num_p = len(persons)
        if num_p >= 2:
            for i in range(num_p):
                for j in range(i + 1, num_p):
                    p1, p2 = persons[i], persons[j]
                    k1 = f"{s.cam}:P{p1['id']}"
                    k2 = f"{s.cam}:P{p2['id']}"
                    pair_key = (min(k1, k2), max(k1, k2))

                    b1, b2 = p1["box"], p2["box"]
                    c1 = ((b1[0] + b1[2]) / 2.0, (b1[1] + b1[3]) / 2.0)
                    c2 = ((b2[0] + b2[2]) / 2.0, (b2[1] + b2[3]) / 2.0)
                    h1 = max(b1[3] - b1[1], 1.0)
                    h2 = max(b2[3] - b2[1], 1.0)
                    avg_h = (h1 + h2) / 2.0

                    dist_norm = math.dist(c1, c2) / avg_h
                    dx = min(b1[2], b2[2]) - max(b1[0], b2[0])
                    dy = min(b1[3], b2[3]) - max(b1[1], b2[1])
                    inter = max(0.0, dx) * max(0.0, dy)
                    a1 = (b1[2] - b1[0]) * (b1[3] - b1[1])
                    a2 = (b2[2] - b2[0]) * (b2[3] - b2[1])
                    box_overlap = inter / max(min(a1, a2), 1.0)
                    if box_overlap > 0.65:
                        continue  # Duplicate tracker boxes on the same individual

                    # Ground plane depth difference: check feet y
                    dy_feet = abs(b1[3] - b2[3])
                    same_ground_plane = dy_feet < 0.35 * avg_h
                    is_overlap = dx > 0 and dy > 0 and same_ground_plane

                    ph = s.pair_hist[pair_key]
                    ph.append((t, dist_norm, c1, c2))
                    while len(ph) > 1 and ph[0][0] < t - 3.0:
                        ph.popleft()

                    # 1. Sudden Aggressive Approach / Violent Convergence (Requires running speed > 1.2 hps)
                    if len(ph) >= 3 and (dist_norm < 0.65 or is_overlap):
                        past = [pt for pt in ph if 0.3 <= (t - pt[0]) <= 1.5]
                        if past:
                            past_pt = past[0]
                            past_dist = past_pt[1]
                            dt_conv = max(t - past_pt[0], 0.1)
                            closing_speed = (past_dist - dist_norm) / dt_conv
                            # Determine velocity of advancing person
                            m1_speed = (math.hypot(c1[0] - past_pt[2][0], c1[1] - past_pt[2][1]) / h1) / dt_conv
                            m2_speed = (math.hypot(c2[0] - past_pt[3][0], c2[1] - past_pt[3][1]) / h2) / dt_conv
                            # Must be running/rushing, not normal walking pass-by
                            if past_dist > 1.1 and closing_speed > 1.3 and max(m1_speed, m2_speed) > 1.1:
                                aggressor = k1 if m1_speed >= m2_speed else k2
                                s.emit(aggressor, "AGGRESSIVE_APPROACH", t, s._zone(c1 if aggressor == k1 else c2))

                    # 2. Physical Struggle / Scuffle / Fight Suspected
                    # Bug 2 Fix: Must hold for a SUSTAINED window (>= 0.45s / multiple consecutive frames), not single-frame snapshot.
                    # Two people crossing paths satisfy proximity + displacement for only a single snapshot, then separate.
                    # Two people walking side-by-side move in the same direction (cos_th > 0.45).
                    in_proximity = (dist_norm < 0.65) or (is_overlap and dist_norm < 0.75)
                    has_fight_motion = False
                    if in_proximity and len(ph) >= 2:
                        rec = [pt for pt in ph if 0.12 <= (t - pt[0]) <= 0.6]
                        if rec:
                            past_p = rec[0]
                            dt_m = max(t - past_p[0], 0.10)
                            disp1 = math.hypot(c1[0] - past_p[2][0], c1[1] - past_p[2][1]) / h1 / dt_m
                            disp2 = math.hypot(c2[0] - past_p[3][0], c2[1] - past_p[3][1]) / h2 / dt_m
                            
                            v1 = (c1[0] - past_p[2][0], c1[1] - past_p[2][1])
                            v2 = (c2[0] - past_p[3][0], c2[1] - past_p[3][1])
                            mag1 = math.hypot(v1[0], v1[1])
                            mag2 = math.hypot(v2[0], v2[1])
                            cos_th = (v1[0]*v2[0] + v1[1]*v2[1]) / (mag1 * mag2) if (mag1 > 3.0 and mag2 > 3.0) else 0.0

                            # Walking together in the same direction is peaceful companion walking
                            is_walking_together = cos_th > 0.35
                            # Separating / passing each other is crossing paths
                            is_separating = (not is_overlap) and (dist_norm > past_p[1] + 0.04)
                            # Passing each other in opposite directions without physical contact
                            is_passing_opposite = (cos_th < -0.3) and (not is_overlap) and (dist_norm > 0.20)
                            # Idle / stationary / casual movement near each other
                            is_idle = (disp1 < 0.40 or disp2 < 0.40)

                            # Physical struggle requires true physical overlap with high reciprocal violent motion from both
                            has_struggle = (is_overlap and (disp1 >= 0.55 and disp2 >= 0.55) and (disp1 + disp2 > 1.65)) or \
                                           ((disp1 > 0.85 and disp2 > 0.85) and (disp1 + disp2 > 2.0))
                            if has_struggle and not is_walking_together and not is_separating and not is_passing_opposite and not is_idle:
                                has_fight_motion = True

                    st = s.pair_contact.setdefault(pair_key, {"start": t, "count": 0, "last_t": t})
                    if in_proximity and has_fight_motion:
                        if t - st["last_t"] > 0.40:
                            st["start"] = t
                            st["count"] = 1
                        else:
                            st["count"] += 1
                        st["last_t"] = t

                        # Requires sustained struggle window >= 1.0s AND multiple consecutive frames (>= 8)
                        if (t - st["start"]) >= 1.0 and st["count"] >= 8:
                            s.emit(k1, "FIGHT_SUSPECTED", t, s._zone(c1))
                            s.emit(k2, "FIGHT_SUSPECTED", t, s._zone(c2))
                    else:
                        s.pair_contact[pair_key] = {"start": t, "count": 0, "last_t": t}

        # Unattended object detection
        for o in [x for x in tracks if x["cls"] in OBJ]:
            key = f"{s.cam}:O{o['id']}"
            x1, y1, x2, y2 = o["box"]
            c = ((x1 + x2) / 2, (y1 + y2) / 2)
            size = max(x2 - x1, y2 - y1)
            s.lastbox[key] = o["box"]
            st = s.ost.setdefault(key, dict(anchor=c, t0=t, near=t))
            if math.dist(c, st["anchor"]) > max(20, 0.6 * size):
                st["anchor"] = c
                st["t0"] = t
            for q in persons:
                a, b, cc, d = q["box"]
                if math.dist(c, ((a + cc) / 2, (b + d) / 2)) < 1.0 * (d - b):
                    st["near"] = t
                    break
            if t - st["t0"] >= p["stat_s"] and t - st["near"] >= p["away_s"]:
                s.emit(key, "UNATTENDED", t, s._zone(c))

        # Weapon proximity (held by or on person)
        for w in [x for x in tracks if x["cls"] in WEAPON_CLS]:
            wx = (w["box"][0] + w["box"][2]) / 2
            wy = (w["box"][1] + w["box"][3]) / 2
            for pp in persons:
                pk = f"{s.cam}:P{pp['id']}"
                px1, py1, px2, py2 = pp["box"]
                pw = max(px2 - px1, 1)
                ph = max(py2 - py1, 1)
                if (px1 - 0.25 * pw <= wx <= px2 + 0.25 * pw) and (py1 - 0.15 * ph <= wy <= py2 + 0.15 * ph):
                    z = s._zone(((px1 + px2) / 2, py2))
                    s.emit(pk, "WEAPON_NEAR_PERSON", t, z)
                    break

        # Output alert evaluation
        out = []
        for key in s.touched:
            s.events[key] = [e for e in s.events[key] if t - e[0] < 5 * p["tau"]]
            sc, types = s.score(key, t)
            groups = {GROUP[x] for x in types}
            # Genuine crime alerts require verified violence or armed threats
            # Routine motion (RUNNING, SUDDEN_SPRINT alone, ATYPICAL_PATH, LOITER) tracks on HUD but DOES NOT trigger alarms
            pose_signals = {"PHYSICAL_STRIKE", "OVERHEAD_STANCE", "VIOLENT_SWING", "KNOCKOUT_FALL"}
            has_strike = bool(types & {"PHYSICAL_STRIKE", "KNOCKOUT_FALL"})
            has_weapon_threat = ("weapon" in groups) or ("WEAPON_NEAR_PERSON" in types)
            has_active_fight = ("FIGHT_SUSPECTED" in types) and bool(types & pose_signals)

            is_confirmed_crime = has_strike or (has_weapon_threat and (bool(types & pose_signals) or bool(types & {"AGGRESSIVE_APPROACH"}))) or has_active_fight

            # Restricted zone trespassing breach
            has_zone_breach = ("zone" in groups) and any(e[3] for e in s.events[key])

            if not (is_confirmed_crime or has_zone_breach):
                continue

            # Require significant risk threshold (>= 70.0) for genuine crime alerts
            effective_thr = 70.0
            if sc < effective_thr:
                continue

            # Cooldown and deduplication: suppress duplicate alerts for the same ongoing threat
            last_al_t = s.alerted_time.get(key, -1e9)
            prev_threats = s.alerted_threats[key]
            active_threat_sigs = types & (pose_signals | {"WEAPON_NEAR_PERSON", "SUDDEN_SPRINT", "RUNNING", "FIGHT_SUSPECTED", "AGGRESSIVE_APPROACH"})

            # Allow immediate alert if there is a critical violence strike escalation
            has_strike_escalation = bool(types & {"PHYSICAL_STRIKE", "KNOCKOUT_FALL"}) and not bool(prev_threats & {"PHYSICAL_STRIKE", "KNOCKOUT_FALL"})

            # Cooldown window of 25s for the same ongoing threat on this entity
            cooldown_window = 25.0
            if (t - last_al_t < cooldown_window) and not has_strike_escalation:
                continue

            # Camera-level deduplication: suppress secondary alerts on the same camera within 20s unless critical strike escalates
            cam_has_strike = bool(types & {"PHYSICAL_STRIKE", "KNOCKOUT_FALL"}) and not bool(getattr(s, "cam_alerted_threats", set()) & {"PHYSICAL_STRIKE", "KNOCKOUT_FALL"})
            if (t - getattr(s, "last_cam_alert_time", -1e9) < 20.0) and not cam_has_strike:
                continue

            # Update alert history (both entity and camera-level)
            s.last_cam_alert_time = t
            s.cam_alerted_threats = set(active_threat_sigs)
            s.alerted_time[key] = t
            s.alerted_threats[key] = set(active_threat_sigs)
            s.alerted[key] = t

            # Alert confirmation and budget check
            while s.atimes and s.atimes[0] < t - 3600:
                s.atimes.popleft()
            status = "PENDING_CONFIRMATION"
            s.atimes.append(t)

            cnt = defaultdict(int)
            for e in s.events[key]:
                cnt[e[1]] += 1
            reasons_list = [f"{k} x{v}" for k, v in sorted(cnt.items())]
            r_level = classify_risk_level(sc, types, reasons_list)
            out.append(
                dict(
                    id=f"{s.cam}-{int(t * 1000)}-{key.split(':')[1]}",
                    camera=s.cam,
                    t=round(t, 2),
                    entity=key,
                    score=round(sc, 1),
                    risk_level=r_level,
                    severity=round(sc / p["thr"], 2),
                    status=status,
                    types=sorted(types),
                    reasons=reasons_list,
                    box=s.lastbox.get(key),
                    zone=next((e[3] for e in reversed(s.events[key]) if e[3]), None),
                )
            )
        s.touched = set()
        return sorted(out, key=lambda a: -a["score"])
