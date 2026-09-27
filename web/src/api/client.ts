export interface Alert {
  id: string;
  timestamp: number;
  camera_id: string;
  camera_name: string;
  location: string;
  risk_score: number;
  risk_level: string;
  status: string;
  types: string[];
  reasons: string[];
  zone?: string;
  entity?: string;
  clip_sha256?: string;
  evidence_path?: string;
  snapshot_url?: string;
  decided_by?: string;
  decided_at?: string;
  notes?: string;
  hash_prev?: string;
  hash_self?: string;
}

export interface Camera {
  id: string;
  name: string;
  location: string;
  zone_type: string;
  status: string;
  fps: number;
  rtsp_url?: string;
  map_x: number;
  map_y: number;
  zones?: Record<string, number[][]>;
  last_seen?: string;
}

export interface DecisionRequest {
  action: 'confirm' | 'dismiss';
  decided_by?: string;
  notes?: string;
}

export interface AnalysisJobCreate {
  job_id: string;
  filename: string;
  status: string;
  extracted_frame_url: string;
}

export interface AnalysisJobStatus {
  job_id: string;
  status: string;
  progress: number;
  current_frame: number;
  total_frames: number;
  peak_risk_score: number;
  no_alert_reason: string;
}

export interface AnalysisJobResult {
  job_id: string;
  status: string;
  total_frames: number;
  peak_risk_score: number;
  no_alert_reason: string;
  alerts: Alert[];
}

const API_BASE = '/api';

export async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(url, options);
  if (!res.ok) {
    const errText = await res.text();
    throw new Error(`API Error ${res.status}: ${errText}`);
  }
  return res.json() as Promise<T>;
}

export async function listAlerts(params?: { status?: string; camera_id?: string; min_score?: number; limit?: number; offset?: number }): Promise<Alert[]> {
  const query = new URLSearchParams();
  if (params?.status) query.append('status', params.status);
  if (params?.camera_id) query.append('camera_id', params.camera_id);
  if (params?.min_score !== undefined) query.append('min_score', params.min_score.toString());
  if (params?.limit) query.append('limit', params.limit.toString());
  if (params?.offset) query.append('offset', params.offset.toString());
  return fetchJson<Alert[]>(`${API_BASE}/alerts?${query.toString()}`);
}

export async function getAlert(id: string): Promise<Alert> {
  return fetchJson<Alert>(`${API_BASE}/alerts/${id}`);
}

export async function decideAlert(id: string, body: DecisionRequest): Promise<{ status: string; alert: Alert; audit_hash: string }> {
  return fetchJson(`${API_BASE}/alerts/${id}/decide`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  });
}

export async function getAlertStats(): Promise<{ total: number; critical: number; active: number; reviewing: number; confirmed: number; dismissed: number }> {
  return fetchJson(`${API_BASE}/alerts/stats`);
}

export async function listCameras(): Promise<Camera[]> {
  return fetchJson<Camera[]>(`${API_BASE}/cameras`);
}

export async function getCamera(id: string): Promise<Camera> {
  return fetchJson<Camera>(`${API_BASE}/cameras/${id}`);
}

export async function saveCamera(cam: Camera): Promise<{ status: string; camera: Camera }> {
  return fetchJson(`${API_BASE}/cameras`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(cam)
  });
}

export async function uploadAnalysisVideo(file: File): Promise<AnalysisJobCreate> {
  const formData = new FormData();
  formData.append('file', file);
  return fetchJson<AnalysisJobCreate>(`${API_BASE}/analysis/upload`, {
    method: 'POST',
    body: formData
  });
}

export async function loadSampleAnalysisVideo(): Promise<AnalysisJobCreate> {
  return fetchJson<AnalysisJobCreate>(`${API_BASE}/analysis/sample`, {
    method: 'POST'
  });
}

export async function updateAnalysisZones(jobId: string, zones: { name: string; points: number[][] }[]): Promise<{ status: string; job_id: string; zones: any[] }> {
  return fetchJson(`${API_BASE}/analysis/${jobId}/zones`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ zones })
  });
}

export async function startAnalysis(jobId: string): Promise<{ status: string; job_id: string }> {
  return fetchJson(`${API_BASE}/analysis/${jobId}/start`, { method: 'POST' });
}

export async function getAnalysisStatus(jobId: string): Promise<AnalysisJobStatus> {
  return fetchJson<AnalysisJobStatus>(`${API_BASE}/analysis/${jobId}/status`);
}

export async function getAnalysisResult(jobId: string): Promise<AnalysisJobResult> {
  return fetchJson<AnalysisJobResult>(`${API_BASE}/analysis/${jobId}/result`);
}

export async function getSystemHealth(): Promise<any> {
  return fetchJson(`${API_BASE}/system/health`);
}

export async function verifySystemIntegrity(): Promise<any> {
  return fetchJson(`${API_BASE}/system/integrity/verify`);
}

export async function listAuditLogs(limit = 50): Promise<any[]> {
  return fetchJson<any[]>(`${API_BASE}/system/audit?limit=${limit}`);
}

export async function getTopology(): Promise<{ nodes: any[]; edges: any[] }> {
  return fetchJson(`${API_BASE}/topology`);
}

export async function getIdentityGhosts(): Promise<{ ghosts: any[] }> {
  return fetchJson(`${API_BASE}/identity/ghosts`);
}

export async function getAllSettings(): Promise<Record<string, any>> {
  return fetchJson(`${API_BASE}/settings`);
}

export async function updateSettingCategory(category: string, payload: Record<string, any>): Promise<any> {
  return fetchJson(`${API_BASE}/settings/${category}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
}

export async function getSettingsHistory(): Promise<any[]> {
  return fetchJson<any[]>(`${API_BASE}/settings/history/all`);
}

export async function getMetricsSummary(): Promise<any> {
  return fetchJson(`${API_BASE}/metrics/summary`);
}

export async function getCameraMetrics(): Promise<any[]> {
  return fetchJson<any[]>(`${API_BASE}/metrics/cameras`);
}

export async function getCameraHealth(): Promise<any[]> {
  return fetchJson<any[]>(`${API_BASE}/system/health/cameras`);
}

export async function restartCameraWorker(cameraId: string): Promise<any> {
  return fetchJson(`${API_BASE}/system/health/cameras/${cameraId}/restart`, { method: 'POST' });
}

export interface User {
  id: string;
  username: string;
  display_name: string;
  role: string;
  email: string;
  active: boolean;
  created_at: string;
  updated_at: string;
}

export async function listUsers(): Promise<User[]> {
  return fetchJson<User[]>(`${API_BASE}/users`);
}

export async function createUser(body: { username: string; display_name: string; role: string; email?: string }): Promise<{ status: string; user: User }> {
  return fetchJson(`${API_BASE}/users`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  });
}

export async function updateUser(userId: string, body: Partial<{ display_name: string; role: string; email: string; active: boolean }>): Promise<{ status: string; user: User }> {
  return fetchJson(`${API_BASE}/users/${userId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  });
}

export async function deleteUser(userId: string): Promise<{ status: string; user_id: string }> {
  return fetchJson(`${API_BASE}/users/${userId}`, { method: 'DELETE' });
}
