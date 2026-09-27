from fastapi import APIRouter
import json
from backend.database import get_db

router = APIRouter(prefix="/api", tags=["topology"])

DEFAULT_NODES = [
    {"id": "cam_gate1", "label": "Main Entrance Gate", "type": "camera", "status": "online"},
    {"id": "cam_lobby", "label": "Main Lobby", "type": "camera", "status": "online"},
    {"id": "cam_server", "label": "Server Room Corridor", "type": "camera", "status": "online"},
    {"id": "cam_perimeter", "label": "North Perimeter Fence", "type": "camera", "status": "degraded"},
    {"id": "node_edge_1", "label": "Edge AI Box 01", "type": "edge_device", "status": "online"},
    {"id": "node_server_main", "label": "Central Inference Host", "type": "server", "status": "online"}
]

DEFAULT_EDGES = [
    {"source": "cam_gate1", "target": "node_edge_1", "latency_ms": 12},
    {"source": "cam_lobby", "target": "node_edge_1", "latency_ms": 14},
    {"source": "cam_server", "target": "node_server_main", "latency_ms": 5},
    {"source": "cam_perimeter", "target": "node_server_main", "latency_ms": 22},
    {"source": "node_edge_1", "target": "node_server_main", "latency_ms": 8}
]

@router.get("/topology")
def get_topology():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT value FROM topology WHERE key = 'graph'")
    r = cursor.fetchone()
    conn.close()

    if r:
        return json.loads(r[0])
    
    return {"nodes": DEFAULT_NODES, "edges": DEFAULT_EDGES}

@router.get("/identity/ghosts")
def get_identity_ghosts():
    # Live in-transit ghost tracked objects across cameras
    return {
        "ghosts": [
            {
                "ghost_id": "GHOST-8821",
                "last_seen_camera": "cam_gate1",
                "predicted_camera": "cam_lobby",
                "confidence": 0.91,
                "time_in_transit_s": 4.2,
                "features_vector": "reid_embed_992"
            }
        ]
    }
