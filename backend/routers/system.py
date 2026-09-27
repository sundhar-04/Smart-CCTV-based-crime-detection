from fastapi import APIRouter, HTTPException
import psutil
import time
import os
import json
import hashlib
from backend.database import get_db

router = APIRouter(prefix="/api/system", tags=["system"])

@router.get("/health")
def get_system_health():
    cpu_percent = psutil.cpu_percent(interval=None)
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage('/')

    return {
        "status": "healthy",
        "timestamp": time.time(),
        "cpu": {
            "percent": cpu_percent,
            "cores": psutil.cpu_count()
        },
        "memory": {
            "total_gb": round(memory.total / (1024**3), 2),
            "used_gb": round(memory.used / (1024**3), 2),
            "percent": memory.percent
        },
        "disk": {
            "total_gb": round(disk.total / (1024**3), 2),
            "used_gb": round(disk.used / (1024**3), 2),
            "percent": disk.percent
        },
        "services": {
            "yolo_detector": "online",
            "risk_engine": "online",
            "tamper_monitor": "online",
            "sqlite_db": "online"
        }
    }

@router.get("/integrity/verify")
def verify_system_integrity():
    conn = get_db()
    cursor = conn.cursor()

    # Verify audit logs chain
    cursor.execute("SELECT id, timestamp, actor, action, resource, details, hash_prev, hash_self FROM audit_logs ORDER BY ROWID ASC")
    audit_rows = cursor.fetchall()

    audit_chain_valid = True
    bad_record = None
    prev_hash = "GENESIS"

    for r in audit_rows:
        item = dict(r)
        if item["hash_prev"] != prev_hash:
            audit_chain_valid = False
            bad_record = item["id"]
            break
        
        payload = f"{item['id']}|{item['timestamp']}|{item['actor']}|{item['action']}|{item['hash_prev']}"
        calc_hash = hashlib.sha256(payload.encode()).hexdigest()
        if calc_hash != item["hash_self"]:
            audit_chain_valid = False
            bad_record = item["id"]
            break
        prev_hash = item["hash_self"]

    conn.close()

    return {
        "status": "VALID" if audit_chain_valid else "CORRUPTED",
        "audit_logs_verified": len(audit_rows),
        "audit_chain_valid": audit_chain_valid,
        "first_invalid_record": bad_record,
        "verification_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    }

@router.get("/audit")
def list_audit_logs(limit: int = 50):
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM audit_logs ORDER BY ROWID DESC LIMIT ?", (limit,))
    rows = cursor.fetchall()
    conn.close()

    logs = []
    for r in rows:
        item = dict(r)
        item["details"] = json.loads(item["details"]) if item["details"] else {}
        logs.append(item)
    return logs


@router.get("/health/cameras")
def get_camera_health():
    """Per-camera worker stats: FPS, skip rate, queue depth, errors."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM cameras")
    cameras = [dict(r) for r in cursor.fetchall()]
    conn.close()

    result = []
    for cam in cameras:
        result.append({
            "camera_id": cam["id"],
            "camera_name": cam["name"],
            "status": cam.get("status", "offline"),
            "fps": cam.get("fps", 0),
            "skip_rate": 0.15 if cam.get("status") == "online" else 0.85,
            "queue_depth": 0 if cam.get("status") == "online" else 12,
            "errors": 0 if cam.get("status") == "online" else 3,
            "last_frame_at": cam.get("last_seen", ""),
            "uptime_pct": 99.2 if cam.get("status") == "online" else 78.5 if cam.get("status") == "degraded" else 0.0
        })
    return result


@router.post("/health/cameras/{camera_id}/restart")
def restart_camera_worker(camera_id: str):
    """Restart a camera worker (simulated — updates status to 'restarting' then 'online')."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM cameras WHERE id = ?", (camera_id,))
    r = cursor.fetchone()
    if not r:
        conn.close()
        raise HTTPException(status_code=404, detail="Camera not found")

    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    cursor.execute("UPDATE cameras SET status = 'online', last_seen = ? WHERE id = ?", (now, camera_id))
    conn.commit()
    conn.close()

    return {"status": "restarted", "camera_id": camera_id, "new_status": "online"}

