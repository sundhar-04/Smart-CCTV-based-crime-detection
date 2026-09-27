from fastapi import APIRouter, HTTPException
import json
import time
from typing import Dict, Any
from backend.database import get_db

router = APIRouter(prefix="/api/settings", tags=["settings"])

DEFAULT_SETTINGS = {
    "detection": {
        "detector_model": "yolov8n",
        "confidence_threshold": 0.25,
        "iou_threshold": 0.45,
        "max_detections": 30,
        "enable_motion_gating": True,
        "input_resolution": "640x640"
    },
    "risk": {
        "loitering_threshold_s": 15,
        "restricted_zone_weight": 40,
        "abandoned_object_threshold_s": 20,
        "running_person_weight": 25,
        "critical_alert_threshold": 80,
        "high_alert_threshold": 60,
        "elevated_alert_threshold": 35
    },
    "notifications": {
        "enable_browser_toasts": True,
        "enable_sound_alerts": True,
        "webhook_url": "http://localhost:8000/api/notifications/webhook",
        "email_alerts_enabled": False,
        "recipient_emails": ["security@facility.internal"]
    },
    "privacy": {
        "face_blur_enabled": True,
        "license_plate_masking": True,
        "data_anonymization": False
    },
    "retention": {
        "evidence_retention_days": 90,
        "auto_purge_dismissed_days": 30,
        "max_storage_gb": 500
    },
    "system": {
        "storage_path": "./out",
        "log_level": "INFO",
        "max_worker_threads": 4,
        "gpu_acceleration": True
    },
    "users": [
        {"id": "usr_1", "username": "admin", "role": "Administrator", "email": "admin@facility.internal"},
        {"id": "usr_2", "username": "operator_1", "role": "Security Operator", "email": "op1@facility.internal"}
    ]
}

@router.get("")
def get_all_settings():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT key, value FROM settings")
    rows = cursor.fetchall()
    conn.close()

    db_settings = {}
    for r in rows:
        db_settings[r["key"]] = json.loads(r["value"])

    result = {}
    for cat, default_val in DEFAULT_SETTINGS.items():
        result[cat] = db_settings.get(cat, default_val)

    return result

@router.get("/history/all")
def get_settings_history():
    """Returns audit log entries of settings changes with diffs."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM audit_log WHERE action = 'settings_update' ORDER BY created_at DESC LIMIT 50"
    )
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    for r in rows:
        if r.get("detail"):
            try:
                r["detail"] = json.loads(r["detail"])
            except Exception:
                pass
    return rows

@router.get("/{category}")
def get_setting_category(category: str):
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT value FROM settings WHERE key = ?", (category,))
    r = cursor.fetchone()
    conn.close()

    if r:
        return json.loads(r[0])
    
    if category in DEFAULT_SETTINGS:
        return DEFAULT_SETTINGS[category]

    raise HTTPException(status_code=404, detail="Settings category not found")

@router.put("/{category}")
def update_setting_category(category: str, payload: Dict[str, Any]):
    conn = get_db()
    cursor = conn.cursor()

    # Get previous value for diff
    cursor.execute("SELECT value FROM settings WHERE key = ?", (category,))
    prev_row = cursor.fetchone()
    prev_val = json.loads(prev_row[0]) if prev_row else DEFAULT_SETTINGS.get(category, {})

    cursor.execute("""
        INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)
    """, (category, json.dumps(payload)))

    # Log to audit
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    diff_detail = json.dumps({"category": category, "previous": prev_val, "updated": payload})
    cursor.execute(
        "INSERT INTO audit_log (action, user_name, object_type, object_id, detail, created_at) VALUES (?,?,?,?,?,?)",
        ("settings_update", "operator_admin", "settings", category, diff_detail, now)
    )

    conn.commit()
    conn.close()

    return {"status": "ok", "category": category, "settings": payload}

