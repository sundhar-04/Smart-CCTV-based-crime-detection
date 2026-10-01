"""Cross-Camera Person Re-Identification & Risk State Handover Coordinator.
Tracks persons seamlessly across multiple camera views through unmonitored blind spots.
Transfers identity, appearance signature, accumulated risk score, and threat signals.
Ensures a risked person continues with the exact same Global ID (e.g. G1) across all cameras.
"""
import os
import sys
import time
import math
import threading
from collections import deque
from typing import Dict, List, Optional, Tuple, Any
import numpy as np
import logging

# Ensure smartcctv package directory is in sys.path
W_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "smartcctv", "w"))
if W_DIR not in sys.path:
    sys.path.insert(0, W_DIR)

logger = logging.getLogger("smartcctv.cross_cam")

# Safe import of appearance embedder with resilient fallback
try:
    from smartcctv.xcam import embed as _xcam_embed
except Exception:
    import cv2
    def _xcam_embed(frame, box):
        x1, y1, x2, y2 = [max(0, int(v)) for v in box]
        c = frame[y1:y2, x1:x2]
        if c.size == 0:
            return np.zeros(96, dtype=np.float32)
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

def embed(frame: np.ndarray, box: Tuple[float, float, float, float]) -> np.ndarray:
    """Safely extracts a normalized appearance embedding."""
    try:
        e = _xcam_embed(frame, box)
        if e is None or len(e) == 0:
            return np.zeros(96, dtype=np.float32)
        return np.asarray(e, dtype=np.float32)
    except Exception as ex:
        logger.debug(f"[EMBED] Extraction fallback: {ex}")
        return np.zeros(96, dtype=np.float32)

def safe_sim(a: np.ndarray, b: np.ndarray) -> float:
    """Robust similarity calculation that handles differing embedding shapes safely without throwing exceptions."""
    if a is None or b is None:
        return 0.0
    try:
        a_arr = np.asarray(a, dtype=np.float32).flatten()
        b_arr = np.asarray(b, dtype=np.float32).flatten()
        if len(a_arr) == 0 or len(b_arr) == 0:
            return 0.0
        # Align lengths if mismatched
        if len(a_arr) != len(b_arr):
            target_len = min(len(a_arr), len(b_arr))
            a_arr = a_arr[:target_len]
            b_arr = b_arr[:target_len]
        na = np.linalg.norm(a_arr)
        nb = np.linalg.norm(b_arr)
        cos = float(np.dot(a_arr, b_arr) / (na * nb)) if (na > 1e-9 and nb > 1e-9) else 0.0
        bhat = float(np.sqrt(np.maximum(0, a_arr * b_arr)).sum())
        return max(0.0, min(1.0, 0.5 * cos + 0.5 * bhat))
    except Exception:
        return 0.0

sim = safe_sim


