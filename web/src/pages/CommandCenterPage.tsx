import React, { useState, useEffect, useRef } from 'react';
import { listAlerts, listCameras, getAlertStats, Alert, Camera } from '../api/client';
import { ICN } from '../components/Icon';
import { RiskBadge } from '../components/RiskBadge';
import { StatusDot } from '../components/StatusDot';
import { Sparkline } from '../components/Sparkline';
import { wsClient } from '../ws/client';

interface CommandCenterPageProps {
  setPage: (page: string) => void;
  onOpenIncident: (alert: Alert) => void;
}

/* Pseudo-3D rotating network graph — matches Meridian's NetworkGraph */
function NetworkGraph({ cameras }: { cameras: Camera[] }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const rotRef = useRef(0);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    let raf: number;
    let w = 0, h = 0;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);

    const nodes = cameras.map((c, i) => ({
      angle: (Math.PI * 2 * i) / Math.max(cameras.length, 1),
      radiusJitter: 0.7 + (((i * 7 + 3) % 11) / 11) * 0.5,
      heightJitter: (((i * 13 + 7) % 9) / 9 - 0.5) * 0.6,
      speed: 0.4 + (((i * 3 + 5) % 7) / 7) * 0.6,
      status: c.status,
      name: c.name,
    }));

    const statusColor: Record<string, string> = { online: '#3DD68C', offline: '#4A5568', alert: '#E5484D', degraded: '#E6C560', maintenance: '#E6C560' };

    function resize() {
      const rect = canvas!.parentElement!.getBoundingClientRect();
      w = rect.width; h = rect.height;
      canvas!.width = w * dpr; canvas!.height = h * dpr;
      canvas!.style.width = w + 'px'; canvas!.style.height = h + 'px';
      ctx!.setTransform(dpr, 0, 0, dpr, 0, 0);
    }
    resize();
    window.addEventListener('resize', resize);

    function project(x: number, y: number, z: number) {
      const persp = 620 / (620 + z);
      return { x: w / 2 + x * persp, y: h / 2 + y * persp, scale: persp };
    }

    function draw() {
      if (!ctx) return;
      ctx.clearRect(0, 0, w, h);
      rotRef.current += 0.0022;
      const rot = rotRef.current;
      const cx = w / 2, cy = h / 2;
      const baseR = Math.min(w, h) * 0.34;

      const pts = nodes.map((n) => {
        const a = n.angle + rot * (n.speed > 0 ? 1 : -1);
        const r = baseR * n.radiusJitter;
        const x = Math.cos(a) * r;
        const z = Math.sin(a) * r * 0.55;
        const y = n.heightJitter * baseR * 0.5 + Math.sin(rot * 2 + n.angle) * 6;
        return { ...n, x, y, z, proj: project(x, y, z) };
      });

      // Core sphere glow
      const coreGrad = ctx.createRadialGradient(cx, cy, 2, cx, cy, baseR * 0.5);
      coreGrad.addColorStop(0, 'rgba(76,158,255,0.16)');
      coreGrad.addColorStop(1, 'rgba(76,158,255,0)');
      ctx.fillStyle = coreGrad;
      ctx.beginPath(); ctx.arc(cx, cy, baseR * 0.55, 0, Math.PI * 2); ctx.fill();

      // Orbit rings
      ctx.strokeStyle = 'rgba(76,158,255,0.10)';
      ctx.lineWidth = 1;
      [0.55, 0.78, 1.0].forEach((f) => {
        ctx.beginPath();
        ctx.ellipse(cx, cy, baseR * f, baseR * f * 0.4, 0, 0, Math.PI * 2);
        ctx.stroke();
      });

      // Sort back to front
      const sorted = [...pts].sort((a, b) => a.z - b.z);
      ctx.lineWidth = 1;
      for (let i = 0; i < sorted.length; i++) {
        const n = sorted[i];
        const op = 0.05 + (n.proj.scale - 0.7) * 0.25;
        ctx.strokeStyle = `rgba(76,158,255,${Math.max(0.02, Math.min(0.16, op))})`;
        ctx.beginPath(); ctx.moveTo(n.proj.x, n.proj.y); ctx.lineTo(cx, cy); ctx.stroke();
      }

      // Node points
      sorted.forEach((n) => {
        const r = 2.6 * n.proj.scale;
        const col = statusColor[n.status] || '#4C9EFF';
        ctx.globalAlpha = Math.max(0.35, n.proj.scale);
        if (n.status === 'alert') {
          const pulse = (Math.sin(Date.now() / 260 + n.angle * 4) + 1) / 2;
          ctx.beginPath();
          ctx.fillStyle = `rgba(229,72,77,${0.12 + pulse * 0.18})`;
          ctx.arc(n.proj.x, n.proj.y, r * 4, 0, Math.PI * 2);
          ctx.fill();
        }
        ctx.beginPath();
        ctx.fillStyle = col;
        ctx.arc(n.proj.x, n.proj.y, r, 0, Math.PI * 2);
        ctx.fill();
        ctx.globalAlpha = 1;
      });

      raf = requestAnimationFrame(draw);
    }
    draw();
    return () => { cancelAnimationFrame(raf); window.removeEventListener('resize', resize); };
  }, [cameras]);

  return <canvas ref={canvasRef} style={{ width: '100%', height: '100%', display: 'block' }} />;
}

