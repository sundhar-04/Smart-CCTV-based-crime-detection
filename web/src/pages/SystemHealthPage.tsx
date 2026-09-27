import React, { useState, useEffect } from 'react';
import { getSystemHealth, getCameraHealth, restartCameraWorker } from '../api/client';
import { ICN } from '../components/Icon';

export function SystemHealthPage() {
  const [health, setHealth] = useState<any>(null);
  const [camHealth, setCamHealth] = useState<any[]>([]);

  useEffect(() => {
    const fetchAll = () => {
      getSystemHealth().then(setHealth).catch(console.error);
      getCameraHealth().then(setCamHealth).catch(console.error);
    };
    fetchAll();
    const interval = setInterval(fetchAll, 5000);
    return () => clearInterval(interval);
  }, []);

  const handleRestart = async (camId: string) => {
    try {
      await restartCameraWorker(camId);
      getCameraHealth().then(setCamHealth).catch(console.error);
    } catch (err: any) {
      alert(`Restart failed: ${err.message}`);
    }
  };

  return (
    <div className="fade-in">
      <div className="page-header">
        <div>
          <div className="page-title">System Health & Hardware Diagnostics</div>
          <div className="page-sub">Host metrics, CPU/GPU utilization & backend service vitals</div>
        </div>
      </div>

      <div className="kpi-grid">
        <div className="kpi-card">
          <div className="kpi-label">CPU Usage</div>
          <div className="kpi-value">{health?.cpu?.percent || 0}%</div>
          <div className="kpi-delta">{health?.cpu?.cores} Physical Cores</div>
        </div>

        <div className="kpi-card">
          <div className="kpi-label">Memory Used</div>
          <div className="kpi-value">{health?.memory?.used_gb || 0} GB</div>
          <div className="kpi-delta">Total: {health?.memory?.total_gb || 0} GB</div>
        </div>

        <div className="kpi-card">
          <div className="kpi-label">Disk Usage</div>
          <div className="kpi-value">{health?.disk?.percent || 0}%</div>
          <div className="kpi-delta">Used: {health?.disk?.used_gb || 0} GB</div>
        </div>

        <div className="kpi-card">
          <div className="kpi-label">System State</div>
          <div className="kpi-value" style={{ color: 'var(--safe)' }}>HEALTHY</div>
          <div className="kpi-delta" style={{ color: 'var(--safe)' }}>All Services Online</div>
        </div>
      </div>

      <div className="panel" style={{ marginTop: 16 }}>
        <div className="panel-title-row">
          <span className="panel-title">Core Inference & Engine Microservices</span>
        </div>
        <div className="panel-body" style={{ padding: 0 }}>
          {health?.services &&
            Object.entries(health.services).map(([service, status]: [string, any]) => (
              <div key={service} className="list-row" style={{ padding: '12px 16px' }}>
                {ICN.cpu({ size: 16, style: { color: 'var(--accent)' } })}
                <div style={{ flex: 1, textTransform: 'capitalize', fontWeight: 600 }}>
                  {service.replace('_', ' ')}
                </div>
                <span className="badge safe">{status}</span>
              </div>
            ))}
        </div>
      </div>

      <div className="panel" style={{ marginTop: 16 }}>
        <div className="panel-title-row">
          <span className="panel-title">Camera Worker Status</span>
        </div>
        <div className="panel-body" style={{ padding: 0 }}>
          <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr 1fr 1fr 1fr 1fr', padding: '8px 16px', fontSize: 11, fontWeight: 700, color: 'var(--text-low)', borderBottom: '1px solid var(--border-soft)' }}>
            <span>Camera</span>
            <span>Status</span>
            <span>FPS</span>
            <span>Skip Rate</span>
            <span>Queue</span>
            <span>Uptime</span>
            <span>Action</span>
          </div>
          {camHealth.map(cam => (
            <div key={cam.camera_id} className="list-row" style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr 1fr 1fr 1fr 1fr', alignItems: 'center', padding: '10px 16px' }}>
              <div>
                <div style={{ fontWeight: 600, fontSize: 13 }}>{cam.camera_name}</div>
                <div className="mono" style={{ fontSize: 10, color: 'var(--text-low)' }}>{cam.camera_id}</div>
              </div>
              <span className={`badge ${cam.status === 'online' ? 'safe' : cam.status === 'degraded' ? 'warning' : 'danger'}`}>
                {cam.status}
              </span>
              <span className="mono" style={{ fontSize: 12 }}>{cam.fps}</span>
              <span className="mono" style={{ fontSize: 12 }}>{(cam.skip_rate * 100).toFixed(0)}%</span>
              <span className="mono" style={{ fontSize: 12 }}>{cam.queue_depth}</span>
              <span className="mono" style={{ fontSize: 12 }}>{cam.uptime_pct}%</span>
              <button className="btn sm" onClick={() => handleRestart(cam.camera_id)}>
                {ICN.restart({ size: 12 })} Restart
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