class CrossCameraCoordinator:
    """
    Central coordinator managing cross-camera tracking handoffs, person identity unification,
    and risk state preservation.
    """

    def __init__(self, transit_window_s: float = 45.0, sim_threshold: float = 0.28):
        self.transit_window_s = transit_window_s
        self.sim_threshold = sim_threshold
        self.lock = threading.Lock()

        # In-transit subjects who exited a camera coverage:
        # global_id -> dict(global_id, from_cam, exit_t, emb, risk_score, risk_level, signals, events, box)
        self.in_transit: Dict[str, dict] = {}

        # Active Persons of Interest (POIs) across all cameras:
        # global_id -> dict(global_id, cam_id, tid, last_seen, risk_score, risk_level, signals, events, emb, box)
        self.active_pois: Dict[str, dict] = {}

        # Local track mapping: (cam_id, local_tid) -> global_id
        self.track_to_global: Dict[Tuple[str, int], str] = {}

        # Track embeddings cache: (cam_id, local_tid) -> np.ndarray
        self.track_embeddings: Dict[Tuple[str, int], np.ndarray] = {}

        # Global entities registry: global_id -> dict
        self.entities: Dict[str, dict] = {}
        self.next_gid = 1

        # Completed handoff event history for UI & API
        self.handoff_history: deque = deque(maxlen=50)

    def _get_or_create_gid(self, cam_id: str, tid: int) -> str:
        key = (cam_id, tid)
        if key in self.track_to_global:
            return self.track_to_global[key]
        gid = f"G{self.next_gid}"
        self.next_gid += 1
        self.track_to_global[key] = gid
        self.entities[gid] = {
            "global_id": gid,
            "created_at": time.time(),
            "first_camera": cam_id,
            "current_camera": cam_id,
            "max_risk_score": 0.0,
            "handoff_count": 0
        }
        return gid

    def get_global_id(self, cam_id: str, tid: int) -> str:
        """Returns the unified global ID for a camera track, creating one if not present."""
        with self.lock:
            return self._get_or_create_gid(cam_id, tid)

    def register_active_person(
        self,
        cam_id: str,
        tid: int,
        now_ts: float,
        risk_score: float,
        risk_level: str,
        signals: list,
        events: list,
        box: Tuple[float, float, float, float],
        frame: Optional[np.ndarray] = None
    ) -> str:
        """
        Continuously called for active persons on every camera frame.
        Registers them as active POIs if they exhibit risk or elevated motion.
        """
        with self.lock:
            key = (cam_id, tid)
            gid = self.track_to_global.get(key)
            if not gid:
                gid = self._get_or_create_gid(cam_id, tid)

            # Extract or update appearance embedding periodically
            emb = self.track_embeddings.get(key)
            if emb is None and frame is not None and box is not None:
                try:
                    emb = embed(frame, box)
                    self.track_embeddings[key] = emb
                except Exception:
                    pass

            if emb is None:
                emb = np.zeros(96, dtype=np.float32)

            # Update entity metadata
            ent = self.entities.setdefault(gid, {
                "global_id": gid,
                "created_at": now_ts,
                "first_camera": cam_id,
                "handoff_count": 0
            })
            ent["current_camera"] = cam_id
            ent["last_seen"] = now_ts
            ent["max_risk_score"] = max(ent.get("max_risk_score", 0.0), float(risk_score))

            # Maintain active POI record (elevated risk or threat signals)
            has_threat = float(risk_score) >= 15.0 or bool(signals)
            if has_threat:
                self.active_pois[gid] = {
                    "global_id": gid,
                    "cam_id": cam_id,
                    "tid": tid,
                    "last_seen": now_ts,
                    "risk_score": float(risk_score),
                    "risk_level": str(risk_level),
                    "signals": list(signals) if signals else [],
                    "events": list(events) if events else [],
                    "emb": emb,
                    "box": box
                }

            return gid

    def process_person_appearance(
        self,
        cam_id: str,
        tid: int,
        now_ts: float,
        frame: np.ndarray,
        box: Tuple[float, float, float, float]
    ) -> Optional[dict]:
        """
        Called when a person track is newly observed or active in cam_id.
        Matches against in-transit subjects and active POIs from other cameras.
        Returns handoff info dict if a cross-camera handover occurred, else None.
        """
        with self.lock:
            key = (cam_id, tid)

            # Purge expired in-transit subjects (> transit_window_s)
            stale_gids = [
                g for g, info in self.in_transit.items()
                if now_ts - info["exit_t"] > self.transit_window_s
            ]
            for g in stale_gids:
                del self.in_transit[g]

            # Purge expired active POIs (> transit_window_s)
            stale_pois = [
                g for g, info in self.active_pois.items()
                if now_ts - info["last_seen"] > self.transit_window_s
            ]
            for g in stale_pois:
                del self.active_pois[g]

            # If already bound to a global ID, update embedding periodically and return
            if key in self.track_to_global:
                gid = self.track_to_global[key]
                try:
                    new_emb = embed(frame, box)
                    old_emb = self.track_embeddings.get(key)
                    if old_emb is not None:
                        self.track_embeddings[key] = (old_emb * 0.7 + new_emb * 0.3).astype(np.float32)
                    else:
                        self.track_embeddings[key] = new_emb
                except Exception:
                    pass
                return None

            # New appearance: extract visual embedding
            new_emb = embed(frame, box)

            # 1. First priority: Search for in-transit subjects from other cameras
            best_gid = None
            best_score = 0.0
            best_candidate = None

            # Collect candidates from both in_transit and active_pois on OTHER cameras
            candidates = {}
            for gid, ghost in self.in_transit.items():
                if ghost["from_cam"] != cam_id or (now_ts - ghost["exit_t"] <= 4.0):
                    candidates[gid] = dict(ghost, last_t=ghost["exit_t"], origin_cam=ghost["from_cam"])

            for gid, poi in self.active_pois.items():
                if gid not in candidates and poi["cam_id"] != cam_id:
                    candidates[gid] = dict(poi, last_t=poi["last_seen"], origin_cam=poi["cam_id"], from_cam=poi["cam_id"])

            for gid, cand in list(candidates.items()):
                dt = max(0.0, now_ts - cand["last_t"])
                if dt > self.transit_window_s:
                    continue

                is_cross_cam = (cand["origin_cam"] != cam_id)
                # Intra-camera track repair allowed within 4.0s
                if not is_cross_cam and dt > 4.0:
                    continue

                # Rule 1: A global ID can NEVER be assigned to two different people active on the same camera!
                active_on_same_cam = any(
                    (c == cam_id and other_tid != tid and other_gid == gid and (now_ts - self.entities.get(gid, {}).get("last_seen", 0.0) < 3.0))
                    for (c, other_tid), other_gid in self.track_to_global.items()
                )
                if active_on_same_cam:
                    continue

                # Rule 2: Cannot match if the person is actively visible on another camera right now (no teleportation)
                if is_cross_cam and cand.get("status") != "IN_TRANSIT" and dt < 0.8:
                    continue

                # Rule 3: Visual similarity must be genuinely positive (same clothing / appearance)
                s = safe_sim(new_emb, cand.get("emb"))
                if s < 0.32:
                    # Visually distinct persons (different clothing, colors) must never be merged!
                    continue

                temporal_factor = math.exp(-0.008 * dt)
                cand_risk = cand.get("risk_score", 0.0)
                has_elevated_risk = cand_risk >= 15.0 or bool(cand.get("signals"))

                # Slight continuity boost for verified suspicious subject across cameras
                risk_boost = 0.08 if (is_cross_cam and has_elevated_risk) else 0.0
                match_score = (s * temporal_factor) + risk_boost

                min_thr = 0.35
                if match_score >= min_thr and match_score > best_score:
                    best_score = match_score
                    best_gid = gid
                    best_candidate = cand

            if best_gid is not None and best_candidate is not None:
                # MATCH FOUND! Cross-Camera Identity Handover!
                if best_gid in self.in_transit:
                    del self.in_transit[best_gid]

                self.track_to_global[key] = best_gid
                self.track_embeddings[key] = new_emb

                ent = self.entities.setdefault(best_gid, {
                    "global_id": best_gid,
                    "created_at": best_candidate["last_t"],
                    "first_camera": best_candidate["origin_cam"],
                    "handoff_count": 0
                })
                is_cross_cam = (best_candidate["origin_cam"] != cam_id)
                if is_cross_cam:
                    ent["handoff_count"] += 1
                    ent["from_camera"] = best_candidate["origin_cam"]
                ent["current_camera"] = cam_id
                ent["max_risk_score"] = max(ent.get("max_risk_score", 0.0), best_candidate.get("risk_score", 0.0))

                transit_duration = round(now_ts - best_candidate["last_t"], 1)
                handoff_record = {
                    "id": f"HO-{int(now_ts * 1000) % 1000000}",
                    "timestamp": now_ts,
                    "global_id": best_gid,
                    "from_camera": best_candidate["origin_cam"],
                    "to_camera": cam_id,
                    "local_tid": tid,
                    "transit_duration_s": transit_duration,
                    "similarity": round(best_score, 2),
                    "transferred_risk": round(best_candidate.get("risk_score", 0.0), 1),
                    "risk_level": best_candidate.get("risk_level", "LOW"),
                    "signals": list(best_candidate.get("signals", [])),
                    "events": list(best_candidate.get("events", []))
                }
                if is_cross_cam:
                    self.handoff_history.appendleft(handoff_record)
                    logger.info(
                        f"[CROSS_CAM] Handover Success: Subject {best_gid} transitioned from {best_candidate['origin_cam']} to {cam_id} "
                        f"(dt={transit_duration}s, score={best_score:.2f}, transferred_risk={best_candidate.get('risk_score', 0):.1f})"
                    )
                    return handoff_record
                else:
                    return None

            # No match found: register as a new global identity
            self.track_to_global[key] = self._get_or_create_gid(cam_id, tid)
            self.track_embeddings[key] = new_emb
            return None

    def check_and_unify_identity(
        self,
        cam_id: str,
        tid: int,
        now_ts: float,
        current_risk: float,
        frame: Optional[np.ndarray] = None,
        box: Optional[Tuple[float, float, float, float]] = None
    ) -> Optional[dict]:
        """
        Active Track Re-Linking:
        If a track was initially assigned G2 (e.g. before the previous camera registered track loss),
        but now shows elevated risk or matches an active POI G1 from another camera,
        merges G2 into G1 and returns a handoff record to unify their identity!
        """
        with self.lock:
            key = (cam_id, tid)
            curr_gid = self.track_to_global.get(key)
            if not curr_gid:
                return None

            # Look for active POIs on other cameras that should be merged
            candidates = [
                (gid, cand) for gid, cand in self.active_pois.items()
                if gid != curr_gid and cand["cam_id"] != cam_id and (now_ts - cand["last_seen"] <= self.transit_window_s)
            ]
            if not candidates:
                # Also check in-transit ghosts
                candidates = [
                    (gid, ghost) for gid, ghost in self.in_transit.items()
                    if gid != curr_gid and ghost["from_cam"] != cam_id and (now_ts - ghost["exit_t"] <= self.transit_window_s)
                ]

            if not candidates:
                return None

            # If there's an active POI from another camera and this track has elevated risk:
            # We unify to the original global ID!
            best_gid, best_cand = None, None
            best_sc = 0.0

            curr_emb = self.track_embeddings.get(key)
            if curr_emb is None and frame is not None and box is not None:
                curr_emb = embed(frame, box)

            for gid, cand in candidates:
                dt = max(0.0, now_ts - cand.get("last_seen", cand.get("exit_t", now_ts)))
                s = safe_sim(curr_emb, cand.get("emb"))
                cand_risk = cand.get("risk_score", 0.0)
                # Strong continuity for suspicious / risked tracks
                risk_match = (cand_risk >= 15.0 or current_risk >= 15.0 or bool(cand.get("signals")))
                score = s * 0.5 + (0.5 if risk_match else 0.0)
                if score > best_sc and (score >= 0.35 or (risk_match and len(candidates) == 1)):
                    best_sc = score
                    best_gid = gid
                    best_cand = cand

            if best_gid and best_cand:
                # Perform unification: merge curr_gid into best_gid
                self.merge_identities(from_gid=curr_gid, to_gid=best_gid)
                handoff_record = {
                    "id": f"HO-UNIFY-{int(now_ts * 1000) % 1000000}",
                    "timestamp": now_ts,
                    "global_id": best_gid,
                    "from_camera": best_cand.get("cam_id", best_cand.get("from_cam", "unknown")),
                    "to_camera": cam_id,
                    "local_tid": tid,
                    "transit_duration_s": round(now_ts - best_cand.get("last_seen", best_cand.get("exit_t", now_ts)), 1),
                    "similarity": round(best_sc, 2),
                    "transferred_risk": round(best_cand.get("risk_score", current_risk), 1),
                    "risk_level": best_cand.get("risk_level", "HIGH"),
                    "signals": list(best_cand.get("signals", [])),
                    "events": list(best_cand.get("events", []))
                }
                self.handoff_history.appendleft(handoff_record)
                logger.info(f"[CROSS_CAM] Unified identity: Merged {curr_gid} into {best_gid} on {cam_id}:P{tid}")
                return handoff_record

            return None

    def merge_identities(self, from_gid: str, to_gid: str):
        """Unifies two global IDs across all internal tracking tables."""
        if from_gid == to_gid:
            return

        # Update all local track bindings
        for k, gid in list(self.track_to_global.items()):
            if gid == from_gid:
                self.track_to_global[k] = to_gid

        # Merge entities
        if from_gid in self.entities:
            from_ent = self.entities.pop(from_gid)
            to_ent = self.entities.setdefault(to_gid, {
                "global_id": to_gid,
                "created_at": from_ent.get("created_at", time.time()),
                "first_camera": from_ent.get("first_camera", ""),
                "handoff_count": 0
            })
            to_ent["handoff_count"] += 1
            to_ent["max_risk_score"] = max(to_ent.get("max_risk_score", 0.0), from_ent.get("max_risk_score", 0.0))

        # Merge active POIs
        if from_gid in self.active_pois:
            from_poi = self.active_pois.pop(from_gid)
            if to_gid not in self.active_pois:
                self.active_pois[to_gid] = from_poi
                self.active_pois[to_gid]["global_id"] = to_gid

        # Merge in-transit
        if from_gid in self.in_transit:
            from_trans = self.in_transit.pop(from_gid)
            if to_gid not in self.in_transit:
                self.in_transit[to_gid] = from_trans
                self.in_transit[to_gid]["global_id"] = to_gid

    def register_track_loss(
        self,
        cam_id: str,
        tid: int,
        now_ts: float,
        risk_score: float,
        risk_level: str,
        signals: list,
        events: list,
        last_box: Optional[Tuple[float, float, float, float]] = None
    ):
        """
        Called when a tracked person exits camera view or becomes lost.
        Stores them as an in-transit subject ready to be picked up by the next camera.
        """
        with self.lock:
            key = (cam_id, tid)
            gid = self.track_to_global.get(key)
            if not gid:
                gid = self._get_or_create_gid(cam_id, tid)

            emb = self.track_embeddings.get(key)
            if emb is None:
                emb = np.zeros(96, dtype=np.float32)

            self.in_transit[gid] = {
                "global_id": gid,
                "from_cam": cam_id,
                "exit_t": now_ts,
                "emb": emb,
                "risk_score": float(risk_score),
                "risk_level": str(risk_level),
                "signals": list(signals) if signals else [],
                "events": list(events) if events else [],
                "box": last_box
            }
            # Release local camera track binding so recycled tracker IDs get evaluated freshly
            self.track_to_global.pop(key, None)
            self.track_embeddings.pop(key, None)
            if gid in self.active_pois:
                self.active_pois.pop(gid, None)

            logger.info(
                f"[CROSS_CAM] Subject {gid} ({cam_id}:P{tid}) entered blind spot. "
                f"Risk={risk_score:.1f}, Signals={signals}"
            )

    def reset(self):
        """Resets all internal mappings to start fresh."""
        with self.lock:
            self.in_transit.clear()
            self.active_pois.clear()
            self.track_to_global.clear()
            self.track_embeddings.clear()
            self.entities.clear()
            self.next_gid = 1
            self.handoff_history.clear()
            logger.info("[CROSS_CAM] Coordinator state reset cleanly.")

    def get_in_transit_ghosts(self) -> List[dict]:
        """Returns live in-transit subjects currently in blind spots between cameras."""
        with self.lock:
            now_t = time.time()
            ghosts = []
            for gid, g in self.in_transit.items():
                elapsed = round(now_t - g["exit_t"], 1)
                ghosts.append({
                    "ghost_id": gid,
                    "last_seen_camera": g["from_cam"],
                    "risk_score": round(g["risk_score"], 1),
                    "risk_level": g["risk_level"],
                    "signals": g["signals"],
                    "time_in_transit_s": elapsed,
                    "confidence": round(max(0.0, 1.0 - (elapsed / self.transit_window_s)), 2),
                    "status": "IN_TRANSIT"
                })
            return sorted(ghosts, key=lambda x: x["time_in_transit_s"])

    def get_handoff_history(self) -> List[dict]:
        """Returns verified cross-camera transitions."""
        with self.lock:
            return list(self.handoff_history)


# Global singleton instance
cross_camera_coordinator = CrossCameraCoordinator()
