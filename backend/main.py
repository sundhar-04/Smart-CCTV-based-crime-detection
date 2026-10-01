from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os
import json
import time
import logging

from backend.database import init_db, get_db
from backend.ws import ws_manager
from backend.routers import alerts, cameras, analysis, system, topology, settings, metrics, users

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("smartcctv_backend")

app = FastAPI(
    title="SmartCCTV Surveillance API",
    version="2.0.0",
    description="Production backend powering SmartCCTV / Meridian surveillance system."
)

# Enable CORS for frontend Vite dev server & production client
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API Routers
app.include_router(alerts.router)
app.include_router(cameras.router)
app.include_router(analysis.router)
app.include_router(system.router)
app.include_router(topology.router)
app.include_router(settings.router)
app.include_router(metrics.router)
app.include_router(users.router)

# Mount upload directory for static video/image evidence serving
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/static/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

def seed_initial_data():
    """Seed initial sample cameras and alerts into SQLite DB if empty"""
    conn = get_db()
    cursor = conn.cursor()

    # Seed cameras
    cursor.execute("SELECT COUNT(*) FROM cameras")
    if cursor.fetchone()[0] == 0:
        cams = [
            ("cam_gate1", "Main Entrance Gate", "Perimeter Gate A", "PERIMETER", "online", 25.0, "rtsp://192.168.1.101/live", 15.0, 20.0, json.dumps({}), time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())),
            ("cam_lobby", "Main Lobby Reception", "Building Alpha Lobby", "HIGH_SECURITY", "online", 25.0, "rtsp://192.168.1.102/live", 45.0, 50.0, json.dumps({}), time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())),
            ("cam_server", "Server Room Vault", "Building Alpha Floor B1", "RESTRICTED", "online", 30.0, "rtsp://192.168.1.103/live", 80.0, 85.0, json.dumps({}), time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())),
            ("cam_perimeter", "North Fence Boundary", "Perimeter Gate N", "RESTRICTED", "degraded", 15.0, "rtsp://192.168.1.104/live", 85.0, 15.0, json.dumps({}), time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
        ]
        cursor.executemany("""
            INSERT INTO cameras (id, name, location, zone_type, status, fps, rtsp_url, map_x, map_y, zones, last_seen)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, cams)
        logger.info("Seeded initial cameras.")

    # Seed sample alerts
    cursor.execute("SELECT COUNT(*) FROM alerts")
    if cursor.fetchone()[0] == 0:
        now_ts = time.time()
        sample_alerts = [
            (
                "ALT-1001", now_ts - 300, "cam_server", "Server Room Vault", "Building Alpha Floor B1",
                88.5, "CRITICAL", "active", json.dumps(["RESTRICTED_ZONE", "LOITERING"]),
                json.dumps(["Person detected in restricted server vault zone", "Loitering time exceeded 25 seconds"]),
                "Vault Zone 1", "P102", "", "", "", None, None, "", "GENESIS", "HASH-1001"
            ),
            (
                "ALT-1002", now_ts - 1200, "cam_gate1", "Main Entrance Gate", "Perimeter Gate A",
                62.0, "HIGH", "reviewing", json.dumps(["LOITERING"]),
                json.dumps(["Loitering near entrance gate after hours"]),
                "Gate Entrance Zone", "P105", "", "", "", None, None, "", "HASH-1001", "HASH-1002"
            )
        ]
        cursor.executemany("""
            INSERT INTO alerts (id, timestamp, camera_id, camera_name, location, risk_score, risk_level, status, types, reasons, zone, entity, clip_sha256, evidence_path, snapshot_url, decided_by, decided_at, notes, hash_prev, hash_self)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, sample_alerts)
        logger.info("Seeded initial alerts.")

    conn.commit()
    conn.close()

@app.on_event("startup")
async def on_startup():
    import asyncio
    try:
        ws_manager.set_loop(asyncio.get_running_loop())
    except Exception:
        pass
    init_db()
    seed_initial_data()
    from backend.camera_manager import camera_manager
    camera_manager.start_all()
    logger.info("SmartCCTV Backend Server started successfully with Camera Stream Manager active.")

@app.on_event("shutdown")
async def on_shutdown():
    from backend.camera_manager import camera_manager
    camera_manager.stop_all()
    logger.info("SmartCCTV Camera Stream Manager stopped cleanly.")

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            # Keep-alive receive loop
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text(json.dumps({"event": "pong", "timestamp": time.time()}))
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception as e:
        logger.warning(f"WebSocket connection error: {e}")
        ws_manager.disconnect(websocket)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
# Reload trigger: 2026-09-28T16:20:15


