import sys, os, json, random, shutil, cv2, numpy as np, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from smartcctv.risk import RiskEngine
from smartcctv.evidence import Chain
from smartcctv.tamper import TamperMonitor
from smartcctv.xcam import CrossCam, LocalTrackReID, embed, sim
from smartcctv.detector import MotionGate
from smartcctv.detector_yolo8 import YoloDetector
from smartcctv.dashboard import create_app

CFG = {"zones": {"vault": {"poly": [[400, 100], [700, 100], [700, 500], [400, 500]], "crit": 1.0}},
       "params": {"start": "2026-01-01T12:00:00", "loiter_s": 8, "dwell_s": 3}}
def P(i, x, y, h=150): return dict(id=i, cls="person", box=(x - 30, y - h, x + 30, y))
def run(eng, seq, fps=10):
    al = []
    for k, tr in enumerate(seq): al += eng.update(k / fps, tr)
    return al

def test_normal_walker_no_alert():
    e = RiskEngine(CFG); seq = [[P(1, 50 + 6 * k, 300)] for k in range(150)]  # walks 0.4 h/s, outside zone
    assert run(e, seq) == []

def test_intruder_loiters_in_zone_alerts_with_reasons():
    e = RiskEngine(CFG); seq = [[P(1, 200 + 15 * k, 300)] for k in range(20)] + [[P(1, 500, 300)]] * 150
    al = run(e, seq); assert al and al[0]["status"] == "PENDING_CONFIRMATION" and "LOITER" in " ".join(al[0]["reasons"]), al

def test_single_zone_touch_alone_does_not_alert():
    e = RiskEngine(CFG); seq = [[P(1, 350 + 12 * k, 300)] for k in range(40)]  # crosses zone quickly
    assert run(e, seq) == []

def test_unattended_object():
    e = RiskEngine(CFG); bag = dict(id=9, cls="backpack", box=(100, 280, 140, 320)); seq = []
    seq += [[P(1, 110, 300), bag]] * 30                      # owner beside bag
    seq += [[P(1, 110 + 20 * k, 300), bag] for k in range(1, 15)] + [[bag]] * 200  # owner walks away
    al = run(e, seq); assert any("UNATTENDED" in " ".join(a["reasons"]) for a in al), al

def test_carried_bag_no_alert():
    e = RiskEngine(CFG); seq = [[P(1, 50 + 8 * k, 300), dict(id=9, cls="backpack", box=(50 + 8 * k, 220, 90 + 8 * k, 260))] for k in range(200)]
    assert run(e, seq) == []

def test_budget_suppresses_flood():
    cfg = json.loads(json.dumps(CFG)); cfg["params"]["alert_budget_per_hour"] = 2
    e = RiskEngine(cfg); seq = []
    for k in range(200): seq.append([dict(id=i, cls="person", box=(470 + 5 * i, 230, 530 + 5 * i, 300 + i * 0)) for i in range(1, 7)])
    al = run(e, seq); st = [a["status"] for a in al]
    assert st.count("PENDING_CONFIRMATION") <= 2 and "SUPPRESSED_BY_BUDGET" in st, st

def test_chain_detects_tampering():
    p = os.path.join(tempfile.gettempdir(), "t.chain"); os.path.exists(p) and os.remove(p); c = Chain(p)
    for i in range(5): c.append({"i": i})
    assert Chain.verify(p)[0]
    L = open(p).read().split("\n"); r = json.loads(L[2]); r["payload"]["i"] = 99; L[2] = json.dumps(r); open(p, "w").write("\n".join(L))
    ok, n, bad = Chain.verify(p); assert not ok and bad == 2

def test_hmac_chain_security():
    p = os.path.join(tempfile.gettempdir(), "t_hmac.chain"); os.path.exists(p) and os.remove(p)
    c = Chain(p, secret="test-super-secret-key")
    c.append({"alert": "intrusion", "score": 95})
    assert Chain.verify(p, secret="test-super-secret-key")[0]
    assert not Chain.verify(p, secret="wrong-key")[0]

def test_tamper_monitor():
    rng = np.random.RandomState(0); base = cv2.GaussianBlur(rng.randint(0, 255, (360, 640, 3), np.uint8), (5, 5), 0)
    base = cv2.addWeighted(base, 1, cv2.resize(cv2.imread("/dev/null") if False else rng.randint(0, 255, (36, 64, 3), np.uint8), (640, 360), interpolation=cv2.INTER_NEAREST), 0.8, 0)
    def kinds(frames):
        m = TamperMonitor(); out = []
        for k, f in enumerate(frames): out += [a["kind"] for a in m.update(k / 10, f)]
        return out
    ok = [base] * 60
    assert kinds(ok) == []
    assert "BLURRED" in kinds(ok + [cv2.GaussianBlur(base, (0, 0), 12)] * 40)
    assert "COVERED" in kinds(ok + [np.zeros_like(base)] * 40)
    assert "MOVED" in kinds(ok + [np.roll(base, 60, axis=1)] * 40)

