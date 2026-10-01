"""
SmartCCTV Camera Stream Ingestion & Processing Manager
Consumes live IP / mobile phone camera streams (HTTP, MJPEG, RTSP).
Integrates directly with SmartCCTV's core detection, tracking, risk, and alert pipeline.
"""

import os
import sys
import time
import json
import threading
import logging
import cv2
import numpy as np
from typing import Dict, Optional, Any, Tuple

# Add smartcctv package parent directory to sys.path
W_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "smartcctv", "w"))
if W_DIR not in sys.path:
    sys.path.insert(0, W_DIR)

from backend.database import get_db
from backend.ws import ws_manager
from backend.cross_cam_coordinator import cross_camera_coordinator

logger = logging.getLogger("smartcctv.cameras")

# Lazy-loaded pipeline components
_PIPELINE_LOADED = False
_MODEL_LOCK = threading.Lock()
_DETECTOR = None
_POSE_DETECTOR = None
_WEAPON_DETECTOR = None

def get_shared_models():
    """Lazily load shared neural network models once to prevent redundant VRAM allocation."""
    global _PIPELINE_LOADED, _DETECTOR, _POSE_DETECTOR, _WEAPON_DETECTOR
    if not _PIPELINE_LOADED:
        with _MODEL_LOCK:
            if not _PIPELINE_LOADED:
                try:
                    from smartcctv.detector_yolo8 import YoloDetector
                    _DETECTOR = YoloDetector()
                except Exception as e:
                    logger.warning(f"[CAMERA_MGR] Could not load YoloDetector: {e}")
                    _DETECTOR = None

        try:
            from smartcctv.pose_violence import PoseViolenceDetector
            _POSE_DETECTOR = PoseViolenceDetector()
        except Exception as e:
            logger.warning(f"[CAMERA_MGR] Could not load PoseViolenceDetector: {e}")
            _POSE_DETECTOR = None

        try:
            from smartcctv.weapon_detector import WeaponDetector
            _WEAPON_DETECTOR = WeaponDetector()
        except Exception as e:
            logger.warning(f"[CAMERA_MGR] Could not load WeaponDetector: {e}")
            _WEAPON_DETECTOR = None

        _PIPELINE_LOADED = True

    return _DETECTOR, _POSE_DETECTOR, _WEAPON_DETECTOR


def normalize_stream_url(url: str) -> str:
    """Normalize phone camera URLs (auto-appending /video, adding http://, fixing .8080 typos)."""
    url = (url or "").strip()
    if not url:
        return ""

    import re
    # Fix accidental dot instead of colon before port: 192.168.1.50.8080 -> 192.168.1.50:8080
    url = re.sub(r"(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\.(\d{4,5})", r"\1:\2", url)

    # Prepend http:// if user entered IP:PORT directly
    if not url.startswith(("http://", "https://", "rtsp://")):
        url = f"http://{url}"

    try:
        from urllib.parse import urlparse, urlunparse
        p = urlparse(url)
        if p.scheme in ("http", "https") and p.netloc:
            path = p.path.rstrip("/")
            if not path:
                if p.port in (8080, 4747, 8081) or ":8080" in p.netloc or ":4747" in p.netloc:
                    return urlunparse((p.scheme, p.netloc, "/video", "", "", ""))
    except Exception:
        pass
    return url


