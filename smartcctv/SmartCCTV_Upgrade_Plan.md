# SmartCCTV: Local Upgrade Plan

Goal: turn the working sandbox pipeline into a stronger, defensible system on your own machine.
Core idea to protect: **risk accumulation per track + alert budget + human confirmation + blind-spot linking**. Everything else is swappable.

> Status of this plan: the current pipeline was run and tested in a sandbox (12/12 tests). The upgrades below are **not yet tested by me**. Each phase has a "done when" check so you can verify it yourself.

---

## 0. Before changing anything (30 min)

1. Extract `smartcctv.tar.gz`, run `./setup.sh`, then `python -m smartcctv.run`.
2. Run `python smartcctv/tests/test_all.py` and confirm all pass.
3. Save `out/summary.json` as your **baseline** (ms per frame, alerts, skip %).
4. Note your hardware: GPU or CPU only. It decides phase 1 settings.
5. Make a git repo and commit. Do each phase on its own branch.

**Done when:** baseline numbers are saved and tests pass on your machine.

---

## 1. Priority order (highest value first)

| # | Upgrade | Why it matters | Effort |
|---|---|---|---|
| 1 | Detector: YOLOv8 | Big accuracy jump, especially small objects (bags) | Low |
| 2 | Evaluation harness | Without it, no claim is credible | Medium |
| 3 | Re-ID: OSNet embeddings | Cross-camera linking is useless with color histograms | Medium |
| 4 | Multi-camera runner | Turns the simulation into a real system | Medium |
| 5 | Site "normal" model (paths/dwell) | Reduces false alerts, feeds the risk engine | Medium |
| 6 | Local VLM explainer on alerts only | Better evidence summaries for operators | Low-Med |
| 7 | Trust hardening (auth, signing, retention) | Matches the "Digital Trust" theme | Low-Med |
| 8 | Learned risk weights | Replaces hand-set weights, needs data first | Later |

---

## 2. Phase 1: Detector swap (day 1)

**Change:** add a YOLOv8 wrapper with the *same output* as the current `Detector`, so nothing else changes.

```bash
pip install ultralytics   # pulls PyTorch; use the CUDA build if you have an NVIDIA GPU
```

Add `smartcctv/detector_yolo8.py` (sketch, verify against your installed version):

```python
from ultralytics import YOLO
KEEP_IDS = [0, 24, 26, 28, 43]   # person, backpack, handbag, suitcase, knife (COCO ids)

class YoloDetector:
    def __init__(self, weights="yolov8s.pt", imgsz=640, conf=0.25, device=None):
        self.m = YOLO(weights); self.imgsz, self.conf, self.device = imgsz, conf, device
        self.names = [self.m.names[i] for i in range(len(self.m.names))]
        self.calls = self.verify_calls = 0
    def __call__(self, frame):
        self.calls += 1
        r = self.m(frame, imgsz=self.imgsz, conf=self.conf, classes=KEEP_IDS,
                   device=self.device, verbose=False)[0]
        return [(*map(float, b), float(c), self.m.names[int(k)])
                for b, c, k in zip(r.boxes.xyxy.tolist(), r.boxes.conf.tolist(), r.boxes.cls.tolist())]
```

In `run.py`, choose the detector from config (`"detector": "yolov8"`). Keep the Stage 2 crop re-check idea, but with YOLOv8 try `imgsz=960` on the crop instead of a second small model.

Model choice: `yolov8n` for CPU or many cameras, `yolov8s` as the default, `yolov8m` only with a GPU.

**Done when:** same video, same tests, and you record ms per frame, recall on your own staged clips, and false alerts per hour versus baseline.

---

## 3. Phase 2: Evaluation harness (build this early)

Build `eval/` that replays footage and scores alerts against a ground-truth file.

**Data you can create yourself (most important):**
- 20-30 short **staged clips** with friends: leave a bag and walk away, enter a marked zone, loiter, run, normal walking, carrying a bag.
- Write `labels.json` per clip: event type + start/end second.

**Public data for sanity checks (verify access and licenses first):**
- UCF-Crime, ShanghaiTech (anomaly detection)
- Market-1501 (person re-ID)
- A non-overlapping multi-camera people dataset (e.g. NLPR_MCT) for cross-camera tests

**Metrics to report (not accuracy):**
- Alerts per camera per day
- Precision and recall **at a fixed alert budget**
- Time from event start to alert
- Cross-camera: re-link accuracy, ID switches, time to re-acquire

**Ablations that prove your idea (this is your evidence):**
1. Per-event alerts (no accumulation) vs risk accumulation
2. Appearance-only linking vs appearance + travel-time
3. Budget on vs off (alerts/day and missed events)
4. Motion gate on vs off (compute vs recall)

**Done when:** one command produces a results table with all four ablations.

---

## 4. Phase 3: Real re-identification

Replace `xcam.embed` (color histogram) with a person re-ID model.

Options:
- **BoxMOT** (`pip install boxmot`): bundles OSNet and re-ID trackers, easiest start.
- **torchreid** (`KaiyangZhou/deep-person-reid`): OSNet models, more manual.

Rules:
- Compute embeddings on the **best-quality crop** of a track, not every frame. Average the top few.
- Keep the interface `embed(frame, box) -> vector` and `sim(a, b) -> [0,1]` (cosine similarity).
- Re-tune `alpha` and `new_prior` in `CrossCam` on your data, do not guess.
- Also use re-ID **within one camera** to repair ByteTrack ID switches. Otherwise risk gets split across IDs. Consider BoT-SORT with re-ID enabled.

**Done when:** on your staged multi-camera clips, linking accuracy beats the histogram version, and ID switches drop.

