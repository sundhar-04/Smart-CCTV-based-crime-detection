from fastapi import APIRouter, HTTPException, Query, Depends
from typing import List, Optional
import json
import time
import hashlib
from backend.database import get_db
from backend.models import AlertBase, DecisionRequest
from backend.ws import ws_manager

router = APIRouter(prefix="/api/alerts", tags=["alerts"])

@router.get("", response_model=List[AlertBase])
def list_alerts(
    status: Optional[str] = None,
    camera_id: Optional[str] = None,
    min_score: Optional[float] = None,
    limit: int = 100,
    offset: int = 0
):
    conn = get_db()
    cursor = conn.cursor()

    query = "SELECT * FROM alerts WHERE 1=1"
    params = []

    if status:
        query += " AND status = ?"
        params.append(status)
    if camera_id:
        query += " AND camera_id = ?"
        params.append(camera_id)
    if min_score is not None:
        query += " AND risk_score >= ?"
        params.append(min_score)

    query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    cursor.execute(query, params)
    rows = cursor.fetchall()

    alerts = []
    for r in rows:
        item = dict(r)
        item["types"] = json.loads(item["types"]) if item["types"] else []
        item["reasons"] = json.loads(item["reasons"]) if item["reasons"] else []
        alerts.append(AlertBase(**item))

    conn.close()
    return alerts

@router.get("/stats")
def get_alert_stats():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT status, COUNT(*) FROM alerts GROUP BY status")
    counts = dict(cursor.fetchall())

    cursor.execute("SELECT COUNT(*) FROM alerts WHERE risk_score >= 80")
    critical_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM alerts")
    total_count = cursor.fetchone()[0]

    conn.close()
    return {
        "total": total_count,
        "critical": critical_count,
        "active": counts.get("active", 0),
        "reviewing": counts.get("reviewing", 0),
        "confirmed": counts.get("confirmed", 0),
        "dismissed": counts.get("dismissed", 0)
    }

@router.get("/{alert_id}", response_model=AlertBase)
def get_alert(alert_id: str):
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM alerts WHERE id = ?", (alert_id,))
    r = cursor.fetchone()
    conn.close()

    if not r:
        raise HTTPException(status_code=404, detail="Alert not found")

    item = dict(r)
    item["types"] = json.loads(item["types"]) if item["types"] else []
    item["reasons"] = json.loads(item["reasons"]) if item["reasons"] else []
    return AlertBase(**item)

@router.post("/{alert_id}/decide")
async def decide_alert(alert_id: str, req: DecisionRequest):
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM alerts WHERE id = ?", (alert_id,))
    r = cursor.fetchone()
    if not r:
        conn.close()
        raise HTTPException(status_code=404, detail="Alert not found")

    new_status = "confirmed" if req.action.lower() in ["confirm", "confirmed"] else "dismissed"
    decided_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    # Get last hash for tamper-evident hash chain
    cursor.execute("SELECT hash_self FROM audit_logs ORDER BY ROWID DESC LIMIT 1")
    last_audit = cursor.fetchone()
    prev_hash = last_audit[0] if last_audit else "GENESIS"

    audit_id = f"AUD-{int(time.time()*1000)}"
    action_desc = f"Alert {alert_id} decided as {new_status} by {req.decided_by}"
    payload = f"{audit_id}|{decided_at}|{req.decided_by}|{action_desc}|{prev_hash}"
    self_hash = hashlib.sha256(payload.encode()).hexdigest()

    cursor.execute("""
        UPDATE alerts 
        SET status = ?, decided_by = ?, decided_at = ?, notes = ?
        WHERE id = ?
    """, (new_status, req.decided_by, decided_at, req.notes or "", alert_id))

    cursor.execute("""
        INSERT INTO audit_logs (id, timestamp, actor, action, resource, details, hash_prev, hash_self)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (audit_id, decided_at, req.decided_by, action_desc, f"alert:{alert_id}", json.dumps(req.dict()), prev_hash, self_hash))

    conn.commit()

    # Get updated alert
    cursor.execute("SELECT * FROM alerts WHERE id = ?", (alert_id,))
    updated_r = cursor.fetchone()
    conn.close()

    updated_item = dict(updated_r)
    updated_item["types"] = json.loads(updated_item["types"]) if updated_item["types"] else []
    updated_item["reasons"] = json.loads(updated_item["reasons"]) if updated_item["reasons"] else []

    # Broadcast WebSocket update
    await ws_manager.broadcast({
        "event": "alert.updated",
        "data": updated_item
    })

    return {"status": "ok", "alert": updated_item, "audit_hash": self_hash}
