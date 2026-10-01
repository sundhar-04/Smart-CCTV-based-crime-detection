from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import StreamingResponse
from typing import List, Optional
import json
import time
import uuid
from backend.database import get_db
from backend.models import (
    CameraModel,
    CameraPositionUpdate,
    CameraTestConnectionRequest,
    CameraTestConnectionResponse
)
from backend.camera_manager import camera_manager, normalize_stream_url
from backend.ws import ws_manager

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
        item["zones"] = json.loads(item["zones"]) if item.get("zones") else {}
        item["enabled"] = bool(item.get("enabled", 1))
        
        # Merge live status from active worker if available
        worker = camera_manager.get_worker(item["id"])
        if worker:
            item["status"] = worker.status
            item["fps"] = round(worker.actual_fps, 1) or item.get("fps", 25.0)
            if worker.last_seen:
                item["last_seen"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(worker.last_seen))
            item["error"] = worker.error_message
        
        # Ensure stream_url and rtsp_url are synced
        if not item.get("stream_url") and item.get("rtsp_url"):
            item["stream_url"] = item["rtsp_url"]
        elif not item.get("rtsp_url") and item.get("stream_url"):
            item["rtsp_url"] = item["stream_url"]

        cameras.append(CameraModel(**item))
    return cameras

@router.get("/{camera_id}/detections")
def get_camera_detections(camera_id: str):
    worker = camera_manager.get_worker(camera_id)
    if not worker:
        raise HTTPException(status_code=404, detail="Camera worker not found")
    with worker.lock:
        return {
            "camera_id": camera_id,
            "peak_risk": worker.latest_risk_score,
            "detections": worker.latest_detections
        }

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
    item["zones"] = json.loads(item["zones"]) if item.get("zones") else {}
    item["enabled"] = bool(item.get("enabled", 1))

    worker = camera_manager.get_worker(camera_id)
    if worker:
        item["status"] = worker.status
        item["fps"] = round(worker.actual_fps, 1) or item.get("fps", 25.0)
        if worker.last_seen:
            item["last_seen"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(worker.last_seen))
        item["error"] = worker.error_message

    if not item.get("stream_url") and item.get("rtsp_url"):
        item["stream_url"] = item["rtsp_url"]

    return CameraModel(**item)

