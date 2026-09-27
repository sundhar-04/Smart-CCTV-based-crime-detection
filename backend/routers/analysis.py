from fastapi import APIRouter, HTTPException, UploadFile, File, BackgroundTasks
from fastapi.responses import FileResponse
from typing import List, Optional
import os
import json
import uuid
import time
import cv2
import asyncio
from backend.database import get_db
from backend.models import AnalysisJobCreateResponse, UpdateAnalysisZonesRequest, AnalysisJobResult, AlertBase
from backend.bridge import run_video_analysis
from backend.ws import ws_manager

router = APIRouter(prefix="/api/analysis", tags=["analysis"])

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

@router.post("/upload", response_model=AnalysisJobCreateResponse)
async def upload_video(file: UploadFile = File(...)):
    job_id = f"JOB-{uuid.uuid4().hex[:8].upper()}"
    file_path = os.path.join(UPLOAD_DIR, f"{job_id}_{file.filename}")

    # Save video file
    with open(file_path, "wb") as f:
        content = await file.read()
        f.write(content)

    # Extract 10th frame for zone drawing canvas
    cap = cv2.VideoCapture(file_path)
    frame_path = os.path.join(UPLOAD_DIR, f"{job_id}_frame.jpg")
    frame_saved = False
    for frame_idx in range(15):
        ok, frame = cap.read()
        if ok and frame_idx == 10:
            cv2.imwrite(frame_path, frame)
            frame_saved = True
            break
    if not frame_saved and ok:
        cv2.imwrite(frame_path, frame)

    cap.release()

    created_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO analysis_jobs 
        (id, filename, file_path, status, created_at, zones, progress, current_frame, total_frames, peak_risk_score, no_alert_reason, alerts_generated, result_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        job_id, file.filename, file_path, "drawing_zones", created_at,
        json.dumps([]), 0.0, 0, 0, 0.0, "", json.dumps([]), json.dumps({})
    ))
    conn.commit()
    conn.close()

    return AnalysisJobCreateResponse(
        job_id=job_id,
        filename=file.filename,
        status="drawing_zones",
        extracted_frame_url=f"/api/analysis/files/{job_id}_frame.jpg"
    )

@router.post("/sample", response_model=AnalysisJobCreateResponse)
def load_sample_video():
    demo_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "demo_annotated.mp4")
    if not os.path.exists(demo_path):
        demo_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "smartcctv", "w", "out", "annotated.mp4")

    if not os.path.exists(demo_path):
        raise HTTPException(status_code=404, detail="Sample video demo_annotated.mp4 not found on server")

    job_id = f"JOB-DEMO-{uuid.uuid4().hex[:6].upper()}"
    file_path = os.path.join(UPLOAD_DIR, f"{job_id}_demo.mp4")

    # Copy sample file
    import shutil
    shutil.copyfile(demo_path, file_path)

    # Extract 10th frame
    cap = cv2.VideoCapture(file_path)
    frame_path = os.path.join(UPLOAD_DIR, f"{job_id}_frame.jpg")
    frame_saved = False
    for frame_idx in range(15):
        ok, frame = cap.read()
        if ok and frame_idx == 10:
            cv2.imwrite(frame_path, frame)
            frame_saved = True
            break
    if not frame_saved and ok:
        cv2.imwrite(frame_path, frame)
    cap.release()

    created_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO analysis_jobs 
        (id, filename, file_path, status, created_at, zones, progress, current_frame, total_frames, peak_risk_score, no_alert_reason, alerts_generated, result_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        job_id, "demo_annotated.mp4", file_path, "drawing_zones", created_at,
        json.dumps([]), 0.0, 0, 0, 0.0, "", json.dumps([]), json.dumps({})
    ))
    conn.commit()
    conn.close()

    return AnalysisJobCreateResponse(
        job_id=job_id,
        filename="demo_annotated.mp4",
        status="drawing_zones",
        extracted_frame_url=f"/api/analysis/files/{job_id}_frame.jpg"
    )