class CameraStreamWorker:
    """
    Dedicated background worker thread for an active camera stream (e.g. mobile phone, RTSP/IP cam).
    Provides robust auto-reconnection, actual frame decoding, and SmartCCTV pipeline ingestion.
    """

    def __init__(self, cam_data: dict):
        self.cam_id = str(cam_data["id"])
        self.name = str(cam_data.get("name", self.cam_id))
        raw_url = cam_data.get("stream_url") or cam_data.get("rtsp_url") or ""
        self.stream_url = normalize_stream_url(raw_url)
        self.protocol = str(cam_data.get("protocol", "mjpeg")).lower()
        self.location = str(cam_data.get("location", "Unassigned"))
        self.enabled = bool(cam_data.get("enabled", True))
        self.target_fps = float(cam_data.get("fps", 25.0))
        self.zones = cam_data.get("zones", {})

        # Status: "CONNECTED", "CONNECTING", "DISCONNECTED", "ERROR"
        self.status = "CONNECTING" if self.enabled and self.stream_url else "DISCONNECTED"
        self.error_message: Optional[str] = None
        self.last_seen: Optional[float] = None
        self.actual_fps: float = 0.0

        # Frame buffers
        self.lock = threading.Lock()
        self.latest_frame: Optional[np.ndarray] = None
        self.latest_jpeg: Optional[bytes] = None
        self.latest_detections: list = []
        self.latest_risk_score: float = 0.0
        self._active_incidents: dict = {}  # entity -> dict(id, time, level, types)
        self._recent_camera_incident: Optional[dict] = None  # active incident across all tracks on this camera

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._cap: Optional[cv2.VideoCapture] = None

    def start(self):
        """Start worker thread if enabled and stream_url is provided."""
        if not self.enabled or not self.stream_url:
            self.status = "DISCONNECTED"
            return
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, name=f"CamWorker-{self.cam_id}", daemon=True)
        self._thread.start()
        logger.info(f"[{self.cam_id}] Stream worker started for URL: {self.stream_url}")

    def stop(self):
        """Stop worker thread and release resources."""
        self._running = False
        if self._cap:
            try:
                self._cap.release()
            except Exception:
                pass
            self._cap = None
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self.status = "DISCONNECTED"
        logger.info(f"[{self.cam_id}] Stream worker stopped.")

    def get_snapshot(self) -> Tuple[bytes, str, int]:
        """Returns the actual live JPEG frame from the camera stream, or a status overlay frame."""
        with self.lock:
            if self.latest_jpeg is not None and self.status == "CONNECTED":
                return self.latest_jpeg, "image/jpeg", 200

        # Render status placeholder frame with actual connection state
        img = np.zeros((480, 640, 3), dtype=np.uint8)
        cv2.rectangle(img, (0, 0), (640, 480), (18, 22, 28), -1)

        # Subtle grid lines
        for x in range(0, 640, 64):
            cv2.line(img, (x, 0), (x, 480), (28, 34, 42), 1)
        for y in range(0, 480, 48):
            cv2.line(img, (0, y), (640, y), (28, 34, 42), 1)

        t_str = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
        status_color = (0, 220, 100) if self.status == "CONNECTED" else (0, 165, 255) if self.status == "CONNECTING" else (80, 80, 240)

        cv2.putText(img, f"{self.name.upper()} ({self.cam_id})", (24, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (255, 255, 255), 2)
        cv2.putText(img, f"STATUS: {self.status}", (24, 85), cv2.FONT_HERSHEY_SIMPLEX, 0.65, status_color, 2)
        cv2.putText(img, f"STREAM: {self.stream_url or 'Not configured'}", (24, 120), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (160, 170, 180), 1)

        if self.error_message:
            err_text = self.error_message[:65]
            cv2.putText(img, f"NOTE: {err_text}", (24, 150), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (100, 100, 255), 1)

        cv2.putText(img, "Reconnecting automatically..." if self.status in ("CONNECTING", "DISCONNECTED") else "", (24, 430), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (180, 180, 180), 1)
        cv2.putText(img, t_str, (24, 460), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (120, 130, 140), 1)

        ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 80])
        return (buf.tobytes() if ok else b""), "image/jpeg", 200

    def get_health(self) -> dict:
        """Returns health state of this camera stream."""
        return {
            "camera_id": self.cam_id,
            "name": self.name,
            "status": self.status,
            "stream_url": self.stream_url,
            "protocol": self.protocol,
            "fps": round(self.actual_fps, 1),
            "last_seen": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.last_seen)) if self.last_seen else None,
            "error": self.error_message
        }

    def _run_loop(self):
        """Primary ingestion thread loop with bounded retry/backoff and pipeline integration."""
        retry_delay = 1.0
        max_retry_delay = 8.0

        # Initialize SmartCCTV tracking & risk engine for this camera
        eng = None
        trk = None
        try:
            from smartcctv.risk import RiskEngine, classify_risk_level
            from smartcctv.tracker import RobustRealtimeTracker

            cfg = {
                "camera_id": self.cam_id,
                "zones": self.zones if isinstance(self.zones, dict) else {},
                "params": {"thr": 35, "cooldown": 3, "alert_budget_per_hour": 1000}
            }
            eng = RiskEngine(cfg, fps=self.target_fps)
            trk = RobustRealtimeTracker(max_lost=int(self.target_fps * 2))
        except Exception as e:
            logger.warning(f"[{self.cam_id}] Could not initialize risk engine: {e}")

        detector, pose_detector, weapon_detector = get_shared_models()

        while self._running:
            # Step 1: Network reachability check for remote stream URLs
            if self.stream_url.startswith(("http://", "https://", "rtsp://")):
                try:
                    import socket
                    from urllib.parse import urlparse
                    parsed = urlparse(self.stream_url)
                    host = parsed.hostname
                    port = parsed.port or (554 if self.stream_url.startswith("rtsp://") else 80)
                    if host:
                        s = socket.create_connection((host, port), timeout=1.5)
                        s.close()
                except Exception as sock_err:
                    self.status = "DISCONNECTED"
                    self.error_message = f"Host {host}:{port} unreachable on local network."
                    self._broadcast_status()
                    time.sleep(retry_delay)
                    retry_delay = min(retry_delay * 1.5, max_retry_delay)
                    continue

            # Step 2: Open stream
            self.status = "CONNECTING"
            self._broadcast_status()

            # Enable aggressive zero-latency ffmpeg options for all streams (RTSP & HTTP MJPEG)
            os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = (
                "rtsp_transport;udp|rtsp_transport;tcp|"
                "fflags;nobuffer|"
                "flags;low_delay|"
                "probesize;32|"
                "analyzeduration;0|"
                "max_delay;0|"
                "reorder_queue_size;0|"
                "timeout;4000000|"
                "threads;1"
            )

            is_http = self.stream_url.startswith(("http://", "https://"))
            cap = None

            if not is_http:
                cap = cv2.VideoCapture(self.stream_url)
                self._cap = cap
                if hasattr(cv2, "CAP_PROP_OPEN_TIMEOUT_MSEC"):
                    cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 4000)
                if hasattr(cv2, "CAP_PROP_READ_TIMEOUT_MSEC"):
                    cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, 4000)
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

                if not cap.isOpened():
                    self.status = "DISCONNECTED"
                    self.error_message = f"Could not connect to {self.stream_url}. Waiting to retry."
                    self._broadcast_status()
                    cap.release()
                    self._cap = None
                    time.sleep(retry_delay)
                    retry_delay = min(retry_delay * 1.5, max_retry_delay)
                    continue

            # Step 2: Stream ingestion loop with decoupled zero-buffer grabber
            logger.info(f"[{self.cam_id}] Stream connected successfully ({self.stream_url})")
            self.status = "CONNECTED"
            self.error_message = None
            retry_delay = 1.0
            self._broadcast_status()

            raw_frame_lock = threading.Lock()
            grabber_state = {"frame": None, "ts": 0.0, "active": True}

            frame_count = 0
            fps_start = time.time()

            def _grabber_loop():
                nonlocal frame_count, fps_start
                # Direct zero-latency MJPEG socket parser for HTTP streams (IP Webcam on Wi-Fi)
                if is_http:
                    import urllib.request
                    import socket
                    try:
                        req = urllib.request.Request(self.stream_url, headers={"User-Agent": "SmartCCTV/2.0", "Connection": "close"})
                        stream = urllib.request.urlopen(req, timeout=4.0)

                        # Configure underlying socket for zero delay and minimal OS receive buffer (prevents Wi-Fi lag build-up)
                        try:
                            raw_sock = getattr(stream.fp, 'raw', None)
                            if raw_sock and hasattr(raw_sock, '_sock'):
                                sock = raw_sock._sock
                                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                                sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 65536)
                        except Exception:
                            pass

                        buf = bytearray()
                        while self._running and grabber_state["active"]:
                            # Read in larger 64KB blocks for line-rate streaming
                            chunk = stream.read(65536)
                            if not chunk:
                                grabber_state["active"] = False
                                break
                            buf.extend(chunk)

                            # Purge stale network backlog: if data accumulates due to Wi-Fi jitter, jump to latest frame
                            if len(buf) > 300000:
                                last_start = buf.rfind(b'\xff\xd8')
                                if last_start != -1 and last_start > 0:
                                    del buf[:last_start]

                            # Find the latest complete JPEG in the buffer
                            end_idx = buf.rfind(b'\xff\xd9')
                            if end_idx != -1:
                                start_idx = buf[:end_idx].rfind(b'\xff\xd8')
                                if start_idx != -1 and end_idx > start_idx:
                                    jpg = bytes(buf[start_idx:end_idx + 2])
                                    # Discard everything up to and including this frame to guarantee zero latency
                                    del buf[:end_idx + 2]
                                    fr = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)
                                    if fr is not None and fr.size > 0:
                                        now_ts = time.time()
                                        with raw_frame_lock:
                                            grabber_state["frame"] = fr
                                            grabber_state["ts"] = now_ts
                                        frame_count += 1
                                        if frame_count >= 25:
                                            dt = now_ts - fps_start
                                            if dt > 0:
                                                self.actual_fps = frame_count / dt
                                            frame_count = 0
                                            fps_start = now_ts
                    except Exception as http_err:
                        logger.debug(f"[{self.cam_id}] Direct HTTP stream reader: {http_err}")
                        grabber_state["active"] = False
                    return

                # Standard OpenCV grabber for RTSP/hardware cameras with queue drainage
                while self._running and grabber_state["active"]:
                    ok = cap.grab()
                    if not ok:
                        grabber_state["active"] = False
                        break
                    ok, fr = cap.retrieve()
                    if not ok or fr is None or fr.size == 0:
                        continue
                    now_ts = time.time()
                    with raw_frame_lock:
                        grabber_state["frame"] = fr
                        grabber_state["ts"] = now_ts

                    # Measure actual incoming streaming FPS
                    frame_count += 1
                    if frame_count >= 25:
                        dt = now_ts - fps_start
                        if dt > 0:
                            self.actual_fps = frame_count / dt
                        frame_count = 0
                        fps_start = now_ts

            def _display_loop():
                """Dedicated display encoder running at capped rate without blocking frame ingestion."""
                last_disp_ts = 0.0
                while self._running and grabber_state["active"]:
                    with raw_frame_lock:
                        fr = grabber_state["frame"]
                        ts = grabber_state["ts"]

                    if fr is None or ts == last_disp_ts:
                        time.sleep(0.003)
                        continue
                    last_disp_ts = ts

                    try:
                        orig_h, orig_w = fr.shape[:2]
                        target_w = 640 if orig_w > 640 else orig_w
                        target_h = int(orig_h * (target_w / orig_w))
                        disp_fr = cv2.resize(fr, (target_w, target_h), interpolation=cv2.INTER_LINEAR)

                        with self.lock:
                            dets = list(self.latest_detections)
                            cur_risk = getattr(self, "latest_risk_score", 0.0)
                            self.latest_frame = fr

                        if dets:
                            sx = target_w / orig_w
                            sy = target_h / orig_h
                            for d in dets:
                                b = d.get("box")
                                if b and len(b) == 4:
                                    x1, y1 = int(b[0] * sx), int(b[1] * sy)
                                    x2, y2 = int(b[2] * sx), int(b[3] * sy)
                                    cname = d.get("cls", "person")
                                    tid = d.get("id", "")
                                    sc = float(d.get("risk_score", 0.0))
                                    sigs = d.get("signals", [])

                                    # Refined threat classification:
                                    critical_sigs = set(sigs) & {"PHYSICAL_STRIKE", "KNOCKOUT_FALL"}
                                    is_critical_violence = bool(critical_sigs)
                                    is_critical_weapon = ("WEAPON_NEAR_PERSON" in sigs) or (cname.lower() in ("gun", "knife", "baseball bat", "weapon"))

                                    is_sprint = "SUDDEN_SPRINT" in sigs or "RUNNING" in sigs
                                    elevated_sigs = set(sigs) & {
                                        "FIGHT_SUSPECTED", "AGGRESSIVE_APPROACH", "SUDDEN_SPRINT",
                                        "RUNNING", "VIOLENT_SWING", "OVERHEAD_STANCE", "PERSON_DOWN"
                                    }
                                    is_elevated = bool(elevated_sigs)

                                    if is_critical_violence or is_critical_weapon:
                                        col = (50, 50, 240)    # BGR Red (CRITICAL)
                                        box_thick = 3
                                    elif is_sprint or is_elevated or sc >= 40:
                                        col = (0, 140, 255)    # BGR Orange (ELEVATED / SPRINT / SUSPICIOUS)
                                        box_thick = 2
                                    elif sc >= 20:
                                        col = (0, 220, 255)    # BGR Yellow (CAUTION)
                                        box_thick = 2
                                    else:
                                        col = (46, 204, 113)   # BGR Green (NORMAL / SAFE)
                                        box_thick = 1

                                    cv2.rectangle(disp_fr, (x1, y1), (x2, y2), col, box_thick)

                                    gid = d.get("global_id")
                                    if not gid:
                                        gid = f"G{tid}" if str(tid).isdigit() else str(tid)
                                    ho = d.get("handoff")

                                    if cname.lower() != "person":
                                        label = f"{cname.upper()}"
                                    elif ho:
                                        fc = ho["from_camera"].replace("cam_", "").replace("_live", "").upper()
                                        label = f"[{gid} FROM {fc}] r={sc:.0f}"
                                    elif is_critical_weapon:
                                        label = f"[{gid} ARMED] r={sc:.0f}"
                                    elif is_critical_violence:
                                        v_sig = next(iter(critical_sigs))
                                        label = f"[{gid} {v_sig}] r={sc:.0f}"
                                    elif is_sprint:
                                        s_tag = "SPRINT" if "SUDDEN_SPRINT" in sigs else "RUN"
                                        label = f"[{gid} {s_tag}] r={sc:.0f}"
                                    elif is_elevated:
                                        e_sig = next(iter(elevated_sigs))
                                        label = f"[{gid} {e_sig}] r={sc:.0f}"
                                    elif sc >= 15.0:
                                        label = f"[{gid} SUSPECT] r={sc:.0f}"
                                    elif sc > 0:
                                        label = f"[{gid}] r={sc:.0f}"
                                    else:
                                        label = f"[{gid}]"

                                    (lw, lh), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
                                    cv2.rectangle(disp_fr, (x1, max(0, y1 - lh - 6)), (x1 + lw + 6, y1), (15, 18, 24), -1)
                                    cv2.rectangle(disp_fr, (x1, max(0, y1 - lh - 6)), (x1 + lw + 6, y1), col, 1)
                                    cv2.putText(disp_fr, label, (x1 + 3, max(lh + 2, y1 - 3)), cv2.FONT_HERSHEY_SIMPLEX, 0.42, col, 1, cv2.LINE_AA)

                        # Top HUD overlay for live analytics status
                        hud_col = (50, 50, 240) if cur_risk >= 75 else (0, 140, 255) if cur_risk >= 30 else (10, 12, 16)
                        cv2.rectangle(disp_fr, (0, 0), (disp_fr.shape[1], 24), hud_col, -1)
                        hud_text = f"LIVE | FPS: {self.actual_fps:.1f} | RISK: {cur_risk:.1f}"
                        if cur_risk >= 75:
                            hud_text += " [!] CRITICAL THREAT DETECTED"
                        elif cur_risk >= 30:
                            hud_text += " [*] ELEVATED ACTIVITY"
                        else:
                            hud_text += " [OK] NORMAL / SECURE"
                        cv2.putText(disp_fr, hud_text, (10, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (255, 255, 255), 1, cv2.LINE_AA)

                        ok_enc, enc = cv2.imencode(".jpg", disp_fr, [cv2.IMWRITE_JPEG_QUALITY, 68])
                        if ok_enc:
                            with self.lock:
                                self.latest_jpeg = enc.tobytes()
                    except Exception as loop_err:
                        logger.debug(f"[{self.cam_id}] Display loop render error: {loop_err}")

                    time.sleep(0.005)

            grabber_t = threading.Thread(target=_grabber_loop, name=f"Grabber-{self.cam_id}", daemon=True)
            grabber_t.start()

            display_t = threading.Thread(target=_display_loop, name=f"Display-{self.cam_id}", daemon=True)
            display_t.start()

            frame_idx = 0
            last_processed_ts = 0.0
            prev_person_ids = set()

            while self._running and grabber_state["active"]:
                with raw_frame_lock:
                    frame = grabber_state["frame"]
                    now_ts = grabber_state["ts"]

                if frame is None or now_ts == last_processed_ts:
                    time.sleep(0.003)
                    continue

                last_processed_ts = now_ts
                frame_idx += 1
                self.last_seen = now_ts

                # Feed into detection cascade asynchronously without blocking live video output
                if detector and eng:
                    try:
                        orig_h, orig_w = frame.shape[:2]
                        if orig_w > 480:
                            scale_infer = 480.0 / orig_w
                            infer_frame = cv2.resize(frame, (480, int(orig_h * scale_infer)), interpolation=cv2.INTER_LINEAR)
                        else:
                            scale_infer = 1.0
                            infer_frame = frame

                        # Dynamic lightweight inference cadence: every 3rd frame when calm, every 2nd on elevated risk
                        is_active_threat = getattr(self, "latest_risk_score", 0.0) >= 25.0
                        infer_stride = 2 if is_active_threat else 3
                        if frame_idx % infer_stride == 0 or is_active_threat:
                            raw_dets = detector(infer_frame)
                            scaled_dets = []
                            for d in raw_dets:
                                if isinstance(d, (list, tuple)) and len(d) >= 6:
                                    scaled_dets.append((d[0]/scale_infer, d[1]/scale_infer, d[2]/scale_infer, d[3]/scale_infer, d[4], d[5]))
                                elif isinstance(d, dict) and "box" in d:
                                    b = d["box"]
                                    scaled_dets.append(dict(d, box=(b[0]/scale_infer, b[1]/scale_infer, b[2]/scale_infer, b[3]/scale_infer)))
                                else:
                                    scaled_dets.append(d)
                            last = trk.update(scaled_dets) if trk else []
                            self._cached_last_dets = last
                        else:
                            last = getattr(self, "_cached_last_dets", [])

                        # Duplicate tracker box suppression
                        if len(last) >= 2:
                            keep = [True] * len(last)
                            for ki in range(len(last)):
                                if not keep[ki]: continue
                                b1, a1 = last[ki]["box"], (last[ki]["box"][2]-last[ki]["box"][0])*(last[ki]["box"][3]-last[ki]["box"][1])
                                for kj in range(ki + 1, len(last)):
                                    if not keep[kj] or last[ki]["cls"] != last[kj]["cls"]: continue
                                    b2, a2 = last[kj]["box"], (last[kj]["box"][2]-last[kj]["box"][0])*(last[kj]["box"][3]-last[kj]["box"][1])
                                    dx = min(b1[2], b2[2]) - max(b1[0], b2[0])
                                    dy = min(b1[3], b2[3]) - max(b1[1], b2[1])
                                    if dx > 0 and dy > 0 and (dx * dy) / max(min(a1, a2), 1.0) > 0.70:
                                        if a1 >= a2: keep[kj] = False
                                        else: keep[ki] = False; break
                            last = [p for p, k in zip(last, keep) if k]

                        persons = [x for x in last if x["cls"] == "person"]
                        current_person_ids = {p["id"] for p in persons}

                        # 1. Detect and register track loss (person exits camera coverage into blind spot)
                        lost_person_ids = prev_person_ids - current_person_ids
                        for lost_id in lost_person_ids:
                            pk_lost = f"{self.cam_id}:P{lost_id}"
                            sc_lost, sigs_lost = eng.score(pk_lost, now_ts)
                            evs_lost = eng.events.get(pk_lost, [])
                            box_lost = eng.lastbox.get(pk_lost)
                            r_lost = classify_risk_level(sc_lost, sigs_lost)
                            cross_camera_coordinator.register_track_loss(
                                self.cam_id, lost_id, now_ts, sc_lost, r_lost, sigs_lost, evs_lost, box_lost
                            )
                        prev_person_ids = current_person_ids

                        # 2. Check for cross-camera handoff & inherit past risk score/events
                        for p in persons:
                            ho = cross_camera_coordinator.process_person_appearance(
                                self.cam_id, p["id"], now_ts, frame, p["box"]
                            )
                            if ho:
                                pk = f"{self.cam_id}:P{p['id']}"
                                eng.inherit_events(pk, ho.get("events", []), now_ts)
                                p["handoff"] = ho
                                ws_manager.broadcast_sync({
                                    "event": "cross_cam_handoff",
                                    "data": ho
                                })

                        # Secondary cascade: Pose Violence (strikes, violent swings, brandishing)
                        has_active_threat = any(d.get("risk_score", 0.0) >= 30 for d in last)
                        if pose_detector and persons and (frame_idx % 2 == 0 or has_active_threat):
                            infer_persons = [dict(p, box=tuple(coord * scale_infer for coord in p["box"])) for p in persons]
                            for pev in pose_detector.analyze(infer_frame, now_ts, infer_persons):
                                pk = f"{self.cam_id}:P{pev['track_id']}"
                                eng.emit(pk, pev["type"], now_ts)

                        # Dedicated Weapon Cascade (runs every 3 frames or if weapons are actively in view)
                        has_active_weapons = any("weapon" in d.get("cls", "").lower() or d.get("cls") in ("Gun", "Weapon") for d in last)
                        if weapon_detector and persons and (frame_idx % 3 == 0 or has_active_weapons):
                            infer_persons = [dict(p, box=tuple(coord * scale_infer for coord in p["box"])) for p in persons]
                            for wd in weapon_detector.detect(infer_frame, infer_persons, t=now_ts):
                                if wd.get("person_id") is not None:
                                    pk = f"{self.cam_id}:P{wd['person_id']}"
                                    eng.emit(pk, "WEAPON_NEAR_PERSON", now_ts)

                        # Risk accumulation & Alert check
                        generated = eng.update(now_ts, last)
                        if generated:
                            self._handle_alerts(generated)

                        # Calculate individual risk score and signals for each tracked person
                        cur_peak = 0.0
                        annotated_dets = []
                        for x in last:
                            pk = f"{self.cam_id}:{'O' if x['cls'] != 'person' else 'P'}{x['id']}"
                            sc, sig_types = eng.score(pk, now_ts)
                            if sc > cur_peak:
                                cur_peak = sc
                            d_copy = dict(x)
                            d_copy["risk_score"] = round(float(sc), 1)
                            d_copy["signals"] = sorted(sig_types) if sig_types else []

                            if x["cls"] == "person":
                                r_level = classify_risk_level(sc, sig_types)
                                evs = eng.events.get(pk, [])
                                # Continuously register active person state with coordinator
                                gid = cross_camera_coordinator.register_active_person(
                                    self.cam_id, x["id"], now_ts, sc, r_level, sig_types, evs, x.get("box"), frame
                                )


                                # Expose unified Global ID (e.g. G1) everywhere
                                d_copy["id"] = gid
                                d_copy["track_id"] = gid
                                d_copy["local_id"] = x["id"]
                                d_copy["global_id"] = gid
                            else:
                                d_copy["global_id"] = f"OBJ-{x['id']}"

                            if "handoff" in x:
                                d_copy["handoff"] = x["handoff"]

                            annotated_dets.append(d_copy)

                        with self.lock:
                            self.latest_detections = annotated_dets
                            self.latest_risk_score = cur_peak

                    except Exception as e:
                        logger.debug(f"[{self.cam_id}] Detection step skipped: {e}")

                time.sleep(0.003)

            grabber_state["active"] = False
            if grabber_t.is_alive():
                grabber_t.join(timeout=1.0)
            if display_t.is_alive():
                display_t.join(timeout=1.0)
            cap.release()
            self.status = "DISCONNECTED"
            self.error_message = "Stream interrupted or disconnected by remote source."
            self._broadcast_status()
            time.sleep(retry_delay)
            retry_delay = min(retry_delay * 1.5, max_retry_delay)

    def _handle_alerts(self, alerts: list):
        """Persist generated camera alerts and broadcast immediately via WebSocket with deduplication."""
        try:
            conn = get_db()
            cursor = conn.cursor()
            now_t = time.time()
            from smartcctv.risk import classify_risk_level

            for al in alerts:
                raw_ent = al.get("entity", "P1")
                local_tid = -1
                if ":P" in raw_ent:
                    try:
                        local_tid = int(raw_ent.split(":P")[-1])
                    except Exception:
                        pass
                elif raw_ent.startswith("P") and raw_ent[1:].isdigit():
                    local_tid = int(raw_ent[1:])
                elif raw_ent.isdigit():
                    local_tid = int(raw_ent)

                gid = cross_camera_coordinator.get_global_id(self.cam_id, local_tid) if local_tid != -1 else raw_ent
                entity = gid

                score = float(al.get("score", 50.0))
                types = al.get("types", ["INTRUSION"])
                reasons = al.get("reasons", ["Activity detected on camera"])

                # Strict crime threshold: require score >= 70.0 for any audible/toast crime alert
                if score < 70.0:
                    continue

                # Filter out routine motion signals (sprints, transitions, walking, loitering)
                violent_signals = {"PHYSICAL_STRIKE", "KNOCKOUT_FALL", "VIOLENT_SWING", "FIGHT_SUSPECTED", "WEAPON_NEAR_PERSON"}
                has_actual_violence = bool(set(types) & violent_signals)
                if not has_actual_violence:
                    # Running, sprinting between cameras, or moving does not produce alerts
                    continue

                r_level = classify_risk_level(score, types, reasons)

                # Suppress alerts for persons identified across cameras:
                # If a person arrived via cross-camera handover, they are tracked on HUD but do NOT trigger new alerts
                # unless an active severe strike occurs directly on this camera view
                g_info = cross_camera_coordinator.entities.get(gid)
                if g_info and g_info.get("handoff_count", 0) > 0:
                    has_live_strike = bool(set(types) & {"PHYSICAL_STRIKE", "KNOCKOUT_FALL"})
                    if not has_live_strike:
                        continue

                # Deduplication check & cooldown (global across cameras for the same subject):
                if not hasattr(cross_camera_coordinator, "_active_global_incidents"):
                    cross_camera_coordinator._active_global_incidents = {}

                last_info = self._active_incidents.get(gid) or cross_camera_coordinator._active_global_incidents.get(gid)
                cam_info = getattr(self, "_recent_camera_incident", None)

                target_incident = None
                if last_info and (now_t - last_info["time"] < 120.0):
                    target_incident = last_info
                elif cam_info and (now_t - cam_info["time"] < 120.0):
                    target_incident = cam_info

                if target_incident:
                    # Check for genuine escalation to violence strike (e.g. from elevated/high to critical strike)
                    has_escalation = (r_level == "CRITICAL" and target_incident.get("level") != "CRITICAL")
                    if not has_escalation:
                        # Same ongoing incident across cameras: update score, location, and timestamp quietly without alert spam
                        existing_aid = target_incident["id"]
                        cursor.execute("""
                            UPDATE alerts 
                            SET camera_id = ?,
                                camera_name = ?,
                                location = ?,
                                risk_score = MAX(risk_score, ?),
                                timestamp = ?
                            WHERE id = ?
                        """, (self.cam_id, self.name, self.location, score, now_t, existing_aid))
                        target_incident["time"] = now_t
                        target_incident["score"] = max(target_incident.get("score", 0.0), score)
                        self._active_incidents[gid] = target_incident
                        cross_camera_coordinator._active_global_incidents[gid] = target_incident
                        self._recent_camera_incident = target_incident
                        continue

                # New incident or critical violence escalation
                aid = f"ALT-{self.cam_id[:4].upper()}-{int(now_t * 1000) % 1000000}"
                incident_record = {
                    "id": aid,
                    "time": now_t,
                    "level": r_level,
                    "types": set(types),
                    "score": score
                }
                self._active_incidents[gid] = incident_record
                cross_camera_coordinator._active_global_incidents[gid] = incident_record
                self._recent_camera_incident = incident_record

                cursor.execute("""
                    INSERT OR REPLACE INTO alerts
                    (id, timestamp, camera_id, camera_name, location, risk_score, risk_level, status, types, reasons, zone, entity, clip_sha256, evidence_path, snapshot_url)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    aid, now_t, self.cam_id, self.name, self.location,
                    score, r_level, "active", json.dumps(types), json.dumps(reasons),
                    al.get("zone", "Unzoned"), gid, "", "", f"/api/cameras/{self.cam_id}/snapshot"
                ))

                payload = {
                    "id": aid,
                    "camera_id": self.cam_id,
                    "camera_name": self.name,
                    "location": self.location,
                    "risk_score": score,
                    "risk_level": r_level,
                    "status": "active",
                    "types": types,
                    "reasons": reasons,
                    "zone": al.get("zone", "Unzoned"),
                    "entity": entity,
                    "snapshot_url": f"/api/cameras/{self.cam_id}/snapshot",
                    "timestamp": now_t
                }
                ws_manager.broadcast_sync({"event": "new_alert", "data": payload})
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"[{self.cam_id}] Error saving alert: {e}")

    def _broadcast_status(self):
        """Update DB and broadcast camera status change."""
        try:
            now_str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("UPDATE cameras SET status = ?, last_seen = ? WHERE id = ?", (self.status, now_str, self.cam_id))
            conn.commit()
            conn.close()

            ws_manager.broadcast_sync({
                "event": "camera_status_changed",
                "data": {
                    "camera_id": self.cam_id,
                    "status": self.status,
                    "fps": round(self.actual_fps, 1),
                    "error": self.error_message
                }
            })
        except Exception:
            pass


class CameraStreamManager:
    """Singleton coordinator managing all live camera stream workers in SmartCCTV."""

    def __init__(self):
        self.workers: Dict[str, CameraStreamWorker] = {}
        self.lock = threading.Lock()

    def start_all(self):
        """Load all enabled cameras from DB and launch ingestion workers."""
        try:
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM cameras")
            rows = cursor.fetchall()
            conn.close()

            with self.lock:
                for r in rows:
                    cam_data = dict(r)
                    cam_id = cam_data["id"]
                    stream_url = cam_data.get("stream_url") or cam_data.get("rtsp_url")
                    enabled = bool(cam_data.get("enabled", 1))

                    if enabled and stream_url:
                        if cam_id not in self.workers:
                            worker = CameraStreamWorker(cam_data)
                            self.workers[cam_id] = worker
                            worker.start()
        except Exception as e:
            logger.error(f"[CAMERA_MGR] Failed to start camera workers: {e}")

    def add_or_update(self, cam_data: dict):
        """Register or update a camera worker immediately."""
        cam_id = str(cam_data["id"])
        with self.lock:
            if cam_id in self.workers:
                self.workers[cam_id].stop()
            worker = CameraStreamWorker(cam_data)
            self.workers[cam_id] = worker
            if worker.enabled and worker.stream_url:
                worker.start()

    def stop_all(self):
        """Cleanly terminate all camera stream workers."""
        with self.lock:
            for cam_id, worker in list(self.workers.items()):
                try:
                    worker.stop()
                except Exception:
                    pass
            self.workers.clear()

    def remove(self, cam_id: str):
        """Stop and remove a camera worker."""
        with self.lock:
            worker = self.workers.pop(cam_id, None)
            if worker:
                worker.stop()

    def get_worker(self, cam_id: str) -> Optional[CameraStreamWorker]:
        return self.workers.get(cam_id)

    def get_snapshot(self, cam_id: str) -> Tuple[bytes, str, int]:
        worker = self.get_worker(cam_id)
        if worker:
            return worker.get_snapshot()

        # Camera exists in DB but not active worker
        img = np.zeros((480, 640, 3), dtype=np.uint8)
        cv2.putText(img, f"CAM: {cam_id} (INACTIVE)", (40, 240), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (120, 120, 120), 2)
        ok, buf = cv2.imencode(".jpg", img)
        return (buf.tobytes() if ok else b""), "image/jpeg", 200

    def test_connection(self, stream_url: str, protocol: str = "mjpeg") -> dict:
        """
        Attempts to open the mobile/IP camera stream URL and verify frame decode.
        Returns status CONNECTED with resolution & FPS if successful, or FAILED with clean error message.
        """
        if not stream_url or not stream_url.strip():
            return {"status": "FAILED", "error": "Stream URL is required."}

        stream_url = normalize_stream_url(stream_url.strip())

        # Fast pre-flight network reachability test for IP/RTSP streams to avoid native thread blocking
        if stream_url.startswith(("http://", "https://", "rtsp://")):
            try:
                import socket
                from urllib.parse import urlparse
                parsed = urlparse(stream_url)
                host = parsed.hostname
                default_port = 554 if stream_url.startswith("rtsp://") else 80
                port = parsed.port or default_port
                if host:
                    s = socket.create_connection((host, port), timeout=2.0)
                    s.close()
            except socket.timeout:
                return {
                    "status": "FAILED",
                    "error": f"Connection timed out reaching {host}:{port}. Ensure phone and server are on the same Wi-Fi network and IP is correct."
                }
            except ConnectionRefusedError:
                return {
                    "status": "FAILED",
                    "error": f"Connection refused by {host}:{port}. Ensure streaming app is actively broadcasting."
                }
            except Exception as e:
                return {
                    "status": "FAILED",
                    "error": f"Cannot reach {host}:{port}: {str(e)}"
                }

        try:
            if protocol.lower() == "rtsp" or stream_url.startswith("rtsp://"):
                os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;udp|rtsp_transport;tcp|timeout;3000000"

            cap = cv2.VideoCapture(stream_url)
            if hasattr(cv2, "CAP_PROP_OPEN_TIMEOUT_MSEC"):
                cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 3500)
            if hasattr(cv2, "CAP_PROP_READ_TIMEOUT_MSEC"):
                cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, 3500)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            if not cap.isOpened():
                cap.release()
                return {
                    "status": "FAILED",
                    "error": f"Unable to open stream at '{stream_url}'. Check that the phone streaming app is actively broadcasting and video format is supported."
                }

            ok, frame = cap.read()
            fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
            cap.release()

            if ok and frame is not None and frame.size > 0:
                h, w = frame.shape[:2]
                return {
                    "status": "CONNECTED",
                    "width": int(w),
                    "height": int(h),
                    "fps": round(float(fps), 1),
                    "error": None
                }
            else:
                return {
                    "status": "FAILED",
                    "error": f"Stream opened at '{stream_url}' but did not yield any video frames."
                }
        except Exception as e:
            return {
                "status": "FAILED",
                "error": f"Connection error: {str(e)}"
            }


# Global singleton instance
camera_manager = CameraStreamManager()
