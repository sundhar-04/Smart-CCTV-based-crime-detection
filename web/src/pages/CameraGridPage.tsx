import React, { useState, useEffect } from 'react';
import { listCameras, deleteCamera, Camera } from '../api/client';
import { StatusDot } from '../components/StatusDot';
import { ICN } from '../components/Icon';
import { AddCameraModal } from '../components/AddCameraModal';
import { wsClient } from '../ws/client';

export function CameraGridPage() {
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [layout, setLayout] = useState<'2x2' | '3x3'>('2x2');
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingCamera, setEditingCamera] = useState<Camera | null>(null);
  const [refreshTs, setRefreshTs] = useState(Date.now());
  const [viewStreamId, setViewStreamId] = useState<string | null>(null);

  const fetchCameras = () => {
    listCameras().then(setCameras).catch(console.error);
  };

  useEffect(() => {
    fetchCameras();
    // Refresh timestamp every 4s for disconnected camera status cards
    const timer = setInterval(() => {
      setRefreshTs(Date.now());
    }, 4000);

    // Listen to real-time camera status updates via WebSocket
    const unsub = wsClient.subscribe('camera_status_changed', (msg: any) => {
      if (msg?.data?.camera_id) {
        setCameras(prev => prev.map(c => c.id === msg.data.camera_id ? {
          ...c,
          status: msg.data.status,
          fps: msg.data.fps || c.fps,
          error: msg.data.error
        } : c));
      }
    });

    return () => {
      clearInterval(timer);
      unsub();
    };
  }, []);

  const handleDelete = async (cam: Camera, e: React.MouseEvent) => {
    e.stopPropagation();
    if (window.confirm(`Are you sure you want to remove camera "${cam.name}" (${cam.id})?`)) {
      try {
        await deleteCamera(cam.id);
        fetchCameras();
      } catch (err: any) {
        alert(err.message || 'Failed to delete camera.');
      }
    }
  };

  const handleEdit = (cam: Camera, e: React.MouseEvent) => {
    e.stopPropagation();
    setEditingCamera(cam);
    setIsModalOpen(true);
  };

  const isConnected = (s: string) => {
    const st = (s || '').toUpperCase();
    return st === 'CONNECTED' || st === 'ONLINE';
  };

  const onlineCams = cameras.filter(c => isConnected(c.status)).length;

  return (
    <div className="fade-in">
      <div className="page-header">
        <div>
          <div className="page-title">Camera Grid View</div>
          <div className="page-sub">
            Live CCTV feeds & mobile phone cameras — {onlineCams} / {cameras.length} active
          </div>
        </div>
        <div className="page-actions" style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <button
            className="btn sm primary"
            onClick={() => {
              setEditingCamera(null);
              setIsModalOpen(true);
            }}
            style={{ display: 'flex', alignItems: 'center', gap: 6, fontWeight: 600 }}
          >
            {ICN.plus({ size: 13 })} Add Camera
          </button>
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
        gap: 12
      }}>
        {cameras.map((cam) => {
          const hue = ((cam.id.charCodeAt(cam.id.length - 1) || 0) * 37) % 360;
          const statusUpper = (cam.status || 'DISCONNECTED').toUpperCase();
          const live = isConnected(cam.status);
          const isStreaming = viewStreamId === cam.id;

          return (
            <div
              key={cam.id}
              className="cam-tile checker-noise"
              style={{
                height: layout === '2x2' ? 300 : 220,
                position: 'relative',
                border: statusUpper === 'ERROR' ? '1px solid rgba(248,81,73,0.4)' : undefined,
                overflow: 'hidden',
                borderRadius: 8
              }}
            >
              {/* Top bar */}
              <div className="cam-tile-topbar" style={{ zIndex: 10, background: 'linear-gradient(180deg, rgba(0,0,0,0.8) 0%, rgba(0,0,0,0) 100%)' }}>
                <span className="chip" style={{
                  background: live ? 'rgba(46,160,67,0.25)' : statusUpper === 'CONNECTING' ? 'rgba(210,153,34,0.25)' : 'rgba(0,0,0,0.6)',
                  border: `1px solid ${live ? 'rgba(46,160,67,0.5)' : statusUpper === 'CONNECTING' ? 'rgba(210,153,34,0.5)' : 'rgba(255,255,255,0.15)'}`
                }}>
                  <StatusDot status={cam.status} />
                  {statusUpper === 'ONLINE' ? 'CONNECTED' : statusUpper}
                </span>

                <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 6 }}>
                  {live && (
                    <span
                      style={{
                        padding: '2px 6px',
                        fontSize: 9,
                        fontWeight: 600,
                        background: 'rgba(46,160,67,0.2)',
                        color: '#3fb950',
                        borderRadius: 4,
                        border: '1px solid rgba(46,160,67,0.35)',
                        letterSpacing: '0.04em'
                      }}
                    >
                      LIVE STREAM
                    </span>
                  )}
                  <button
                    className="btn ghost sm"
                    title="Edit Camera"
                    onClick={(e) => handleEdit(cam, e)}
                    style={{ padding: '2px 6px', fontSize: 11, background: 'rgba(0,0,0,0.4)' }}
                  >
                    Edit
                  </button>
                  <button
                    className="btn ghost sm"
                    title="Delete Camera"
                    onClick={(e) => handleDelete(cam, e)}
                    style={{ padding: '2px 6px', fontSize: 11, background: 'rgba(0,0,0,0.4)', color: '#f85149' }}
                  >
                    {ICN.trash({ size: 12 })}
                  </button>
                </div>
              </div>

              {/* Camera Video / Snapshot View */}
              <div style={{
                width: '100%', height: '100%',
                background: `linear-gradient(135deg, hsl(${hue},30%,10%), hsl(${(hue + 40) % 360},25%,6%))`,
                display: 'flex', alignItems: 'center', justifyContent: 'center', position: 'relative'
              }}>
                <img
                  src={live ? `/api/cameras/${cam.id}/stream` : `/api/cameras/${cam.id}/snapshot?t=${refreshTs}`}
                  alt={cam.name}
                  style={{ width: '100%', height: '100%', objectFit: 'contain', background: '#0a0c10' }}
                  onError={(e) => {
                    // Fallback on stream error to snapshot
                    (e.target as HTMLImageElement).src = `/api/cameras/${cam.id}/snapshot?t=${Date.now()}`;
                  }}
                />

                {live && <div className="scan-line" />}

                {/* Error Banner Overlay if camera is in ERROR state */}
                {cam.error && (
                  <div style={{
                    position: 'absolute',
                    top: 42,
                    left: 10,
                    right: 10,
                    background: 'rgba(248, 81, 73, 0.85)',
                    color: '#fff',
                    padding: '4px 8px',
                    borderRadius: 4,
                    fontSize: 10,
                    zIndex: 5,
                    backdropFilter: 'blur(4px)',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap'
                  }}>
                    {cam.error}
                  </div>
                )}
              </div>

              {/* Bottom bar */}
              <div className="cam-tile-botbar" style={{
                background: 'linear-gradient(0deg, rgba(0,0,0,0.85) 0%, rgba(0,0,0,0.4) 70%, rgba(0,0,0,0) 100%)',
                padding: '10px 12px'
              }}>
                <div>
                  <div style={{ fontSize: 12, fontWeight: 600, color: '#fff' }}>{cam.name}</div>
                  <div style={{ fontSize: 10, color: 'rgba(255,255,255,0.6)', display: 'flex', gap: 6 }}>
                    <span>{cam.location}</span>
                    <span>·</span>
                    <span className="mono" style={{ textTransform: 'uppercase' }}>{cam.protocol || 'mjpeg'}</span>
                  </div>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <div className="mono" style={{ fontSize: 11, color: live ? 'var(--safe)' : 'var(--text-low)' }}>
                    {cam.fps || 0} FPS
                  </div>
                  {live && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: 4, justifyContent: 'flex-end' }}>
                      <span className="dot safe" style={{ width: 5, height: 5 }} />
                      <span className="mono" style={{ fontSize: 9, color: 'var(--safe)' }}>ANALYZING</span>
                    </div>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Add / Edit Camera Modal */}
      <AddCameraModal
        camera={editingCamera}
        isOpen={isModalOpen}
        onClose={() => {
          setIsModalOpen(false);
          setEditingCamera(null);
        }}
        onSaved={() => {
          fetchCameras();
        }}
      />
    </div>
  );
}
