import sys
import os
import time
import numpy as np
import cv2

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "smartcctv", "w")))
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from backend.cross_cam_coordinator import CrossCameraCoordinator
from smartcctv.risk import RiskEngine

def test_cross_camera_scenario():
    print("=== Testing Cross-Camera 2-Second Transition & Risk Inheritance ===")
    coord = CrossCameraCoordinator(transit_window_s=30.0, sim_threshold=0.50)

    # 1. Setup Camera A risk engine & simulate elevated activity
    cfg_a = {"camera_id": "cam_phone_live", "zones": {}, "params": {"thr": 35, "cooldown": 3, "alert_budget_per_hour": 1000}}
    eng_a = RiskEngine(cfg_a, fps=25.0)

    t0 = 1000.0
    pk_a = "cam_phone_live:P1"

    # Emit elevated actions on Cam A: running sprint + aggressive stance
    eng_a.emit(pk_a, "SUDDEN_SPRINT", t0 - 4.0)
    eng_a.emit(pk_a, "AGGRESSIVE_APPROACH", t0 - 2.0)
    score_a, sigs_a = eng_a.score(pk_a, t0)
    print(f"[Cam A] Person P1 accumulated Risk Score: {score_a:.1f}, Signals: {sigs_a}")
    assert score_a > 40, f"Expected elevated score on Cam A, got {score_a}"

    # Create dummy person frame and bounding box
    frame_a = np.zeros((480, 640, 3), dtype=np.uint8)
    frame_a[100:350, 200:350] = (40, 60, 200) # Distinct color pattern for embedding
    box_a = (200, 100, 350, 350)

    # Person P1 appears in Cam A
    coord.process_person_appearance("cam_phone_live", 1, t0 - 5.0, frame_a, box_a)
    gid_a = coord.track_to_global[("cam_phone_live", 1)]
    print(f"[Cam A] Assigned Global Entity ID: {gid_a}")

    # 2. At t0, person exits Cam A coverage into blind spot
    evs_a = eng_a.events.get(pk_a, [])
    coord.register_track_loss("cam_phone_live", 1, t0, score_a, "HIGH", sigs_a, evs_a, box_a)
    assert gid_a in coord.in_transit, "Person must be registered in blind spot in-transit cache"
    print(f"[Blind Spot] Registered {gid_a} in transit with preserved risk {score_a:.1f}")

    # Check live ghosts query
    ghosts = coord.get_in_transit_ghosts()
    print(f"[Blind Spot API] Active ghosts count: {len(ghosts)}, Ghost: {ghosts[0]['ghost_id']}")

    # 3. After 2.0 seconds (t0 + 2.0s), person enters Camera B (cam_phone_live_2)
    t1 = t0 + 2.0
    cfg_b = {"camera_id": "cam_phone_live_2", "zones": {}, "params": {"thr": 35, "cooldown": 3, "alert_budget_per_hour": 1000}}
    eng_b = RiskEngine(cfg_b, fps=25.0)

    # Same person appearance in Cam B (same clothing/visual profile)
    frame_b = np.zeros((480, 640, 3), dtype=np.uint8)
    frame_b[80:330, 220:370] = (40, 60, 200)
    box_b = (220, 80, 370, 330)

    # Cam B detects person as local track ID 5
    handoff = coord.process_person_appearance("cam_phone_live_2", 5, t1, frame_b, box_b)
    assert handoff is not None, "Coordinator MUST match the person exiting Cam A after 2s!"
    print(f"[Cam B] SUCCESSFUL RE-ID MATCH!")
    print(f"       Global ID: {handoff['global_id']}")
    print(f"       From Camera: {handoff['from_camera']} -> To: {handoff['to_camera']}")
    print(f"       Transit Duration: {handoff['transit_duration_s']}s")
    print(f"       Transferred Risk: {handoff['transferred_risk']}")
    print(f"       Similarity: {handoff['similarity']}")

    # 4. Camera B inherits the past risk events into its RiskEngine
    pk_b = "cam_phone_live_2:P5"
    eng_b.inherit_events(pk_b, handoff.get("events", []), t1)

    # 5. Check risk score on Cam B
    score_b, sigs_b = eng_b.score(pk_b, t1)
    print(f"[Cam B] Person P5 (Global {handoff['global_id']}) Resumed Risk Score: {score_b:.1f}")
    assert score_b > 40, f"Expected risk to be preserved on Cam B, but got {score_b}"

    # 6. Verify that calling eng_b.update does NOT fire a false alert on Camera B
    tracks_b = [{"id": 5, "cls": "person", "box": box_b}]
    alerts_b = eng_b.update(t1, tracks_b)
    print(f"[Cam B] Alert count generated for transferred person: {len(alerts_b)}")
    assert len(alerts_b) == 0, f"Expected 0 alerts for transferred person, got {len(alerts_b)}"

    # Verify handoff history
    history = coord.get_handoff_history()
    assert len(history) == 1
    print(f"[API Verified] Cross-Camera Handover Completed Successfully! Test PASSED.")

if __name__ == "__main__":
    test_cross_camera_scenario()
