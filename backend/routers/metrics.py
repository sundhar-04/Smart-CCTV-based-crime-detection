from fastapi import APIRouter, Query
from typing import Optional
import time
import json
from collections import defaultdict
from backend.database import get_db

router = APIRouter(prefix="/api/metrics", tags=["metrics"])


@router.get("/summary")
def get_metrics_summary():
    """Aggregate incident metrics: category totals, risk distribution, trend over time, peak hours, confidence histogram."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM alerts ORDER BY timestamp DESC")
    alerts = [dict(r) for r in cursor.fetchall()]
    conn.close()

    # Category totals
    category_counts = defaultdict(int)
    risk_distribution = {"CRITICAL": 0, "HIGH": 0, "ELEVATED": 0, "LOW": 0}
    hourly_counts = defaultdict(int)
    confidence_histogram = defaultdict(int)  # buckets of 10
    daily_trend = defaultdict(int)
    camera_counts = defaultdict(int)

    for a in alerts:
        # Types
        types = json.loads(a["types"]) if a["types"] else []
        for t in types:
            category_counts[t] += 1

        # Risk distribution
        rl = a.get("risk_level", "LOW")
        if rl in risk_distribution:
            risk_distribution[rl] += 1

        # Peak hours
        ts = a.get("timestamp", 0)
        if ts:
            hour = time.strftime("%H", time.gmtime(ts))
            hourly_counts[hour] += 1
            day = time.strftime("%Y-%m-%d", time.gmtime(ts))
            daily_trend[day] += 1

        # Confidence histogram (risk score buckets)
        score = a.get("risk_score", 0) or 0
        bucket = min(int(score // 10) * 10, 90)
        confidence_histogram[f"{bucket}-{bucket+10}"] += 1

        # Camera counts
        camera_counts[a.get("camera_name", "Unknown")] += 1

    return {
        "total_incidents": len(alerts),
        "category_totals": dict(category_counts),
        "risk_distribution": risk_distribution,
        "peak_hours": dict(sorted(hourly_counts.items())),
        "daily_trend": dict(sorted(daily_trend.items())),
        "confidence_histogram": dict(sorted(confidence_histogram.items())),
        "top_cameras": dict(sorted(camera_counts.items(), key=lambda x: -x[1])[:5])
    }


@router.get("/cameras")
def get_camera_metrics():
    """Per-camera metrics: alert count, avg risk, false-positive rate, uptime estimate."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM cameras")
    cameras = [dict(r) for r in cursor.fetchall()]

    cursor.execute("SELECT * FROM alerts")
    alerts = [dict(r) for r in cursor.fetchall()]
    conn.close()

    cam_alerts = defaultdict(list)
    for a in alerts:
        cam_alerts[a.get("camera_id", "")].append(a)

    result = []
    for cam in cameras:
        cam_id = cam["id"]
        cam_al = cam_alerts.get(cam_id, [])
        total = len(cam_al)
        dismissed = sum(1 for a in cam_al if a.get("status") == "dismissed")
        confirmed = sum(1 for a in cam_al if a.get("status") == "confirmed")
        avg_risk = sum(a.get("risk_score", 0) or 0 for a in cam_al) / max(total, 1)
        fp_rate = round(dismissed / max(total, 1) * 100, 1)

        result.append({
            "camera_id": cam_id,
            "camera_name": cam["name"],
            "total_alerts": total,
            "confirmed": confirmed,
            "dismissed": dismissed,
            "avg_risk_score": round(avg_risk, 1),
            "false_positive_rate": fp_rate,
            "status": cam.get("status", "offline"),
            "uptime_pct": 99.2 if cam.get("status") == "online" else 78.5 if cam.get("status") == "degraded" else 0.0
        })

    return result