@router.get("/files/{filename}")
def get_analysis_file(filename: str):
    file_path = os.path.join(UPLOAD_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(file_path)

@router.put("/{job_id}/zones")
def update_analysis_zones(job_id: str, req: UpdateAnalysisZonesRequest):
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM analysis_jobs WHERE id = ?", (job_id,))
    r = cursor.fetchone()
    if not r:
        conn.close()
        raise HTTPException(status_code=404, detail="Analysis job not found")

    zones_data = [z.dict() for z in req.zones]
    cursor.execute("UPDATE analysis_jobs SET zones = ? WHERE id = ?", (json.dumps(zones_data), job_id))
    conn.commit()
    conn.close()

    return {"status": "ok", "job_id": job_id, "zones": zones_data}

def execute_job_background(job_id: str, file_path: str, zones_list: list):
    output_job_dir = os.path.join(UPLOAD_DIR, job_id)
    os.makedirs(output_job_dir, exist_ok=True)

    # Convert zones list to dictionary format expected by RiskEngine: {"zone1": {"poly": [[x,y],...], "crit": 1.0, "restricted": True}}
    zones_config = {}
    for idx, z in enumerate(zones_list):
        zname = z.get("name", f"zone_{idx+1}")
        raw_pts = z.get("points", [])
        norm_pts = []
        for p in raw_pts:
            if isinstance(p, dict):
                norm_pts.append([int(p.get("x", 0)), int(p.get("y", 0))])
            elif isinstance(p, (list, tuple)) and len(p) >= 2:
                norm_pts.append([int(p[0]), int(p[1])])
        if norm_pts:
            zones_config[zname] = {"poly": norm_pts, "crit": 1.0, "restricted": True}

    def progress_cb(current_f, total_f, current_peak, active_tracks):
        pct = round((current_f / max(total_f, 1)) * 100, 1)
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE analysis_jobs 
            SET progress = ?, current_frame = ?, total_frames = ?, peak_risk_score = ?
            WHERE id = ?
        """, (pct, current_f, total_f, current_peak, job_id))
        conn.commit()
        conn.close()

    try:
        res = run_video_analysis(file_path, output_job_dir, zones_config=zones_config, progress_callback=progress_cb)

        # Save generated alerts to main alerts table
        saved_alerts = []
        conn = get_db()
        cursor = conn.cursor()

        now_str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        for idx, al in enumerate(res.get("alerts", [])):
            alert_id = f"ALT-ANALYSIS-{job_id[:6]}-{idx+1}"
            r_score = float(al.get("score", 40.0))
            r_level = "CRITICAL" if r_score >= 80 else "HIGH" if r_score >= 60 else "ELEVATED" if r_score >= 35 else "LOW"
            
            types_list = [al.get("kind", "INTRUSION")]
            reasons_list = al.get("reasons", [f"Triggered in zone {al.get('zone', 'Z1')}"])
            
            clip_file = al.get("clip", "")
            best_shot_file = al.get("best_shot", "")
            clip_sha = al.get("clip_sha256", "")

            evidence_url = f"/static/uploads/{job_id}/clips/{clip_file}" if clip_file else f"/static/uploads/{job_id}/annotated_analysis.mp4"
            snapshot_url = f"/static/uploads/{job_id}/clips/{best_shot_file}" if best_shot_file else evidence_url

            cursor.execute("""
                INSERT OR REPLACE INTO alerts
                (id, timestamp, camera_id, camera_name, location, risk_score, risk_level, status, types, reasons, zone, entity, clip_sha256, evidence_path, snapshot_url)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                alert_id, time.time(), "ANALYSIS_CAM", "Uploaded Clip Analyzer", "Analysis Sandbox",
                r_score, r_level, "active", json.dumps(types_list), json.dumps(reasons_list),
                al.get("zone", "Z1"), al.get("entity", "P1"), clip_sha, evidence_url, snapshot_url
            ))
            
            saved_alerts.append({
                "id": alert_id,
                "timestamp": time.time(),
                "camera_id": "ANALYSIS_CAM",
                "camera_name": "Uploaded Clip Analyzer",
                "location": "Analysis Sandbox",
                "risk_score": r_score,
                "risk_level": r_level,
                "status": "active",
                "types": types_list,
                "reasons": reasons_list,
                "zone": al.get("zone", "Z1"),
                "entity": al.get("entity", "P1"),
                "clip_sha256": clip_sha,
                "evidence_path": evidence_url,
                "snapshot_url": snapshot_url
            })

        cursor.execute("""
            UPDATE analysis_jobs
            SET status = 'completed', progress = 100.0, total_frames = ?, peak_risk_score = ?, no_alert_reason = ?, alerts_generated = ?, result_json = ?
            WHERE id = ?
        """, (
            res["total_frames"], res["peak_risk_score"], res["no_alert_reason"],
            json.dumps([a["id"] for a in saved_alerts]), json.dumps(res, default=str), job_id
        ))

        conn.commit()
        conn.close()

    except Exception as e:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("UPDATE analysis_jobs SET status = 'failed', no_alert_reason = ? WHERE id = ?", (str(e), job_id))
        conn.commit()
        conn.close()