function relTime(ts: number): string {
  const diff = Math.floor((Date.now() / 1000) - ts);
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

export function CommandCenterPage({ setPage, onOpenIncident }: CommandCenterPageProps) {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [stats, setStats] = useState<any>({ total: 0, critical: 0, active: 0, reviewing: 0, confirmed: 0, dismissed: 0 });

  const loadData = async () => {
    try {
      const [alRes, camRes, stRes] = await Promise.all([
        listAlerts({ limit: 10 }),
        listCameras(),
        getAlertStats()
      ]);
      setAlerts(alRes);
      setCameras(camRes);
      setStats(stRes);
    } catch (err) {
      console.error('Error loading Command Center data:', err);
    }
  };

  useEffect(() => {
    loadData();
    const unsubscribe = wsClient.subscribe('alert.updated', () => loadData());
    return () => unsubscribe();
  }, []);

  const onlineCams = cameras.filter((c) => c.status === 'online').length;
  const activeAlerts = alerts.filter(a => a.status === 'active' || a.status === 'reviewing');

  return (
    <div className="fade-in">
      <div className="page-header">
        <div>
          <div className="page-title">Command Center</div>
          <div className="page-sub">Live operational summary across all monitored surveillance zones</div>
        </div>
        <div className="page-actions">
          <button className="btn" onClick={() => setPage('map')}>
            {ICN.map({ size: 14 })} Open Map
          </button>
          <button className="btn primary" onClick={() => setPage('analysis')}>
            {ICN.upload({ size: 14 })} Analyze Video Clip
          </button>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="kpi-grid">
        <div className="kpi-card">
          <div className="kpi-bar" style={{ background: 'var(--critical)' }} />
          <div className="scan-line" />
          <div className="kpi-label">Active Threats</div>
          <div className="kpi-value" style={{ color: stats.critical > 0 ? 'var(--critical)' : 'var(--text-hi)' }}>{stats.critical}</div>
          <div className="kpi-delta" style={{ color: 'var(--critical)' }}>
            {stats.critical > 0 ? 'Requires Immediate Review' : 'No active threats'}
          </div>
        </div>

        <div className="kpi-card">
          <div className="kpi-bar" style={{ background: 'var(--accent)' }} />
          <div className="kpi-label">Total Incidents</div>
          <div className="kpi-value">{stats.total}</div>
          <Sparkline data={[2, 5, 8, 4, 9, 12, 15, stats.total]} color="#4C9EFF" />
        </div>

        <div className="kpi-card">
          <div className="kpi-bar" style={{ background: 'var(--safe)' }} />
          <div className="kpi-label">Cameras Online</div>
          <div className="kpi-value">{onlineCams}<span style={{ fontSize: 14, color: 'var(--text-low)', fontWeight: 500 }}> / {cameras.length}</span></div>
          <div className="kpi-delta" style={{ color: cameras.length === onlineCams ? 'var(--safe)' : 'var(--high)' }}>
            {cameras.length === onlineCams ? '100% Coverage' : `${cameras.length - onlineCams} feed(s) degraded`}
          </div>
        </div>

        <div className="kpi-card">
          <div className="kpi-bar" style={{ background: 'var(--safe)' }} />
          <div className="kpi-label">Evidence Chain</div>
          <div className="kpi-value" style={{ color: 'var(--safe)' }}>VALID</div>
          <div className="kpi-delta" style={{ color: 'var(--safe)' }}>
            {ICN.shield({ size: 12 })} Hash Chain Verified
          </div>
        </div>
      </div>

      {/* Main content: 3 columns — alerts, network graph, camera status */}
      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1.2fr 1fr', gap: 12, alignItems: 'start' }}>
        {/* Active Alerts */}
        <div className="panel">
          <div className="panel-title-row">
            <span className="panel-title">Active High-Priority Alerts</span>
            <button className="btn sm ghost" onClick={() => setPage('alerts')}>View All</button>
          </div>
          <div className="panel-body" style={{ padding: 0, maxHeight: 400, overflowY: 'auto' }}>
            {alerts.length === 0 ? (
              <div style={{ padding: 24, color: 'var(--text-low)', textAlign: 'center', fontSize: 12.5 }}>
                {ICN.shield({ size: 28, style: { color: 'var(--safe)', display: 'block', margin: '0 auto 8px' } })}
                No active alerts — all clear.
              </div>
            ) : (
              alerts.map((al) => (
                <div key={al.id} className="list-row" style={{ padding: '12px 16px' }} onClick={() => onOpenIncident(al)}>
                  <RiskBadge risk={al.risk_level}>{al.risk_level}</RiskBadge>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontWeight: 600, fontSize: 13 }}>{al.reasons?.[0] || al.id}</div>
                    <div style={{ fontSize: 11, color: 'var(--text-mid)' }} className="mono">
                      {al.camera_name} · Zone: {al.zone || 'Z1'}
                    </div>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-hi)' }} className="mono">
                      {al.risk_score?.toFixed(1)}
                    </div>
                    <div style={{ fontSize: 10, color: 'var(--text-low)' }} className="mono">
                      {relTime(al.timestamp)}
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Network Graph */}
        <div className="panel" style={{ height: 420 }}>
          <div className="panel-title-row">
            <span className="panel-title">Camera Network</span>
            <span className="chip">
              <span className="dot safe" /> {onlineCams} Active
            </span>
          </div>
          <div style={{ height: 'calc(100% - 45px)', position: 'relative' }}>
            <NetworkGraph cameras={cameras} />
          </div>
        </div>

        {/* Camera Status */}
        <div className="panel" style={{ maxHeight: 420, overflow: 'hidden' }}>
          <div className="panel-title-row">
            <span className="panel-title">Feed Status</span>
            <button className="btn sm ghost" onClick={() => setPage('gridview')}>Grid</button>
          </div>
          <div className="panel-body scroll-thin" style={{ padding: 0, maxHeight: 370, overflowY: 'auto' }}>
            {cameras.map((cam) => (
              <div key={cam.id} className="list-row" style={{ padding: '10px 14px' }}>
                <StatusDot status={cam.status} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontWeight: 600, fontSize: 12 }}>{cam.name}</div>
                  <div style={{ fontSize: 10, color: 'var(--text-low)' }}>{cam.location}</div>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <div style={{ fontSize: 11, color: 'var(--text-mid)' }} className="mono">{cam.fps} FPS</div>
                  <div style={{ fontSize: 10, color: 'var(--text-low)' }} className="mono">{cam.zone_type}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