@router.post("", response_model=CameraModel)
def save_camera(cam: CameraModel):
    conn = get_db()
    cursor = conn.cursor()
    now_str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    # Generate camera ID if not provided
    cam_id = cam.id.strip() if cam.id and cam.id.strip() else f"cam_{uuid.uuid4().hex[:6]}"
    stream_url = normalize_stream_url((cam.stream_url or cam.rtsp_url or "").strip())
    protocol = (cam.protocol or "mjpeg").lower()

    cursor.execute("""
        INSERT OR REPLACE INTO cameras 
        (id, name, location, zone_type, status, fps, rtsp_url, stream_url, protocol, enabled, map_x, map_y, zones, last_seen)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        cam_id, cam.name, cam.location, cam.zone_type, cam.status,
        cam.fps, stream_url, stream_url, protocol, 1 if cam.enabled else 0,
        cam.map_x, cam.map_y, json.dumps(cam.zones or {}), now_str
    ))

    conn.commit()
    conn.close()

    cam_dict = cam.dict()
    cam_dict["id"] = cam_id
    cam_dict["stream_url"] = stream_url
    cam_dict["rtsp_url"] = stream_url

    # Start or update the background ingestion worker
    camera_manager.add_or_update(cam_dict)

    return CameraModel(**cam_dict)

@router.put("/{camera_id}", response_model=CameraModel)
def update_camera(camera_id: str, cam: CameraModel):
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM cameras WHERE id = ?", (camera_id,))
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Camera not found")

    now_str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    stream_url = normalize_stream_url((cam.stream_url or cam.rtsp_url or "").strip())
    protocol = (cam.protocol or "mjpeg").lower()

    cursor.execute("""
        UPDATE cameras 
        SET name = ?, location = ?, zone_type = ?, status = ?, fps = ?,
            rtsp_url = ?, stream_url = ?, protocol = ?, enabled = ?,
            map_x = ?, map_y = ?, zones = ?, last_seen = ?
        WHERE id = ?
    """, (
        cam.name, cam.location, cam.zone_type, cam.status, cam.fps,
        stream_url, stream_url, protocol, 1 if cam.enabled else 0,
        cam.map_x, cam.map_y, json.dumps(cam.zones or {}), now_str,
        camera_id
    ))

    conn.commit()
    conn.close()

    cam_dict = cam.dict()
    cam_dict["id"] = camera_id
    cam_dict["stream_url"] = stream_url
    cam_dict["rtsp_url"] = stream_url

    camera_manager.add_or_update(cam_dict)
    return CameraModel(**cam_dict)

@router.delete("/{camera_id}")
def delete_camera(camera_id: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM cameras WHERE id = ?", (camera_id,))
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()

    if not deleted:
        raise HTTPException(status_code=404, detail="Camera not found")

    camera_manager.remove(camera_id)
    return {"status": "ok", "deleted": camera_id}

@router.patch("/{camera_id}/position")
def update_camera_position(camera_id: str, pos: CameraPositionUpdate):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE cameras SET map_x = ?, map_y = ? WHERE id = ?", (pos.map_x, pos.map_y, camera_id))
    if cursor.rowcount == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="Camera not found")
    conn.commit()
    conn.close()
    
    ws_manager.broadcast_sync({
        "event": "camera_position_updated",
        "data": {
            "camera_id": camera_id,
            "map_x": pos.map_x,
            "map_y": pos.map_y
        }
    })
    return {"status": "ok", "camera_id": camera_id, "map_x": pos.map_x, "map_y": pos.map_y}

@router.post("/test-connection", response_model=CameraTestConnectionResponse)
def test_camera_connection(req: CameraTestConnectionRequest):
    """
    Validates a mobile phone / IP camera stream URL and tests live frame decode.
    Returns status CONNECTED with resolution & FPS if reachable, or FAILED with clear error message.
    """
    res = camera_manager.test_connection(req.stream_url, req.protocol or "mjpeg")
    return CameraTestConnectionResponse(**res)

@router.get("/{camera_id}/health")
def get_camera_health(camera_id: str):
    """Returns camera health status: CONNECTED, CONNECTING, DISCONNECTED, or ERROR."""
    worker = camera_manager.get_worker(camera_id)
    if worker:
        return worker.get_health()

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM cameras WHERE id = ?", (camera_id,))
    r = cursor.fetchone()
    conn.close()

    if not r:
        raise HTTPException(status_code=404, detail="Camera not found")

    cam = dict(r)
    return {
        "camera_id": camera_id,
        "name": cam.get("name"),
        "status": cam.get("status", "DISCONNECTED"),
        "stream_url": cam.get("stream_url") or cam.get("rtsp_url"),
        "protocol": cam.get("protocol", "mjpeg"),
        "fps": cam.get("fps", 0.0),
        "last_seen": cam.get("last_seen"),
        "error": "No active worker for this camera"
    }

@router.get("/{camera_id}/snapshot")
async def get_camera_snapshot(camera_id: str):
    """
    Returns the ACTUAL decoded live frame from the mobile camera stream.
    Zero fake placeholder images when stream is active.
    """
    jpeg_bytes, media_type, status_code = camera_manager.get_snapshot(camera_id)
    if not jpeg_bytes:
        raise HTTPException(status_code=status_code, detail="Could not retrieve camera snapshot")

    return Response(
        content=jpeg_bytes,
        media_type=media_type,
        headers={"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache"}
    )

@router.get("/{camera_id}/stream")
async def get_camera_mjpeg_stream(camera_id: str):
    """
    Streams live multipart MJPEG video directly to browser <img> elements at real-time FPS.
    Runs on asyncio event loop to avoid threadpool exhaustion.
    """
    import asyncio
    worker = camera_manager.get_worker(camera_id)
    if not worker:
        raise HTTPException(status_code=404, detail="Camera stream not found or inactive")

    async def _frame_generator():
        last_jpeg_bytes = None
        try:
            while True:
                with worker.lock:
                    jpeg = worker.latest_jpeg
                if jpeg is not None and jpeg != last_jpeg_bytes:
                    last_jpeg_bytes = jpeg
                    yield (b"--frame\r\n"
                           b"Content-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n")
                await asyncio.sleep(0.015)
        except (asyncio.CancelledError, GeneratorExit):
            pass

    return StreamingResponse(
        _frame_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "X-Accel-Buffering": "no"
        }
    )


