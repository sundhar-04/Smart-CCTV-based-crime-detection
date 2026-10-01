import React, { useState, useEffect, useRef, useCallback } from 'react';
import { listCameras, updateCameraPosition, testCameraConnection, Camera } from '../api/client';
import { StatusDot } from '../components/StatusDot';
import { ICN } from '../components/Icon';
import { wsClient } from '../ws/client';

interface ActiveAlertState {
  [cameraId: string]: {
    level: string;
    score: number;
    timestamp: number;
  };
}

export function CameraMapPage() {
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [selectedCamId, setSelectedCamId] = useState<string | null>(null);
  const [activeAlerts, setActiveAlerts] = useState<ActiveAlertState>({});
  const [isEditMode, setIsEditMode] = useState(false);
  const [draggingCamId, setDraggingCamId] = useState<string | null>(null);
  const [dragPos, setDragPos] = useState<{ x: number; y: number } | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<'all' | 'online' | 'offline' | 'alert'>('all');
  const [snapshotTs, setSnapshotTs] = useState(Date.now());
  const [testResult, setTestResult] = useState<{ status: string; message: string } | null>(null);
  const [isTesting, setIsTesting] = useState(false);
  const [liveStreamMode, setLiveStreamMode] = useState(false);
  const [toastMsg, setToastMsg] = useState<string | null>(null);

  const mapContainerRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  // Helper to normalize coordinates safely to [5%, 95%] percentage
  const getCamCoords = useCallback((cam: Camera, index: number) => {
    // If currently dragging this camera, use live drag position
    if (draggingCamId === cam.id && dragPos) {
      return dragPos;
    }
    let x = cam.map_x;
    let y = cam.map_y;
    if (x === undefined || x === null || isNaN(x) || (x === 0 && y === 0)) {
      x = 22 + (index % 3) * 28;
      y = 22 + Math.floor(index / 3) * 28;
    } else {
      if (x <= 1.0) x = x * 100;
      if (y <= 1.0) y = y * 100;
    }
    return {
      x: Math.max(6, Math.min(94, Math.round(x * 10) / 10)),
      y: Math.max(6, Math.min(94, Math.round(y * 10) / 10))
    };
  }, [draggingCamId, dragPos]);

  // Load cameras
  const fetchCameras = useCallback(() => {
    listCameras().then(cams => {
      setCameras(cams);
      if (!selectedCamId && cams.length > 0) {
        setSelectedCamId(cams[0].id);
      }
    }).catch(console.error);
  }, [selectedCamId]);

  // Initial load + Real-time listeners & Polling
  useEffect(() => {
    fetchCameras();

    // 1. Continuous polling fallback (every 3 seconds) for live FPS & status
    const pollInterval = setInterval(() => {
      listCameras().then(freshCams => {
        setCameras(prev => {
          // Keep drag positions intact while dragging
          return freshCams.map(fresh => {
            const existing = prev.find(p => p.id === fresh.id);
            return existing ? { ...existing, ...fresh } : fresh;
          });
        });
      }).catch(() => {});
    }, 3000);

    // 2. Snapshot refresh for live feed preview (every 1 second)
    const snapInterval = setInterval(() => {
      setSnapshotTs(Date.now());
    }, 1000);

    // 3. WebSocket: Camera Status Changed
    const unsubStatus = wsClient.subscribe('camera_status_changed', (msg: any) => {
      const data = msg?.data || msg;
      if (data?.camera_id) {
        setCameras(prev => prev.map(c => c.id === data.camera_id ? {
          ...c,
          status: data.status || c.status,
          fps: data.fps !== undefined ? data.fps : c.fps,
          error: data.error
        } : c));
      }
    });

    // 4. WebSocket: Camera Position Updated (from other operator or self)
    const unsubPos = wsClient.subscribe('camera_position_updated', (msg: any) => {
      const data = msg?.data || msg;
      if (data?.camera_id) {
        setCameras(prev => prev.map(c => c.id === data.camera_id ? {
          ...c,
          map_x: data.map_x,
          map_y: data.map_y
        } : c));
      }
    });

    // 5. WebSocket: Live Alerts (Highlight cameras with active crime alerts)
    const unsubAlert = wsClient.subscribe('new_alert', (msg: any) => {
      const data = msg?.data || msg;
      if (data?.camera_id) {
        setActiveAlerts(prev => ({
          ...prev,
          [data.camera_id]: {
            level: data.risk_level || 'CRITICAL',
            score: data.risk_score || 85,
            timestamp: Date.now()
          }
        }));
      }
    });

    return () => {
      clearInterval(pollInterval);
      clearInterval(snapInterval);
      unsubStatus();
      unsubPos();
      unsubAlert();
    };
  }, [fetchCameras]);

  // Clean up alerts after 20 seconds
  useEffect(() => {
    const alertCleaner = setInterval(() => {
      const now = Date.now();
      setActiveAlerts(prev => {
        let changed = false;
        const next: ActiveAlertState = {};
        for (const [k, v] of Object.entries(prev)) {
          if (now - v.timestamp < 20000) {
            next[k] = v;
          } else {
            changed = true;
          }
        }
        return changed ? next : prev;
      });
    }, 4000);
    return () => clearInterval(alertCleaner);
  }, []);

  // Show transient toast
  const showToast = (msg: string) => {
    setToastMsg(msg);
    setTimeout(() => setToastMsg(null), 3000);
  };

  // Test camera connection handler
  const handleTestConnection = async (cam: Camera) => {
    setIsTesting(true);
    setTestResult(null);
    try {
      const streamUrl = cam.stream_url || cam.rtsp_url || '';
      const res = await testCameraConnection(streamUrl, cam.protocol || 'mjpeg');
      if (res.status === 'CONNECTED') {
        setTestResult({
          status: 'success',
          message: `Reachable! ${res.width || 1280}x${res.height || 720} @ ${Math.round(res.fps || 25)} FPS`
        });
        showToast(`Camera ${cam.name} is ONLINE & reachable`);
      } else {
        setTestResult({
          status: 'failed',
          message: res.error || 'Connection timed out or stream unreachable'
        });
      }
    } catch (err: any) {
      setTestResult({
        status: 'failed',
        message: err.message || 'Network test failed'
      });
    } finally {
      setIsTesting(false);
    }
  };

  // Drag and Drop handling for repositioning cameras
  const handleMouseDown = (camId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setSelectedCamId(camId);
    if (!isEditMode) return;
    setDraggingCamId(camId);
  };

  const handleMouseMove = useCallback((e: MouseEvent) => {
    if (!draggingCamId || !mapContainerRef.current) return;
    const rect = mapContainerRef.current.getBoundingClientRect();
    const rawX = ((e.clientX - rect.left) / rect.width) * 100;
    const rawY = ((e.clientY - rect.top) / rect.height) * 100;
    const clampedX = Math.max(6, Math.min(94, Math.round(rawX * 10) / 10));
    const clampedY = Math.max(6, Math.min(94, Math.round(rawY * 10) / 10));
    setDragPos({ x: clampedX, y: clampedY });
  }, [draggingCamId]);

  const handleMouseUp = useCallback(async () => {
    if (!draggingCamId || !dragPos) {
      setDraggingCamId(null);
      setDragPos(null);
      return;
    }
    const finalCamId = draggingCamId;
    const finalX = dragPos.x;
    const finalY = dragPos.y;

    setDraggingCamId(null);
    setDragPos(null);

    // Optimistically update local state
    setCameras(prev => prev.map(c => c.id === finalCamId ? { ...c, map_x: finalX / 100, map_y: finalY / 100 } : c));

    try {
      await updateCameraPosition(finalCamId, finalX / 100, finalY / 100);
      showToast(`Position saved: X: ${finalX}% · Y: ${finalY}%`);
    } catch (err) {
      console.error('Failed to save camera position:', err);
      showToast('Error saving position to backend');
      fetchCameras();
    }
  }, [draggingCamId, dragPos, fetchCameras]);

  // Click on map to place camera when in edit mode
  const handleMapClick = async (e: React.MouseEvent<HTMLDivElement>) => {
    if (!isEditMode || !selectedCamId || draggingCamId || !mapContainerRef.current) return;
    const rect = mapContainerRef.current.getBoundingClientRect();
    const rawX = ((e.clientX - rect.left) / rect.width) * 100;
    const rawY = ((e.clientY - rect.top) / rect.height) * 100;
    const finalX = Math.max(6, Math.min(94, Math.round(rawX * 10) / 10));
    const finalY = Math.max(6, Math.min(94, Math.round(rawY * 10) / 10));

    setCameras(prev => prev.map(c => c.id === selectedCamId ? { ...c, map_x: finalX / 100, map_y: finalY / 100 } : c));
    try {
      await updateCameraPosition(selectedCamId, finalX / 100, finalY / 100);
      showToast(`Camera placed at X: ${finalX}% · Y: ${finalY}%`);
    } catch (err) {
      console.error('Failed to set position:', err);
    }
  };

  useEffect(() => {
    if (draggingCamId) {
      window.addEventListener('mousemove', handleMouseMove);
      window.addEventListener('mouseup', handleMouseUp);
      return () => {
        window.removeEventListener('mousemove', handleMouseMove);
        window.removeEventListener('mouseup', handleMouseUp);
      };
    }
  }, [draggingCamId, handleMouseMove, handleMouseUp]);

  // Draw Tactical Canvas Blueprint
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);

    let animationFrameId: number;
    let scanAngle = 0;

    function renderCanvas() {
      if (!canvas) return;
      const rect = canvas.parentElement!.getBoundingClientRect();
      canvas.width = rect.width * dpr;
      canvas.height = rect.height * dpr;
      canvas.style.width = rect.width + 'px';
      canvas.style.height = rect.height + 'px';
      ctx!.setTransform(dpr, 0, 0, dpr, 0, 0);

      const w = rect.width;
      const h = rect.height;
      ctx!.clearRect(0, 0, w, h);

      // 1. Tactical Grid Lines
      ctx!.strokeStyle = 'rgba(76, 158, 255, 0.05)';
      ctx!.lineWidth = 1;
      for (let x = 0; x < w; x += 36) {
        ctx!.beginPath(); ctx!.moveTo(x, 0); ctx!.lineTo(x, h); ctx!.stroke();
      }
      for (let y = 0; y < h; y += 36) {
        ctx!.beginPath(); ctx!.moveTo(0, y); ctx!.lineTo(w, y); ctx!.stroke();
      }

      // 2. Blueprint Architectural Zones
      // Zone A: Perimeter Secure Entry
      ctx!.fillStyle = 'rgba(76, 158, 255, 0.035)';
      ctx!.fillRect(w * 0.04, h * 0.06, w * 0.42, h * 0.42);
      ctx!.strokeStyle = 'rgba(76, 158, 255, 0.18)';
      ctx!.strokeRect(w * 0.04, h * 0.06, w * 0.42, h * 0.42);

      // Zone B: Central Concourse & Public Corridor
      ctx!.fillStyle = 'rgba(61, 214, 140, 0.03)';
      ctx!.fillRect(w * 0.50, h * 0.08, w * 0.45, h * 0.38);
      ctx!.strokeStyle = 'rgba(61, 214, 140, 0.16)';
      ctx!.strokeRect(w * 0.50, h * 0.08, w * 0.45, h * 0.38);

      // Zone C: Restricted Vault & Server Ops
      ctx!.fillStyle = 'rgba(229, 72, 77, 0.035)';
      ctx!.fillRect(w * 0.12, h * 0.54, w * 0.76, h * 0.38);
      ctx!.strokeStyle = 'rgba(229, 72, 77, 0.16)';
      ctx!.strokeRect(w * 0.12, h * 0.54, w * 0.76, h * 0.38);

      // Zone Typography
      ctx!.font = '600 10px JetBrains Mono, monospace';
      ctx!.fillStyle = 'rgba(76, 158, 255, 0.45)';
      ctx!.fillText('ZONE 01 // NORTH PERIMETER', w * 0.06, h * 0.11);

      ctx!.fillStyle = 'rgba(61, 214, 140, 0.45)';
      ctx!.fillText('ZONE 02 // PUBLIC LOBBY & CORRIDOR', w * 0.52, h * 0.13);

      ctx!.fillStyle = 'rgba(229, 72, 77, 0.45)';
      ctx!.fillText('ZONE 03 // RESTRICTED ACCESS & VAULT', w * 0.14, h * 0.59);

      // 3. Inter-Camera Surveillance Network Mesh (connect adjacent active cameras)
      const points = cameras.map((c, i) => {
        const coords = getCamCoords(c, i);
        return {
          id: c.id,
          x: (coords.x / 100) * w,
          y: (coords.y / 100) * h,
          isOnline: isCameraOnline(c.status)
        };
      });

      ctx!.lineWidth = 1.2;
      for (let i = 0; i < points.length; i++) {
        for (let j = i + 1; j < points.length; j++) {
          const p1 = points[i];
          const p2 = points[j];
          const dist = Math.hypot(p1.x - p2.x, p1.y - p2.y);
          if (dist < w * 0.65) {
            ctx!.beginPath();
            ctx!.setLineDash([4, 6]);
            ctx!.strokeStyle = p1.isOnline && p2.isOnline ? 'rgba(61, 214, 140, 0.14)' : 'rgba(76, 158, 255, 0.07)';
            ctx!.moveTo(p1.x, p1.y);
            ctx!.lineTo(p2.x, p2.y);
            ctx!.stroke();
            ctx!.setLineDash([]);
          }
        }
      }

      // 4. Subtle Ambient Radar Sweep
      scanAngle += 0.012;
      const radarCenterX = w * 0.5;
      const radarCenterY = h * 0.5;
      const radarRadius = Math.min(w, h) * 0.48;

      ctx!.save();
      ctx!.beginPath();
      ctx!.arc(radarCenterX, radarCenterY, radarRadius, 0, Math.PI * 2);
      ctx!.strokeStyle = 'rgba(76, 158, 255, 0.05)';
      ctx!.lineWidth = 1;
      ctx!.stroke();

      // Radar sweep line
      const sweepX = radarCenterX + Math.cos(scanAngle) * radarRadius;
      const sweepY = radarCenterY + Math.sin(scanAngle) * radarRadius;
      ctx!.beginPath();
      ctx!.moveTo(radarCenterX, radarCenterY);
      ctx!.lineTo(sweepX, sweepY);
      ctx!.strokeStyle = 'rgba(76, 158, 255, 0.15)';
      ctx!.lineWidth = 1.5;
      ctx!.stroke();
      ctx!.restore();

      animationFrameId = requestAnimationFrame(renderCanvas);
    }

    renderCanvas();

    return () => {
      cancelAnimationFrame(animationFrameId);
    };
  }, [cameras, getCamCoords]);

  const isCameraOnline = (status: string) => {
    const s = (status || '').toLowerCase();
    return s === 'online' || s === 'connected';
  };

  const onlineCams = cameras.filter(c => isCameraOnline(c.status)).length;
  const offlineCams = cameras.length - onlineCams;
  const alertCamCount = Object.keys(activeAlerts).length;

  const selectedCam = cameras.find(c => c.id === selectedCamId) || cameras[0] || null;

  // Filtered cameras for roster
  const filteredCameras = cameras.filter(c => {
    const matchesSearch = c.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
                          c.id.toLowerCase().includes(searchQuery.toLowerCase()) ||
                          c.location.toLowerCase().includes(searchQuery.toLowerCase());
    if (!matchesSearch) return false;
    if (statusFilter === 'online') return isCameraOnline(c.status);
    if (statusFilter === 'offline') return !isCameraOnline(c.status);
    if (statusFilter === 'alert') return Boolean(activeAlerts[c.id]);
    return true;
  });

  return (
    <div className="fade-in" style={{ height: 'calc(100vh - 84px)', display: 'flex', flexDirection: 'column' }}>
      {/* Top Header & Operational Bar */}
      <div className="page-header" style={{ marginBottom: 12, flexShrink: 0 }}>
        <div>
          <div className="page-title" style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            {ICN.map({ size: 20, style: { color: 'var(--accent)' } })}
            Real-Time Facility Camera Map
          </div>
          <div className="page-sub">
            Live geospatial positioning & active threat telemetry across monitored security zones
          </div>
        </div>

        <div className="page-actions" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {/* Status Metrics */}
          <div className="chip" style={{ background: 'rgba(61,214,140,0.1)', borderColor: 'rgba(61,214,140,0.3)', color: '#3DD68C' }}>
            <span className="dot safe" /> {onlineCams} Online
          </div>
          {offlineCams > 0 && (
            <div className="chip" style={{ background: 'rgba(74,85,104,0.1)', borderColor: 'rgba(74,85,104,0.3)', color: 'var(--text-mid)' }}>
              <span className="dot offline" /> {offlineCams} Offline
            </div>
          )}
          {alertCamCount > 0 && (
            <div className="chip" style={{ background: 'rgba(229,72,77,0.15)', borderColor: 'rgba(229,72,77,0.4)', color: '#FF4D4F' }}>
              <span className="dot critical" /> {alertCamCount} Crime Threat
            </div>
          )}

          {/* Mode Switch Button */}
          <button
            className={`btn ${isEditMode ? 'primary' : 'ghost'}`}
            style={{ fontSize: 12, padding: '6px 12px', gap: 6 }}
            onClick={() => setIsEditMode(prev => !prev)}
            title="Toggle repositioning mode to drag camera pins on the floor plan"
          >
            {ICN.target({ size: 14 })}
            {isEditMode ? 'Finish Layout' : 'Reposition Cameras'}
          </button>
        </div>
      </div>

      {/* Main Grid View */}
      <div style={{ flex: 1, display: 'grid', gridTemplateColumns: '1fr 380px', gap: 14, minHeight: 0 }}>
        {/* Interactive Tactical Map Panel */}
        <div
          ref={mapContainerRef}
          onClick={handleMapClick}
          className="panel"
          style={{
            position: 'relative',
            background: '#070A10',
            overflow: 'hidden',
            border: isEditMode ? '1px dashed var(--accent)' : '1px solid var(--border-soft)',
            borderRadius: 8,
            boxShadow: 'inset 0 0 40px rgba(0,0,0,0.8)',
            cursor: isEditMode ? 'crosshair' : 'default',
            display: 'flex',
            flexDirection: 'column'
          }}
        >
          {/* Tactical Canvas Background */}
          <canvas ref={canvasRef} style={{ width: '100%', height: '100%', display: 'block', position: 'absolute', top: 0, left: 0 }} />

          {/* Top HUD Overlay */}
          <div style={{ position: 'absolute', top: 12, left: 14, zIndex: 10, display: 'flex', alignItems: 'center', gap: 10 }}>
            <span className="mono" style={{ fontSize: 10.5, color: 'var(--text-low)', letterSpacing: '0.08em', background: 'rgba(10,14,22,0.85)', padding: '3px 8px', borderRadius: 4, border: '1px solid rgba(255,255,255,0.08)' }}>
              FACILITY SATELLITE / GRID BLUEPRINT // EPSG:3857
            </span>
            {isEditMode && (
              <span className="badge" style={{ background: 'var(--accent)', color: '#000', fontWeight: 700, fontSize: 10.5 }}>
                EDIT MODE: Drag pins to position
              </span>
            )}
          </div>

          {/* Compass Rose */}
          <div style={{ position: 'absolute', top: 12, right: 14, zIndex: 10, background: 'rgba(10,14,22,0.85)', padding: '4px 10px', borderRadius: 4, border: '1px solid rgba(255,255,255,0.08)', color: 'var(--text-low)', fontSize: 10, fontFamily: 'monospace' }}>
            N ▲ 000°
          </div>

          {/* Transient Toast Overlay */}
          {toastMsg && (
            <div style={{ position: 'absolute', bottom: 16, left: '50%', transform: 'translateX(-50%)', zIndex: 30, background: 'rgba(13,18,28,0.95)', border: '1px solid var(--accent)', color: 'var(--text-hi)', padding: '6px 16px', borderRadius: 6, fontSize: 11.5, fontWeight: 600, boxShadow: '0 4px 16px rgba(0,0,0,0.6)' }}>
              {toastMsg}
            </div>
          )}

          {/* Live Camera Markers */}
          {cameras.map((cam, idx) => {
            const coords = getCamCoords(cam, idx);
            const isOnline = isCameraOnline(cam.status);
            const isSelected = selectedCam?.id === cam.id;
            const hasAlert = Boolean(activeAlerts[cam.id]);
            const isDragging = draggingCamId === cam.id;

            const markerColor = hasAlert ? '#EF4444' : (isOnline ? '#3DD68C' : '#64748B');

            return (
              <div
                key={cam.id}
                onMouseDown={(e) => handleMouseDown(cam.id, e)}
                onClick={(e) => { e.stopPropagation(); setSelectedCamId(cam.id); }}
                style={{
                  position: 'absolute',
                  left: `${coords.x}%`,
                  top: `${coords.y}%`,
                  transform: 'translate(-50%, -50%)',
                  zIndex: isDragging ? 40 : (isSelected ? 25 : 15),
                  cursor: isEditMode ? (isDragging ? 'grabbing' : 'grab') : 'pointer',
                  userSelect: 'none',
                  transition: isDragging ? 'none' : 'transform 0.15s ease, left 0.2s ease, top 0.2s ease'
                }}
              >
                {/* Field-of-View Visual Cone */}
                <div
                  style={{
                    position: 'absolute',
                    width: 70,
                    height: 70,
                    top: -25,
                    left: -25,
                    borderRadius: '50%',
                    background: hasAlert
                      ? 'radial-gradient(circle, rgba(239,68,68,0.3) 0%, transparent 70%)'
                      : (isOnline ? 'radial-gradient(circle, rgba(61,214,140,0.2) 0%, transparent 70%)' : 'none'),
                    pointerEvents: 'none',
                    zIndex: -1
                  }}
                />

                {/* Animated Pulsing Beacon for Online/Alert Cameras */}
                {(isOnline || hasAlert) && (
                  <div
                    style={{
                      position: 'absolute',
                      width: 28,
                      height: 28,
                      top: -4,
                      left: -4,
                      borderRadius: '50%',
                      border: `1.5px solid ${markerColor}`,
                      animation: hasAlert ? 'ping 1s cubic-bezier(0, 0, 0.2, 1) infinite' : 'pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite',
                      opacity: 0.6,
                      pointerEvents: 'none'
                    }}
                  />
                )}

                {/* Target Pin Center */}
                <div
                  style={{
                    width: 20,
                    height: 20,
                    borderRadius: '50%',
                    background: isSelected ? '#FFFFFF' : markerColor,
                    border: `3px solid ${isSelected ? markerColor : '#090D14'}`,
                    boxShadow: isSelected
                      ? `0 0 16px ${markerColor}, 0 0 24px rgba(255,255,255,0.4)`
                      : `0 0 10px ${markerColor}`,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    color: '#000'
                  }}
                >
                  <div style={{ width: 6, height: 6, borderRadius: '50%', background: isSelected ? markerColor : '#090D14' }} />
                </div>

                {/* Tactical Selection Reticle */}
                {isSelected && (
                  <div
                    style={{
                      position: 'absolute',
                      width: 34,
                      height: 34,
                      top: -7,
                      left: -7,
                      border: '1.5px dashed var(--accent)',
                      borderRadius: 4,
                      pointerEvents: 'none'
                    }}
                  />
                )}

                {/* Floating Real-Time Label Badge */}
                <div
                  style={{
                    position: 'absolute',
                    top: 24,
                    left: '50%',
                    transform: 'translateX(-50%)',
                    background: 'rgba(9, 13, 20, 0.92)',
                    backdropFilter: 'blur(6px)',
                    border: `1px solid ${isSelected ? 'var(--accent)' : 'rgba(255,255,255,0.12)'}`,
                    borderRadius: 4,
                    padding: '3px 7px',
                    display: 'flex',
                    alignItems: 'center',
                    gap: 5,
                    whiteSpace: 'nowrap',
                    boxShadow: '0 3px 10px rgba(0,0,0,0.5)',
                    pointerEvents: 'none'
                  }}
                >
                  <StatusDot status={cam.status} />
                  <span style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-hi)' }}>
                    {cam.name}
                  </span>
                  {isOnline && (
                    <span className="mono" style={{ fontSize: 9, color: 'var(--safe)', marginLeft: 2 }}>
                      {Math.round(cam.fps || 25)} FPS
                    </span>
                  )}
                  {hasAlert && (
                    <span className="mono" style={{ fontSize: 9, color: '#EF4444', fontWeight: 800 }}>
                      ⚠️ ALERT
                    </span>
                  )}
                </div>
              </div>
            );
          })}
        </div>

        {/* Camera Inspector & Roster Sidebar */}
        <div className="panel" style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
          {/* Header */}
          <div className="panel-title-row" style={{ flexShrink: 0 }}>
            <span className="panel-title" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              {ICN.camera({ size: 14 })} Camera Telemetry
            </span>
            {selectedCam && (
              <span className="mono" style={{ fontSize: 10, color: 'var(--text-low)' }}>
                {selectedCam.id}
              </span>
            )}
          </div>

          {/* Inspector Body */}
          <div className="panel-body scroll-thin" style={{ flex: 1, overflowY: 'auto', padding: '12px 14px' }}>
            {selectedCam ? (
              <div>
                {/* Live Preview Window */}
                <div className="cam-tile" style={{ height: 180, marginBottom: 14, position: 'relative' }}>
                  <div className="cam-tile-topbar">
                    <span className="chip" style={{ fontSize: 9 }}>
                      <StatusDot status={selectedCam.status} /> {isCameraOnline(selectedCam.status) ? 'LIVE STREAM' : 'STANDBY'}
                    </span>
                    <button
                      className="btn sm ghost"
                      style={{ marginLeft: 'auto', padding: '2px 6px', fontSize: 10 }}
                      onClick={() => setLiveStreamMode(prev => !prev)}
                    >
                      {liveStreamMode ? 'Snapshot Mode' : 'Direct Video'}
                    </button>
                  </div>

                  {liveStreamMode && isCameraOnline(selectedCam.status) ? (
                    <img
                      src={`/api/cameras/${selectedCam.id}/stream`}
                      alt="Live Stream"
                      style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                      onError={() => setLiveStreamMode(false)}
                    />
                  ) : (
                    <img
                      src={`/api/cameras/${selectedCam.id}/snapshot?t=${snapshotTs}`}
                      alt="Live Snapshot"
                      style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                      onError={(e) => {
                        (e.target as HTMLImageElement).src = 'data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="100%" height="100%" viewBox="0 0 100 100"><rect width="100" height="100" fill="%230c1017"/><text x="50" y="52" fill="%23555" font-size="6" text-anchor="middle" font-family="monospace">NO LIVE FEED AVAILABLE</text></svg>';
                      }}
                    />
                  )}

                  <div className="cam-tile-botbar">
                    <span className="mono" style={{ fontSize: 10, color: '#fff' }}>
                      {selectedCam.fps ? `${Math.round(selectedCam.fps)} FPS` : '0 FPS'} · {selectedCam.protocol?.toUpperCase() || 'MJPEG'}
                    </span>
                    <span className="mono" style={{ fontSize: 10, color: isCameraOnline(selectedCam.status) ? 'var(--safe)' : 'var(--text-low)' }}>
                      {selectedCam.status.toUpperCase()}
                    </span>
                  </div>
                </div>

                {/* Camera Identity Card */}
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
                  <div>
                    <div style={{ fontWeight: 700, fontSize: 15, color: 'var(--text-hi)' }}>{selectedCam.name}</div>
                    <div style={{ fontSize: 11, color: 'var(--text-low)', marginTop: 2 }}>{selectedCam.location || 'General Surveillance'}</div>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <div className="mono" style={{ fontSize: 12, fontWeight: 700, color: isCameraOnline(selectedCam.status) ? 'var(--safe)' : '#64748B' }}>
                      {selectedCam.status.toUpperCase()}
                    </div>
                  </div>
                </div>

                {/* Real-time KPI Cards Grid */}
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 14 }}>
                  <div className="kpi-card" style={{ padding: '8px 10px' }}>
                    <div className="kpi-label">Frame Rate</div>
                    <div className="mono" style={{ fontSize: 15, fontWeight: 700, marginTop: 4, color: isCameraOnline(selectedCam.status) ? 'var(--safe)' : 'var(--text-low)' }}>
                      {selectedCam.fps ? `${selectedCam.fps} FPS` : 'Offline'}
                    </div>
                  </div>

                  <div className="kpi-card" style={{ padding: '8px 10px' }}>
                    <div className="kpi-label">Map Position</div>
                    <div className="mono" style={{ fontSize: 13, fontWeight: 700, marginTop: 4 }}>
                      X: {Math.round(getCamCoords(selectedCam, 0).x)}% · Y: {Math.round(getCamCoords(selectedCam, 0).y)}%
                    </div>
                  </div>

                  <div className="kpi-card" style={{ padding: '8px 10px' }}>
                    <div className="kpi-label">Security Zone</div>
                    <div style={{ fontSize: 12, fontWeight: 600, marginTop: 4 }}>
                      {selectedCam.zone_type || 'Perimeter'}
                    </div>
                  </div>

                  <div className="kpi-card" style={{ padding: '8px 10px' }}>
                    <div className="kpi-label">Threat Level</div>
                    <div className="mono" style={{ fontSize: 12, fontWeight: 700, marginTop: 4, color: activeAlerts[selectedCam.id] ? '#EF4444' : 'var(--safe)' }}>
                      {activeAlerts[selectedCam.id] ? `${activeAlerts[selectedCam.id].level} (${activeAlerts[selectedCam.id].score})` : 'NOMINAL (SAFE)'}
                    </div>
                  </div>
                </div>

                {/* Action Buttons */}
                <div style={{ display: 'flex', gap: 8, marginBottom: 14 }}>
                  <button
                    className="btn sm"
                    style={{ flex: 1, justifyContent: 'center' }}
                    onClick={() => handleTestConnection(selectedCam)}
                    disabled={isTesting}
                  >
                    {isTesting ? ICN.refresh({ size: 12, className: 'spin' }) : ICN.wifi({ size: 12 })}
                    {isTesting ? 'Testing Link...' : 'Test Connection'}
                  </button>

                  <button
                    className={`btn sm ${isEditMode ? 'primary' : 'ghost'}`}
                    style={{ flex: 1, justifyContent: 'center' }}
                    onClick={() => setIsEditMode(prev => !prev)}
                  >
                    {ICN.target({ size: 12 })}
                    {isEditMode ? 'Lock Pin' : 'Reposition Pin'}
                  </button>
                </div>

                {/* Connection Test Result Box */}
                {testResult && (
                  <div
                    style={{
                      padding: '8px 10px',
                      borderRadius: 6,
                      fontSize: 11,
                      marginBottom: 12,
                      background: testResult.status === 'success' ? 'rgba(61,214,140,0.1)' : 'rgba(229,72,77,0.1)',
                      border: `1px solid ${testResult.status === 'success' ? 'rgba(61,214,140,0.3)' : 'rgba(229,72,77,0.3)'}`,
                      color: testResult.status === 'success' ? 'var(--safe)' : '#FF4D4F'
                    }}
                  >
                    <div style={{ fontWeight: 700, marginBottom: 2 }}>
                      {testResult.status === 'success' ? '✓ Stream Online' : '✕ Connection Warning'}
                    </div>
                    <div>{testResult.message}</div>
                  </div>
                )}
              </div>
            ) : (
              <div style={{ height: 220, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 10 }}>
                {ICN.crosshair({ size: 36, style: { opacity: 0.25 } })}
                <div style={{ fontSize: 12, color: 'var(--text-low)', textAlign: 'center' }}>
                  Select a camera marker on the map to view live telemetry
                </div>
              </div>
            )}

            {/* Camera Roster Header */}
            <div style={{ borderTop: '1px solid var(--border-soft)', paddingTop: 12, marginTop: 8 }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
                <span className="mono" style={{ fontSize: 10.5, fontWeight: 700, color: 'var(--text-mid)', letterSpacing: '0.04em' }}>
                  ALL MONITORED NODES ({cameras.length})
                </span>
                <span className="mono" style={{ fontSize: 9.5, color: 'var(--text-low)' }}>
                  UPDATES LIVE
                </span>
              </div>

              {/* Search & Filter Bar */}
              <div style={{ display: 'flex', gap: 6, marginBottom: 8 }}>
                <div style={{ flex: 1, position: 'relative' }}>
                  <input
                    type="text"
                    className="field"
                    placeholder="Search node..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    style={{ width: '100%', fontSize: 11, padding: '5px 8px' }}
                  />
                </div>
                <button
                  className={`btn sm ${statusFilter === 'all' ? 'active' : 'ghost'}`}
                  style={{ padding: '4px 8px', fontSize: 10 }}
                  onClick={() => setStatusFilter('all')}
                >
                  All
                </button>
                <button
                  className={`btn sm ${statusFilter === 'online' ? 'active' : 'ghost'}`}
                  style={{ padding: '4px 8px', fontSize: 10, color: 'var(--safe)' }}
                  onClick={() => setStatusFilter('online')}
                >
                  Online
                </button>
              </div>

              {/* Camera List Rows */}
              <div style={{ maxHeight: 180, overflowY: 'auto' }} className="scroll-thin">
                {filteredCameras.map((cam, idx) => {
                  const isOnline = isCameraOnline(cam.status);
                  const isSelected = selectedCam?.id === cam.id;
                  const hasAlert = Boolean(activeAlerts[cam.id]);

                  return (
                    <div
                      key={cam.id}
                      className="list-row"
                      onClick={() => setSelectedCamId(cam.id)}
                      style={{
                        padding: '7px 10px',
                        cursor: 'pointer',
                        borderRadius: 4,
                        marginBottom: 4,
                        background: isSelected ? 'rgba(76,158,255,0.1)' : 'transparent',
                        border: isSelected ? '1px solid rgba(76,158,255,0.3)' : '1px solid transparent',
                        display: 'flex',
                        alignItems: 'center',
                        gap: 8
                      }}
                    >
                      <StatusDot status={cam.status} />
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ fontWeight: 600, fontSize: 11.5, color: 'var(--text-hi)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {cam.name}
                        </div>
                        <div className="mono" style={{ fontSize: 9.5, color: 'var(--text-low)' }}>
                          {cam.location || cam.id}
                        </div>
                      </div>

                      <div style={{ textAlign: 'right' }}>
                        <span className="mono" style={{ fontSize: 10, fontWeight: 700, color: isOnline ? 'var(--safe)' : 'var(--text-low)' }}>
                          {isOnline ? `${Math.round(cam.fps || 25)} FPS` : 'OFFLINE'}
                        </span>
                        {hasAlert && (
                          <div style={{ fontSize: 9, color: '#EF4444', fontWeight: 800 }}>ALERT</div>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