@router.post("/{job_id}/start")
def start_analysis(job_id: str, background_tasks: BackgroundTasks):
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM analysis_jobs WHERE id = ?", (job_id,))
    r = cursor.fetchone()
    if not r:
        conn.close()
        raise HTTPException(status_code=404, detail="Analysis job not found")

    job = dict(r)
    file_path = job["file_path"]
    zones_list = json.loads(job["zones"]) if job["zones"] else []

    cursor.execute("UPDATE analysis_jobs SET status = 'processing', progress = 0.0 WHERE id = ?", (job_id,))
    conn.commit()
    conn.close()

    background_tasks.add_task(execute_job_background, job_id, file_path, zones_list)

    return {"status": "processing", "job_id": job_id}

@router.get("/{job_id}/status")
def get_analysis_status(job_id: str):
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM analysis_jobs WHERE id = ?", (job_id,))
    r = cursor.fetchone()
    conn.close()

    if not r:
        raise HTTPException(status_code=404, detail="Analysis job not found")

    job = dict(r)
    return {
        "job_id": job["id"],
        "status": job["status"],
        "progress": job["progress"],
        "current_frame": job["current_frame"],
        "total_frames": job["total_frames"],
        "peak_risk_score": job["peak_risk_score"],
        "no_alert_reason": job["no_alert_reason"]
    }

@router.get("/{job_id}/result", response_model=AnalysisJobResult)
def get_analysis_result(job_id: str):
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM analysis_jobs WHERE id = ?", (job_id,))
    r = cursor.fetchone()
    if not r:
        conn.close()
        raise HTTPException(status_code=404, detail="Analysis job not found")

    job = dict(r)
    alerts_ids = json.loads(job["alerts_generated"]) if job["alerts_generated"] else []

    alerts_list = []
    if alerts_ids:
        placeholders = ",".join(["?"] * len(alerts_ids))
        cursor.execute(f"SELECT * FROM alerts WHERE id IN ({placeholders})", alerts_ids)
        for ar in cursor.fetchall():
            item = dict(ar)
            item["types"] = json.loads(item["types"]) if item["types"] else []
            item["reasons"] = json.loads(item["reasons"]) if item["reasons"] else []
            alerts_list.append(AlertBase(**item))

    conn.close()

    return AnalysisJobResult(
        job_id=job["id"],
        status=job["status"],
        total_frames=job["total_frames"] or 0,
        peak_risk_score=job["peak_risk_score"] or 0.0,
        no_alert_reason=job["no_alert_reason"] or "",
        alerts=alerts_list
    )