---

## 5. Phase 4: Real multi-camera runner

Current `xcam` is only tested in simulation. Make it live:

- One process or thread per camera (RTSP or video file), each running the existing per-camera pipeline.
- A shared **identity service** (start simple: a `multiprocessing.Manager` object or a small Redis instance) that holds `CrossCam` ghosts and merges risk with `RiskEngine.merge`.
- Events sent between processes: `exit(cam, track, t, embedding)` and `appear(cam, track, t, embedding)`.
- **Learn the topology** instead of hand-writing it: for links that operators confirm, store the transit time, then fit mean and spread per camera pair.
- Use `belief()` output to pre-position a PTZ camera or notify the nearest guard.
- Sync clocks (NTP) across cameras. Bad timestamps break transit-time logic.

Config sketch:
```json
{
  "cameras": [
    {"id": "gate", "source": "rtsp://...", "zones": {}},
    {"id": "lobby", "source": "rtsp://...", "zones": {}}
  ],
  "topology": [["gate", "lobby", 12.0, 2.5]]
}
```

**Done when:** a person walking gate to lobby keeps one global ID, and a person who hides in the gap triggers `GAP_DWELL`.

---

## 6. Phase 5: Better "normal" and cheaper compute

**Site normal model (cheap, effective):**
- Over a week of footage, learn per-camera heatmaps: where people stand, how long, and which direction they walk.
- Add new risk events: `ATYPICAL_PATH` (going against the usual flow, using a rarely used area), `RARE_DWELL_PLACE`.
- These are still weak signals. They feed the accumulator, they never alert alone.

**Compute savings:**
- Use the camera's **low-res substream** for the gate and detector, and pull the **main stream crop** only on a flag (you can do this now with RTSP).
- Make the motion gate **per region**, so busy scenes still save compute.
- Cap detector rate (for example 8-10 fps) and let the tracker fill the gaps.

**Optional Stage 3: local VLM explainer:**
- Run a small local vision-language model (for example via Ollama) **only on alerts that already passed the threshold**.
- Ask it to *describe* the clip (who, where, what changed). Show it as context text.
- Never let it make the decision, and never use it for identifying people.

**Done when:** alerts per camera per day drop on the same footage, with recall on staged events unchanged.

---

## 7. Phase 6: Trust hardening ("Digital Trust")

- **Streams:** RTSP over TLS or a VPN, unique camera credentials, no default passwords.
- **Dashboard:** add login and role checks before exposing it beyond localhost (currently none).
- **Logs:** move from plain hash chain to **signed** records (Ed25519 or HMAC with a key kept outside the app). Periodically write the chain head hash somewhere separate (another machine or a printed daily receipt).
- **Evidence:** store the clip hash, model version, config hash and threshold in every alert record.
- **Tamper monitor:** calibrate blur, cover and shift thresholds on your real cameras. Expect false alarms on PTZ cameras.
- **Privacy (India: DPDP Act 2023):** retention limits (auto-delete non-alert footage), delete best-shot crops after review, access logs, no face recognition, and a written purpose statement.
- **Humans:** dispatch to authorities only after confirmation. Tamper alerts go to the admin, not the police.

**Done when:** an altered log line is detected, an unauthenticated dashboard request is refused, and retention deletes old files.

---

## 8. Known weaknesses in the current code (fix list)

1. Clip files use `mp4v`, which many browsers cannot play. Re-encode to H.264 with ffmpeg.
2. Time uses video seconds. For live cameras use wall-clock time for the budget and time-of-day prior.
3. The alert budget is global per engine. Make it per camera and per zone.
4. Risk weights are hand-set. After a few hundred confirmed or dismissed alerts, fit them (logistic regression on event counts), and keep the operator feedback loop as a safety net.
5. The dashboard feedback multiplies weights by 1.1 or 0.85 with no memory of context. Track feedback per zone and time of day.
6. Object ownership is simple (nearest person). Crowds will confuse it.
7. The loiter and running thresholds use pixel ratios and ignore perspective. Calibrate with a ground-plane homography per camera.
8. Adversarial robustness is not addressed. Multi-signal accumulation and temporal consistency help, but treat this as an open risk in your write-up.

---

## 9. Suggested timeline

| Week | Deliverable |
|---|---|
| 1 | Phase 0 baseline, YOLOv8 swap, 20+ staged clips labeled |
| 2 | Evaluation harness with the 4 ablations |
| 3 | Real re-ID, within-camera ID repair |
| 4 | Multi-camera runner, topology learning |
| 5 | Site normal model, per-region gating, substream/main-stream split |
| 6 | Trust hardening, privacy policy, final evaluation and write-up |

For a hackathon, do weeks 1-2 plus a small version of week 4 (two cameras) and present the ablation table.

---

## 10. What to claim (and not claim)

**Safe to claim (once your ablations show it):**
- Accumulating weak signals per track cuts alerts per camera per day compared with per-event alerts.
- Travel-time priors improve cross-camera linking over appearance alone.
- Every alert ships with evidence, a signed log, and a human confirmation step.

**Do not claim:**
- "Detects crime." You detect defined suspicious behaviors.
- Real-world accuracy from public benchmarks. Report your own site results.
- That adversarial attacks are solved.
- That the blind-spot tracking is exact. It is a probability, and it degrades with gap length.

---

## 11. Commands cheat sheet

```bash
./setup.sh                                           # models + basic deps
python -m smartcctv.run --config smartcctv/config.json
python -m smartcctv.dashboard out                    # review queue at http://localhost:5000
python smartcctv/tests/test_all.py                   # logic tests
```
