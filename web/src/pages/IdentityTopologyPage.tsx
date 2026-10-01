import React, { useState, useEffect } from 'react';
import { getTopology, getIdentityGhosts } from '../api/client';
import { ICN } from '../components/Icon';

export function IdentityTopologyPage() {
  const [topology, setTopology] = useState<any>({ nodes: [], edges: [] });
  const [ghosts, setGhosts] = useState<any[]>([]);
  const [handoffs, setHandoffs] = useState<any[]>([]);
  const [lastRefreshed, setLastRefreshed] = useState<string>('');

  const fetchIdentityData = () => {
    Promise.all([getTopology(), getIdentityGhosts()])
      .then(([topRes, ghostRes]) => {
        setTopology(topRes || { nodes: [], edges: [] });
        setGhosts(ghostRes?.ghosts || []);
        setHandoffs(ghostRes?.recent_handoffs || []);
        setLastRefreshed(new Date().toLocaleTimeString());
      })
      .catch(console.error);
  };

  useEffect(() => {
    fetchIdentityData();
    const interval = setInterval(fetchIdentityData, 2000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="fade-in">
      <div className="page-header">
        <div>
          <div className="page-title">Identity & Cross-Camera Topology</div>
          <div className="page-sub">
            Real-time blind spot re-identification & risk continuation across camera network
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ fontSize: 11.5, color: 'var(--text-low)' }}>
            Auto-refresh: 2s · Last updated: {lastRefreshed || 'Just now'}
          </span>
          <button className="btn btn-secondary btn-sm" onClick={fetchIdentityData}>
            {ICN.refresh({ size: 13 })} Refresh
          </button>
        </div>
      </div>

      {/* Info Banner */}
      <div style={{
        background: 'rgba(56, 189, 248, 0.08)',
        border: '1px solid rgba(56, 189, 248, 0.25)',
        borderRadius: 8,
        padding: '12px 16px',
        marginBottom: 20,
        display: 'flex',
        alignItems: 'center',
        gap: 12
      }}>
        {ICN.link({ size: 20, style: { color: 'var(--accent)', flexShrink: 0 } })}
        <div style={{ fontSize: 12.5, lineHeight: 1.5, color: 'var(--text-high)' }}>
          <strong>Cross-Camera Risk Continuity Active:</strong> When a tracked person exits one camera (e.g. Phone Cam 1) and enters another camera within 30 seconds, their visual appearance embedding is matched across the blind spot. Their accumulated threat risk score, running sprint signals, and alert history are seamlessly inherited by the new camera.
        </div>
      </div>

      <div className="grid-2col" style={{ gap: 20 }}>
        {/* Active In-Transit Ghosts (Blind Spots) */}
        <div className="panel">
          <div className="panel-title-row">
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              {ICN.ghost({ size: 16, style: { color: '#f59e0b' } })}
              <span className="panel-title">Active In-Transit Subjects ({ghosts.length})</span>
            </div>
            <span className="badge high" style={{ fontSize: 10.5 }}>Blind Spot Tracking</span>
          </div>
          <div className="panel-body" style={{ minHeight: 220 }}>
            {ghosts.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '36px 16px', color: 'var(--text-low)' }}>
                <div style={{ marginBottom: 8 }}>{ICN.eye({ size: 28, style: { opacity: 0.4 } })}</div>
                <div style={{ fontWeight: 600, fontSize: 13, color: 'var(--text-mid)' }}>No Subjects in Blind Spots</div>
                <div style={{ fontSize: 11.5, marginTop: 4 }}>
                  When a person walks out of camera view, their risk profile is registered here for up to 30s awaiting re-entry into the next camera.
                </div>
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                {ghosts.map((g, i) => (
                  <div
                    key={i}
                    style={{
                      background: 'var(--panel)',
                      padding: '12px 14px',
                      borderRadius: 8,
                      border: '1px solid rgba(245, 158, 11, 0.3)',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: 8
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <span className="mono" style={{ fontWeight: 700, fontSize: 13.5, color: '#f59e0b' }}>
                          [{g.ghost_id}]
                        </span>
                        <span style={{ fontSize: 12, color: 'var(--text-mid)' }}>
                          Exited: <strong>{g.last_seen_camera}</strong>
                        </span>
                      </div>
                      <span className={`badge ${g.risk_score >= 60 ? 'critical' : g.risk_score >= 30 ? 'high' : 'safe'}`}>
                        Risk: {Math.round(g.risk_score)}
                      </span>
                    </div>

                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: 11.5 }}>
                      <span style={{ color: 'var(--text-low)' }}>
                        Transit Time: <strong style={{ color: 'var(--text-high)' }}>{g.time_in_transit_s}s</strong>
                      </span>
                      <span style={{ color: 'var(--text-low)' }}>
                        Confidence: <strong style={{ color: 'var(--text-high)' }}>{Math.round(g.confidence * 100)}%</strong>
                      </span>
                    </div>

                    {g.signals && g.signals.length > 0 && (
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 2 }}>
                        {g.signals.map((sig: string, si: number) => (
                          <span key={si} className="badge high" style={{ fontSize: 10, padding: '1px 6px' }}>
                            {sig}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Verified Cross-Camera Handoffs History */}
        <div className="panel">
          <div className="panel-title-row">
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              {ICN.link({ size: 16, style: { color: 'var(--accent)' } })}
              <span className="panel-title">Completed Handoffs ({handoffs.length})</span>
            </div>
            <span className="badge safe" style={{ fontSize: 10.5 }}>Risk Preserved</span>
          </div>
          <div className="panel-body" style={{ minHeight: 220 }}>
            {handoffs.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '36px 16px', color: 'var(--text-low)' }}>
                <div style={{ marginBottom: 8 }}>{ICN.link({ size: 28, style: { opacity: 0.4 } })}</div>
                <div style={{ fontWeight: 600, fontSize: 13, color: 'var(--text-mid)' }}>No Handoffs Recorded Yet</div>
                <div style={{ fontSize: 11.5, marginTop: 4 }}>
                  Exit from one camera (e.g. Phone 1) and step into Phone 2 view to trigger seamless appearance Re-ID and risk handover.
                </div>
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                {handoffs.map((h, i) => (
                  <div
                    key={h.id || i}
                    style={{
                      background: 'var(--panel)',
                      padding: '12px 14px',
                      borderRadius: 8,
                      border: '1px solid rgba(46, 204, 113, 0.3)',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: 6
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                      <span className="mono" style={{ fontWeight: 700, fontSize: 13, color: 'var(--accent)' }}>
                        [{h.global_id}] HANDOFF SUCCESS
                      </span>
                      <span className={`badge ${h.transferred_risk >= 60 ? 'critical' : h.transferred_risk >= 30 ? 'high' : 'safe'}`}>
                        Risk: {Math.round(h.transferred_risk)} Inherited
                      </span>
                    </div>

                    <div style={{ fontSize: 12, color: 'var(--text-mid)', display: 'flex', alignItems: 'center', gap: 6 }}>
                      <span className="mono" style={{ color: 'var(--text-high)' }}>{h.from_camera}</span>
                      <span style={{ color: 'var(--accent)' }}>➔</span>
                      <span className="mono" style={{ color: 'var(--text-high)' }}>{h.to_camera}</span>
                    </div>

                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: 11, color: 'var(--text-low)' }}>
                      <span>Transit Duration: <strong style={{ color: 'var(--text-high)' }}>{h.transit_duration_s}s</strong></span>
                      <span>Re-ID Match: <strong style={{ color: 'var(--text-high)' }}>{Math.round(h.similarity * 100)}%</strong></span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Edge & Network Topology */}
      <div className="panel" style={{ marginTop: 20 }}>
        <div className="panel-title-row">
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            {ICN.cpu({ size: 16, style: { color: 'var(--accent)' } })}
            <span className="panel-title">Active Surveillance Nodes & Cameras</span>
          </div>
        </div>
        <div className="panel-body" style={{ padding: 0 }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 1, background: 'var(--border-soft)' }}>
            {topology.nodes?.map((n: any) => (
              <div key={n.id} style={{ background: 'var(--panel)', padding: '12px 16px', display: 'flex', alignItems: 'center', gap: 12 }}>
                {n.type === 'camera' ? ICN.camera({ size: 18, style: { color: 'var(--accent)' } }) : ICN.cpu({ size: 18, style: { color: '#818cf8' } })}
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontWeight: 600, fontSize: 13, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {n.label}
                  </div>
                  <div style={{ fontSize: 11, color: 'var(--text-low)' }} className="mono">
                    {n.id} · {n.type}
                  </div>
                </div>
                <span className={`badge ${n.status === 'online' ? 'safe' : 'high'}`} style={{ fontSize: 10.5 }}>
                  {n.status}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
