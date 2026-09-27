from fastapi import APIRouter, HTTPException, Response
from typing import List, Optional
import json
import cv2
import numpy as np
import time
from backend.database import get_db
from backend.models import CameraModel

router = APIRouter(prefix="/api/cameras", tags=["cameras"])

@router.get("", response_model=List[CameraModel])
def list_cameras():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM cameras")
    rows = cursor.fetchall()
    conn.close()

    cameras = []
    for r in rows:
        item = dict(r)
        item["zones"] = json.loads(item["zones"]) if item["zones"] else {}
        cameras.append(CameraModel(**item))
    return cameras

@router.get("/{camera_id}", response_model=CameraModel)
def get_camera(camera_id: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM cameras WHERE id = ?", (camera_id,))
    r = cursor.fetchone()
    conn.close()

    if not r:
        raise HTTPException(status_code=404, detail="Camera not found")

    item = dict(r)
    item["zones"] = json.loads(item["zones"]) if item["zones"] else {}
    return CameraModel(**item)

@router.post("")
def save_camera(cam: CameraModel):
    conn = get_db()
    cursor = conn.cursor()
    now_str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    cursor.execute("""
        INSERT OR REPLACE INTO cameras 
        (id, name, location, zone_type, status, fps, rtsp_url, map_x, map_y, zones, last_seen)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        cam.id, cam.name, cam.location, cam.zone_type, cam.status,
        cam.fps, cam.rtsp_url, cam.map_x, cam.map_y,
        json.dumps(cam.zones or {}), now_str
    ))

    conn.commit()
    conn.close()
    return {"status": "ok", "camera": cam}

@router.get("/{camera_id}/snapshot")
def get_camera_snapshot(camera_id: str):
    # Generate dynamic test pattern camera snapshot
    img = np.zeros((480, 640, 3), dtype=np.uint8)
    cv2.rectangle(img, (0, 0), (640, 480), (30, 30, 30), -1)
    
    # Grid lines
    for x in range(0, 640, 80):
        cv2.line(img, (x, 0), (x, 480), (50, 50, 50), 1)
    for y in range(0, 480, 60):
        cv2.line(img, (0, y), (640, y), (50, 50, 50), 1)

    t_str = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
    cv2.putText(img, f"CAM: {camera_id} | LIVE FEED", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 128), 2)
    cv2.putText(img, f"TIME: {t_str}", (20, 450), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

    success, encoded_image = cv2.imencode('.jpg', img)
    if not success:
        raise HTTPException(status_code=500, detail="Could not render camera snapshot")

    return Response(content=encoded_image.tobytes(), media_type="image/jpeg")
