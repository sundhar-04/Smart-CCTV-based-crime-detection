import React, { useState, useEffect } from 'react';
import { listCameras, Camera } from '../api/client';
import { StatusDot } from '../components/StatusDot';
import { ICN } from '../components/Icon';

export function CameraGridPage() {
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [layout, setLayout] = useState<'2x2' | '3x3'>('2x2');

  useEffect(() => {
    listCameras().then(setCameras).catch(console.error);
  }, []);

  const onlineCams = cameras.filter(c => c.status === 'online').length;

  return (
    <div className="fade-in">
      <div className="page-header">
        <div>
          <div className="page-title">Camera Grid View</div>
          <div className="page-sub">
            Live video feed overview — {onlineCams} / {cameras.length} cameras online
          </div>
        </div>
        <div className="page-actions">
          <button className={`btn sm ${layout === '2x2' ? 'primary' : ''}`} onClick={() => setLayout('2x2')}>
            {ICN.grid({ size: 12 })} 2×2
          </button>
          <button className={`btn sm ${layout === '3x3' ? 'primary' : ''}`} onClick={() => setLayout('3x3')}>
            {ICN.layers({ size: 12 })} 3×3
          </button>
        </div>
      </div>

      <div style={{
        display: 'grid',
        gridTemplateColumns: layout === '2x2' ? 'repeat(2, 1fr)' : 'repeat(3, 1fr)',
        gap: 10
      }}>
        {cameras.map((cam) => {
          const hue = ((cam.id.charCodeAt(cam.id.length - 1) || 0) * 37) % 360;
          const isOffline = cam.status === 'offline';

          return (
            <div key={cam.id} className="cam-tile checker-noise" style={{ height: layout === '2x2' ? 280 : 200, position: 'relative' }}>
              {/* Top bar */}
              <div className="cam-tile-topbar">
                <span className="chip">
                  <StatusDot status={cam.status} />
                  {cam.status === 'online' ? 'LIVE' : cam.status.toUpperCase()}
                </span>
                <span style={{ marginLeft: 'auto', fontSize: 10, color: '#fff' }} className="mono">
                  {cam.id}
                </span>
              </div>

              {/* Simulated camera feed */}
              {isOffline ? (
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', background: '#0a0c10' }}>
                  {ICN.wifiOff({ size: 32, style: { color: 'var(--text-low)', opacity: 0.5 } })}
                </div>
              ) : (
                <div style={{
                  width: '100%', height: '100%',
                  background: `linear-gradient(135deg, hsl(${hue},40%,12%), hsl(${(hue + 40) % 360},35%,8%))`,
                  display: 'flex', alignItems: 'center', justifyContent: 'center', position: 'relative'
                }}>
                  <img
                    src={`/api/cameras/${cam.id}/snapshot`}
                    alt={cam.name}
                    style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                    onError={(e) => {
                      (e.target as HTMLImageElement).style.display = 'none';
                    }}
                  />
                  <div className="scan-line" />
                </div>
              )}

              {/* Bottom bar */}
              <div className="cam-tile-botbar">
                <div>
                  <div style={{ fontSize: 12, fontWeight: 600, color: '#fff' }}>{cam.name}</div>
                  <div style={{ fontSize: 10, color: 'rgba(255,255,255,0.5)' }}>{cam.location}</div>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <div className="mono" style={{ fontSize: 11, color: cam.status === 'online' ? 'var(--safe)' : 'var(--text-low)' }}>
                    {cam.fps} FPS
                  </div>
                  {cam.status === 'online' && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                      <span className="dot safe" style={{ width: 5, height: 5 }} />
                      <span className="mono" style={{ fontSize: 9, color: 'var(--safe)' }}>REC</span>
                    </div>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
