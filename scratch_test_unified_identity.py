import sys
import os
import time
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "smartcctv", "w")))
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from backend.cross_cam_coordinator import cross_camera_coordinator, embed, safe_sim
from smartcctv.risk import RiskEngine

def test_unified_cross_cam_identity():
    print("=== Testing Unique Person IDs + Single ID Handover Across Cameras ===")
    coord = cross_camera_coordinator
    coord.reset()

    # -------------------------------------------------------------
    # 1. Camera 1 detects Person A (John, red shirt) and Person B (Mary, white shirt) simultaneously
    # -------------------------------------------------------------
    t0 = 1000.0
    cam1 = "cam_phone_live"

    # Person A (John) - Red clothing pattern
    frame_john = np.zeros((480, 640, 3), dtype=np.uint8)
    frame_john[100:300, 200:320] = (20, 30, 220)  # BGR: Red
    box_john = (200, 100, 320, 300)

    # Person B (Mary) - White/Green clothing pattern
    frame_mary = np.zeros((480, 640, 3), dtype=np.uint8)
    frame_mary[100:300, 400:520] = (220, 220, 40) # BGR: Cyan/White
    box_mary = (400, 100, 520, 300)

    # Person A appears as track 1
    coord.process_person_appearance(cam1, 1, t0, frame_john, box_john)
    gid_john_cam1 = coord.get_global_id(cam1, 1)
    coord.register_active_person(cam1, 1, t0, 65.0, "HIGH", ["SUDDEN_SPRINT"], [], box_john, frame_john)

    # Person B appears as track 2 in the same camera at the same time
    coord.process_person_appearance(cam1, 2, t0, frame_mary, box_mary)
    gid_mary_cam1 = coord.get_global_id(cam1, 2)
    coord.register_active_person(cam1, 2, t0, 10.0, "LOW", [], [], box_mary, frame_mary)

    print(f"[Cam 1] Person A (John) Global ID: {gid_john_cam1}")
    print(f"[Cam 1] Person B (Mary) Global ID: {gid_mary_cam1}")

    # VERIFY RULE 1: Distinct people on the same camera MUST have distinct Global IDs!
    assert gid_john_cam1 != gid_mary_cam1, f"Person A and B must NOT share an ID! Got {gid_john_cam1} for both"
    assert gid_john_cam1 == "G1"
    assert gid_mary_cam1 == "G2"

    # -------------------------------------------------------------
    # 2. Person A (John) leaves Camera 1 into blind spot (Risk=65.0)
    # -------------------------------------------------------------
    coord.register_track_loss(cam1, 1, t0 + 1.0, 65.0, "HIGH", ["SUDDEN_SPRINT"], [], box_john)
    assert "G1" in coord.in_transit, "John (G1) must be in blind spot in-transit cache"

    # -------------------------------------------------------------
    # 3. Person A (John) enters Camera 2 after 2.0s (local tracker calls him 15)
    # -------------------------------------------------------------
    t1 = t0 + 3.0
    cam2 = "cam_phone_live_2"

    # Same red shirt profile on Camera 2
    frame_john_cam2 = np.zeros((480, 640, 3), dtype=np.uint8)
    frame_john_cam2[110:300, 180:300] = (22, 35, 215) # BGR: Red
    box_john_cam2 = (180, 110, 300, 300)

    ho_john = coord.process_person_appearance(cam2, 15, t1, frame_john_cam2, box_john_cam2)
    assert ho_john is not None, "Coordinator MUST match John (G1) across cameras!"
    gid_john_cam2 = coord.get_global_id(cam2, 15)
    print(f"[Cam 2] John (Track 15) successfully linked to Global ID: {gid_john_cam2}")

    # VERIFY RULE 2: Same person gets the SAME Global ID on the new camera!
    assert gid_john_cam2 == "G1", f"John must remain G1 on Camera 2! Got {gid_john_cam2}"

    # -------------------------------------------------------------
    # 4. A completely new person (Person C, Alex, wearing dark blue) enters Camera 2
    # -------------------------------------------------------------
    frame_alex = np.zeros((480, 640, 3), dtype=np.uint8)
    frame_alex[100:300, 350:470] = (150, 40, 20)  # BGR: Blue
    box_alex = (350, 100, 470, 300)

    ho_alex = coord.process_person_appearance(cam2, 16, t1 + 0.5, frame_alex, box_alex)
    gid_alex_cam2 = coord.get_global_id(cam2, 16)
    print(f"[Cam 2] Person C (Alex, Track 16) assigned Global ID: {gid_alex_cam2}")

    # VERIFY RULE 3: New person MUST NOT be given John's ID (G1)!
    assert gid_alex_cam2 != "G1", f"Alex must NOT be given John's ID G1! Got {gid_alex_cam2}"
    assert gid_alex_cam2 == "G3", f"Alex should be G3! Got {gid_alex_cam2}"

    # -------------------------------------------------------------
    # 5. Person B (Mary) leaves Camera 1 and enters Camera 2
    # -------------------------------------------------------------
    coord.register_track_loss(cam1, 2, t1 + 1.0, 10.0, "LOW", [], [], box_mary)
    assert "G2" in coord.in_transit

    # Mary enters Camera 2 (white/cyan shirt) as track 17
    t2 = t1 + 2.5
    frame_mary_cam2 = np.zeros((480, 640, 3), dtype=np.uint8)
    frame_mary_cam2[100:300, 50:170] = (215, 215, 38)
    box_mary_cam2 = (50, 100, 170, 300)

    ho_mary = coord.process_person_appearance(cam2, 17, t2, frame_mary_cam2, box_mary_cam2)
    assert ho_mary is not None, "Coordinator MUST match Mary (G2) across cameras!"
    gid_mary_cam2 = coord.get_global_id(cam2, 17)
    print(f"[Cam 2] Mary (Track 17) successfully linked to Global ID: {gid_mary_cam2}")

    # VERIFY RULE 4: Mary remains G2 on Camera 2!
    assert gid_mary_cam2 == "G2", f"Mary must remain G2 on Camera 2! Got {gid_mary_cam2}"

    print("\n>>> ALL TESTS PASSED! Distinct people have distinct IDs (G1, G2, G3) AND each person keeps their single ID across cameras! <<<")

if __name__ == "__main__":
    test_unified_cross_cam_identity()
