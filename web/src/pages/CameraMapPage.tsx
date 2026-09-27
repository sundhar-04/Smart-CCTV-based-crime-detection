import React, { useState, useEffect, useRef } from 'react';
import { listCameras, Camera } from '../api/client';
import { StatusDot } from '../components/StatusDot';
import { ICN } from '../components/Icon';

function MapCanvas({ cameras, onSelect }: { cameras: Camera[]; onSelect: (cam: Camera) => void }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);

    function resize() {
      const rect = canvas!.parentElement!.getBoundingClientRect();
      canvas!.width = rect.width * dpr;
      canvas!.height = rect.height * dpr;
      canvas!.style.width = rect.width + 'px';
      canvas!.style.height = rect.height + 'px';
      ctx!.setTransform(dpr, 0, 0, dpr, 0, 0);
      draw();
    }

    function draw() {
      const w = canvas!.width / dpr;
      const h = canvas!.height / dpr;
      ctx!.clearRect(0, 0, w, h);

      // Draw grid lines
      ctx!.strokeStyle = 'rgba(76,158,255,0.06)';
      ctx!.lineWidth = 1;
      for (let x = 0; x < w; x += 40) {
        ctx!.beginPath(); ctx!.moveTo(x, 0); ctx!.lineTo(x, h); ctx!.stroke();
      }
      for (let y = 0; y < h; y += 40) {
        ctx!.beginPath(); ctx!.moveTo(0, y); ctx!.lineTo(w, y); ctx!.stroke();
      }

      // Draw zone areas
      ctx!.fillStyle = 'rgba(76,158,255,0.03)';
      ctx!.fillRect(w * 0.05, h * 0.05, w * 0.4, h * 0.4);
      ctx!.fillStyle = 'rgba(61,214,140,0.03)';
      ctx!.fillRect(w * 0.5, h * 0.1, w * 0.45, h * 0.35);
      ctx!.fillStyle = 'rgba(229,72,77,0.03)';
      ctx!.fillRect(w * 0.2, h * 0.55, w * 0.6, h * 0.4);

      // Draw zone labels
      ctx!.font = '10px JetBrains Mono, monospace';
      ctx!.fillStyle = 'rgba(76,158,255,0.25)';
      ctx!.fillText('PERIMETER ZONE', w * 0.06, h * 0.1);
      ctx!.fillStyle = 'rgba(61,214,140,0.25)';
      ctx!.fillText('PUBLIC ZONE', w * 0.52, h * 0.15);
      ctx!.fillStyle = 'rgba(229,72,77,0.25)';
      ctx!.fillText('RESTRICTED ZONE', w * 0.22, h * 0.6);
    }

    resize();
    window.addEventListener('resize', resize);
    return () => window.removeEventListener('resize', resize);
  }, [cameras]);

  return <canvas ref={canvasRef} style={{ width: '100%', height: '100%', display: 'block', position: 'absolute', top: 0, left: 0 }} />;
}

