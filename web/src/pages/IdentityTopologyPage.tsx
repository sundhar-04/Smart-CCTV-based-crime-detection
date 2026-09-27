import React, { useState, useEffect } from 'react';
import { getTopology, getIdentityGhosts } from '../api/client';
import { ICN } from '../components/Icon';

export function IdentityTopologyPage() {
  const [topology, setTopology] = useState<any>({ nodes: [], edges: [] });
  const [ghosts, setGhosts] = useState<any[]>([]);

  useEffect(() => {
    Promise.all([getTopology(), getIdentityGhosts()])
      .then(([topRes, ghostRes]) => {
        setTopology(topRes);
        setGhosts(ghostRes.ghosts || []);
      })
      .catch(console.error);
  }, []);

  return (
    <div className="fade-in">
      <div className="page-header">
        <div>
          <div className="page-title">Identity & Camera Topology</div>
          <div className="page-sub">Re-identification tracking across camera blind-spots and edge network topology</div>
        </div>
      </div>

      <div className="grid-2col">
        {/* Nodes list */}
        <div className="panel">
          <div className="panel-title-row">
            <span className="panel-title">Topology Edge & Inference Nodes</span>
          </div>
          <div className="panel-body" style={{ padding: 0 }}>
            {topology.nodes?.map((n: any) => (
              <div key={n.id} className="list-row" style={{ padding: '10px 16px' }}>
                {ICN.cpu({ size: 16, style: { color: 'var(--accent)' } })}
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontWeight: 600, fontSize: 13 }}>{n.label}</div>
                  <div style={{ fontSize: 11, color: 'var(--text-low)' }} className="mono">{n.id} · Type: {n.type}</div>
                </div>
                <span className="badge safe">{n.status}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Live Identity Ghosts */}
        <div className="panel">
          <div className="panel-title-row">
            <span className="panel-title">In-Transit Re-ID Trackers</span>
          </div>
          <div className="panel-body">
            {ghosts.map((g: any, i: number) => (
              <div key={i} style={{ background: 'var(--panel)', padding: 12, borderRadius: 6, border: '1px solid var(--border-soft)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  {ICN.ghost({ size: 16, style: { color: 'var(--high)' } })}
                  <span style={{ fontWeight: 700, fontSize: 13 }} className="mono">{g.ghost_id}</span>
                  <span className="badge high" style={{ marginLeft: 'auto' }}>{(g.confidence * 100).toFixed(0)}% Confidence</span>
                </div>
                <div style={{ fontSize: 11.5, color: 'var(--text-mid)', marginTop: 8 }}>
                  Last Seen: <b>{g.last_seen_camera}</b> → Predicted Next: <b>{g.predicted_camera}</b>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