def test_crosscam_topology_beats_appearance_only():
    edges = {("A", "B"): (12.0, 2.0)}; wins = {True: 0, False: 0}; N = 400
    for use in (True, False):
        rng = random.Random(1)
        for _ in range(N):
            cc = CrossCam(edges, use_topology=use, rng=random.Random(rng.random())); emb = np.ones(96) / 96  # identical appearance = worst case
            te1, te2 = 0.0, rng.uniform(2, 8); cc.on_exit("P1", "A", te1, emb); cc.on_exit("P2", "A", te2, emb)
            ar = sorted([(te1 + rng.gauss(12, 2), "P1"), (te2 + rng.gauss(12, 2), "P2")]); ok = True
            for t, truth in ar:
                gid, post, gap = cc.on_appear("B", t, emb); ok &= (gid == truth)
            wins[use] += ok
    print(f"   re-link both correctly: topology={wins[True]/N:.2f} appearance-only={wins[False]/N:.2f}")
    assert wins[True] > wins[False] + 0.15

def test_gap_dwell_and_belief():
    cc = CrossCam({("A", "B"): (12, 2), ("A", "C"): (30, 5)}); emb = np.ones(96) / 96; cc.on_exit("P1", "A", 0, emb)
    b = cc.belief("P1", 10); assert set(b) == {"B", "C"} and abs(sum(b.values()) - 1) < 0.01
    gid, post, gap = cc.on_appear("B", 25, emb); assert gid == "P1" or gap is None  # too late -> may be new id
    cc2 = CrossCam({("A", "B"): (12, 2)}); cc2.on_exit("P1", "A", 0, emb); cc2.new_prior = 1e-3
    gid, post, gap = cc2.on_appear("B", 17, emb); assert gid == "P1" and gap and gap["excess_s"] == 5.0

def test_local_track_reid_repair():
    tracker = LocalTrackReID(max_gap_s=3.0, sim_thr=0.7)
    emb = np.array([0.5] * 96, dtype=np.float32)
    tracker.on_lost(101, t=10.0, emb=emb, box=(100, 100, 200, 200))
    # New track appears 1.5s later with matching embedding
    matched_id, s = tracker.match_new(t=11.5, emb=emb, box=(110, 105, 210, 205))
    assert matched_id == 101 and s > 0.9

def test_motion_gate_skips_static_scene():
    g = MotionGate(); fr = np.full((360, 640, 3), 90, np.uint8); on = [g(fr) for _ in range(150)]
    skip = 100 * (1 - sum(on) / len(on)); print(f"   static scene: detector skipped on {skip:.0f}% of frames"); assert skip > 80

def test_yolov8_detector_wrapper():
    det = YoloDetector(weights="yolov8n.pt", imgsz=320)
    dummy = np.zeros((320, 320, 3), np.uint8)
    out = det(dummy)
    assert isinstance(out, list) and det.calls >= 1

def test_feedback_loop_and_dashboard():
    out = os.path.join(tempfile.gettempdir(), "dash"); shutil.rmtree(out, ignore_errors=True); os.makedirs(out + "/clips")
    Chain(out + "/alerts.chain.jsonl").append(dict(id="a1", camera="cam1", score=90, reasons=["LOITER x3"], types=["LOITER"], status="PENDING_CONFIRMATION", zone="vault", clip="x.mp4"))
    c = create_app(out).test_client()
    headers = {"Authorization": "Basic YWRtaW46YWRtaW4xMjM="}
    assert b"a1" in c.get("/", headers=headers).data
    c.get("/decide/a1/dismiss", headers=headers); w = json.load(open(out + "/weights.json"))["scale"]["LOITER"]; assert w < 1
    assert Chain.verify(out + "/decisions.chain.jsonl")[0]
    e = RiskEngine(CFG, weights_path=out + "/weights.json"); e._reload(100); assert e.scale["LOITER"] == w

if __name__ == "__main__":
    fails = 0
    for n, f in list(globals().items()):
        if n.startswith("test_"):
            try: f(); print("PASS", n)
            except Exception as ex: fails += 1; print("FAIL", n, repr(ex)[:300])
    sys.exit(fails)
