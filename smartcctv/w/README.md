# SmartCCTV: risk-accumulating, human-confirmed CCTV alerting
Setup: `./setup.sh`  |  Run: `python -m smartcctv.run --config smartcctv/config.json`  |  Review UI: `python -m smartcctv.dashboard out`  |  Tests: `python smartcctv/tests/test_all.py`

Reused (not rewritten): OpenCV DNN + YOLOv4-tiny COCO weights (AlexeyAB/darknet), ByteTrack (supervision 0.30.4), MOG2, Flask.
Original: motion/crop cascade, per-track risk accumulation + alert budget, cross-camera blind-spot linking, evidence hash chain, tamper monitor, feedback loop.
Upgrade path (needs PyTorch): swap `Detector` for a YOLOv8 wrapper with the same `__call__` output; swap `xcam.embed` for OSNet embeddings.