export function CameraMapPage() {
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [selectedCam, setSelectedCam] = useState<Camera | null>(null);

  useEffect(() => {
    listCameras().then(setCameras).catch(console.error);
  }, []);

  const onlineCams = cameras.filter(c => c.status === 'online').length;
  const statusColor: Record<string, string> = { online: '#3DD68C', offline: '#4A5568', degraded: '#E6C560', alert: '#E5484D', maintenance: '#E6C560' };

  return (
    <div className="fade-in">
      <div className="page-header">
        <div>
          <div className="page-title">Camera Network Map</div>
          <div className="page-sub">Geospatial positioning of facility security cameras — {onlineCams} / {cameras.length} online</div>
        </div>
        <div className="page-actions">
          <div className="chip">
            <span className="dot safe" /> {onlineCams} Active
          </div>
          {cameras.filter(c => c.status !== 'online').length > 0 && (
            <div className="chip" style={{ borderColor: 'rgba(229,72,77,0.3)' }}>
              <span className="dot critical" /> {cameras.filter(c => c.status !== 'online').length} Degraded
            </div>
          )}
        </div>
      </div>

      <div className="grid-2col">
        {/* Map Canvas */}
        <div className="panel checker-noise" style={{ height: 520, position: 'relative', background: '#090D14', overflow: 'hidden' }}>
          <div className="scan-line" />
          <MapCanvas cameras={cameras} onSelect={setSelectedCam} />

          {/* Grid label */}
          <div style={{ position: 'absolute', top: 10, left: 12, zIndex: 5, display: 'flex', alignItems: 'center', gap: 6 }}>
            <span className="mono" style={{ fontSize: 10, color: 'var(--text-low)', letterSpacing: '0.04em' }}>
              FACILITY GRID MAP
            </span>
          </div>

          {/* Camera markers */}
          {cameras.map((cam) => (
            <div
              key={cam.id}
              className="marker-pin"
              style={{
                position: 'absolute',
                left: `${cam.map_x || (20 + Math.random() * 60)}%`,
                top: `${cam.map_y || (15 + Math.random() * 60)}%`,
                background: statusColor[cam.status] || '#4C9EFF',
                boxShadow: `0 0 12px ${statusColor[cam.status] || '#4C9EFF'}`,
                zIndex: selectedCam?.id === cam.id ? 10 : 3,
                transform: selectedCam?.id === cam.id ? 'scale(1.5)' : 'scale(1)',
              }}
              title={`${cam.id} — ${cam.name}`}
              onClick={() => setSelectedCam(cam)}
            />
          ))}
        </div>

        {/* Camera Inspector Sidebar */}
        <div className="panel" style={{ height: 520, display: 'flex', flexDirection: 'column' }}>
          <div className="panel-title-row">
            <span className="panel-title">Camera Inspector</span>
            {selectedCam && (
              <button className="btn sm ghost" onClick={() => setSelectedCam(null)}>
                {ICN.x({ size: 12 })} Clear
              </button>
            )}
          </div>
          <div className="panel-body scroll-thin" style={{ flex: 1, overflow: 'auto' }}>
            {selectedCam ? (
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
                  <StatusDot status={selectedCam.status} />
                  <div>
                    <div style={{ fontWeight: 700, fontSize: 15 }}>{selectedCam.name}</div>
                    <div style={{ fontSize: 11, color: 'var(--text-low)' }}>{selectedCam.id}</div>
                  </div>
                </div>

                {/* Details grid */}
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 16 }}>
                  <div className="kpi-card" style={{ padding: '10px 12px' }}>
                    <div className="kpi-label">Location</div>
                    <div style={{ fontSize: 12, fontWeight: 600, marginTop: 4 }}>{selectedCam.location}</div>
                  </div>
                  <div className="kpi-card" style={{ padding: '10px 12px' }}>
                    <div className="kpi-label">Frame Rate</div>
                    <div className="mono" style={{ fontSize: 16, fontWeight: 700, marginTop: 4 }}>{selectedCam.fps} FPS</div>
                  </div>
                  <div className="kpi-card" style={{ padding: '10px 12px' }}>
                    <div className="kpi-label">Zone Type</div>
                    <div style={{ fontSize: 12, fontWeight: 600, marginTop: 4 }}>{selectedCam.zone_type || 'General'}</div>
                  </div>
                  <div className="kpi-card" style={{ padding: '10px 12px' }}>
                    <div className="kpi-label">Status</div>
                    <div style={{ fontSize: 12, fontWeight: 600, marginTop: 4, textTransform: 'uppercase' as const,
                      color: selectedCam.status === 'online' ? 'var(--safe)' : 'var(--critical)' }}>
                      {selectedCam.status}
                    </div>
                  </div>
                </div>

                {/* Snapshot */}
                <div className="cam-tile" style={{ height: 180 }}>
                  <div className="cam-tile-topbar">
                    <span className="chip" style={{ fontSize: 9 }}>
                      <StatusDot status={selectedCam.status} /> LIVE
                    </span>
                  </div>
                  <img
                    src={`/api/cameras/${selectedCam.id}/snapshot`}
                    alt="Camera Live Snapshot"
                    style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                    onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
                  />
                  <div className="scan-line" />
                </div>
              </div>
            ) : (
              <div style={{ height: '100%', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 12 }}>
                {ICN.crosshair({ size: 40, style: { color: 'var(--text-low)', opacity: 0.3 } })}
                <div style={{ color: 'var(--text-low)', fontSize: 12.5, textAlign: 'center' }}>
                  Click any camera marker on the map to inspect its live feed and metadata.
                </div>
              </div>
            )}
          </div>

          {/* Camera list */}
          <div style={{ borderTop: '1px solid var(--border-soft)', maxHeight: 150, overflowY: 'auto' }}>
            {cameras.map(cam => (
              <div key={cam.id} className="list-row" style={{ padding: '8px 14px' }} onClick={() => setSelectedCam(cam)}>
                <StatusDot status={cam.status} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontWeight: 600, fontSize: 11.5 }}>{cam.name}</div>
                </div>
                <span className="mono" style={{ fontSize: 10, color: 'var(--text-low)' }}>{cam.id}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
