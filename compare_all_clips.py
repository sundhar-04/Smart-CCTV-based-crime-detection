import sys, os
sys.path.insert(0, r'd:\Doom\Smart-CCTV-based-crime-detection\smartcctv\w')
from verify_pipeline import run_clip

clips = [
    ("Clip 1: Assault (JOB-E8807273)", r"d:\Doom\Smart-CCTV-based-crime-detection\backend\uploads\JOB-E8807273_Ravi_crime.mp4", 240),
    ("Clip 2: Normal Walking (vtest.avi)", r"d:\Doom\Smart-CCTV-based-crime-detection\smartcctv\w\data\vtest.avi", 300),
    ("Clip 3: Crowd Walking (GettyImages)", r"d:\Doom\Smart-CCTV-based-crime-detection\backend\uploads\JOB-161E10F0_gettyimages-1995820194-640_adpp.mp4", 300),
]

v_types = {'FIGHT_SUSPECTED', 'PHYSICAL_STRIKE', 'VIOLENT_SWING', 'OVERHEAD_STANCE', 'KNOCKOUT_FALL', 'PERSON_DOWN'}

print("\n================== 3-CLIP VERIFICATION SUMMARY ==================")
for name, path, max_f in clips:
    fl, al = run_clip(path, max_frames=max_f)
    v_alerts = [a for a in al if any(t in str(a.get('reasons', [])) for t in v_types)]
    print(f"\n>>> {name}")
    print(f"Total frames processed: {len(fl)}")
    print(f"Total alerts: {len(al)}, Violence alerts: {len(v_alerts)}")
    if al:
        seen = set()
        for a in al:
            key = (a['entity'], tuple(a['reasons']), a['status'])
            if key not in seen:
                seen.add(key)
                print(f"  Entity: {a['entity']} | Score: {a['score']} | Status: {a['status']} | Reasons: {a['reasons']}")
    else:
        print("  (No alerts fired)")
