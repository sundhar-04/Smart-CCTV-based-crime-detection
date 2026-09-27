from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Union

class AlertBase(BaseModel):
    id: str
    timestamp: float
    camera_id: str
    camera_name: str
    location: str
    risk_score: float
    risk_level: str
    status: str
    types: List[str]
    reasons: List[str]
    zone: Optional[str] = None
    entity: Optional[str] = None
    clip_sha256: Optional[str] = None
    evidence_path: Optional[str] = None
    snapshot_url: Optional[str] = None
    decided_by: Optional[str] = None
    decided_at: Optional[str] = None
    notes: Optional[str] = None
    hash_prev: Optional[str] = None
    hash_self: Optional[str] = None

class AlertFilters(BaseModel):
    status: Optional[str] = None
    camera_id: Optional[str] = None
    min_score: Optional[float] = None
    limit: Optional[int] = 100
    offset: Optional[int] = 0

class DecisionRequest(BaseModel):
    action: str  # "confirm" or "dismiss"
    decided_by: str = "operator_admin"
    notes: Optional[str] = ""

class CameraModel(BaseModel):
    id: str
    name: str
    location: str
    zone_type: str = "SECURE"
    status: str = "online"
    fps: float = 25.0
    rtsp_url: Optional[str] = None
    map_x: float = 50.0
    map_y: float = 50.0
    zones: Optional[Dict[str, List[List[int]]]] = {}
    last_seen: Optional[str] = None

class AnalysisJobCreateResponse(BaseModel):
    job_id: str
    filename: str
    status: str
    extracted_frame_url: str

class PointObj(BaseModel):
    x: float
    y: float

class ZonePolygon(BaseModel):
    name: str
    points: List[Any]

class UpdateAnalysisZonesRequest(BaseModel):
    zones: List[ZonePolygon]

class AnalysisJobResult(BaseModel):
    job_id: str
    status: str
    total_frames: int
    peak_risk_score: float
    no_alert_reason: str
    alerts: List[AlertBase]
