import React, { useState, useEffect } from 'react';
import { listAlerts, Alert } from '../api/client';
import { RiskBadge } from '../components/RiskBadge';
import { ICN } from '../components/Icon';

export function HistoryPage({ onOpenIncident }: { onOpenIncident: (alert: Alert) => void }) {
  const [history, setHistory] = useState<Alert[]>([]);
  const [search, setSearch] = useState('');
  const [riskFilter, setRiskFilter] = useState('');

  useEffect(() => {
    listAlerts({ limit: 100 }).then(setHistory).catch(console.error);
  }, []);

  const filtered = history.filter(al => {
    const matchSearch = !search ||
      al.id.toLowerCase().includes(search.toLowerCase()) ||
      al.camera_name.toLowerCase().includes(search.toLowerCase()) ||
      (al.location || '').toLowerCase().includes(search.toLowerCase());
    const matchRisk = !riskFilter || al.risk_level === riskFilter;
    return matchSearch && matchRisk;
  });

  const stats = {
    total: history.length,
    confirmed: history.filter(a => a.status === 'confirmed').length,
    dismissed: history.filter(a => a.status === 'dismissed').length,
    active: history.filter(a => a.status === 'active' || a.status === 'reviewing').length,
  };

  return (
    <div className="fade-in">
      <div className="page-header">
        <div>
          <div className="page-title">Incident History & Audit Log</div>
          <div className="page-sub">Historical record of all surveillance incidents — {filtered.length} records</div>
        </div>
        <div className="page-actions">
          <div className="kpi-card" style={{ padding: '6px 12px', display: 'flex', gap: 16 }}>
            <div style={{ textAlign: 'center' }}>
              <div className="mono" style={{ fontSize: 16, fontWeight: 700 }}>{stats.total}</div>
              <div className="kpi-label">Total</div>
            </div>
            <div style={{ textAlign: 'center' }}>
              <div className="mono" style={{ fontSize: 16, fontWeight: 700, color: 'var(--safe)' }}>{stats.confirmed}</div>
              <div className="kpi-label">Confirmed</div>
            </div>
            <div style={{ textAlign: 'center' }}>
              <div className="mono" style={{ fontSize: 16, fontWeight: 700, color: 'var(--text-low)' }}>{stats.dismissed}</div>
              <div className="kpi-label">Dismissed</div>
            </div>
            <div style={{ textAlign: 'center' }}>
              <div className="mono" style={{ fontSize: 16, fontWeight: 700, color: 'var(--critical)' }}>{stats.active}</div>
              <div className="kpi-label">Active</div>
            </div>
          </div>
        </div>
      </div>

      {/* Filters */}
      <div style={{ display: 'flex', gap: 10, marginBottom: 14 }}>
        <div style={{ flex: 1, maxWidth: 360 }}>
          <input
            className="field"
            style={{ width: '100%' }}
            placeholder="Search by ID, camera, or location..."
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
        </div>
        <select className="role-select" value={riskFilter} onChange={e => setRiskFilter(e.target.value)}>
          <option value="">All Risk Levels</option>
          <option value="CRITICAL">Critical</option>
          <option value="HIGH">High</option>
          <option value="ELEVATED">Elevated</option>
          <option value="LOW">Low</option>
        </select>
      </div>

      <div className="panel">
        <div className="panel-body" style={{ padding: 0 }}>
          <table className="data-table">
            <thead>
              <tr>
                <th></th>
                <th>Incident ID</th>
                <th>Timestamp</th>
                <th>Camera / Location</th>
                <th>Risk</th>
                <th>Score</th>
                <th>Status</th>
                <th>Decided By</th>
                <th>Chain Link</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 ? (
                <tr>
                  <td colSpan={10} style={{ textAlign: 'center', padding: 30, color: 'var(--text-low)' }}>
                    No records match your search criteria.
                  </td>
                </tr>
              ) : (
                filtered.map((al) => (
                  <tr key={al.id} onClick={() => onOpenIncident(al)}>
                    <td>
                      <span className={`dot ${al.risk_level === 'CRITICAL' ? 'critical' : al.risk_level === 'HIGH' ? 'high' : al.risk_level === 'ELEVATED' ? 'medium' : 'safe'}`} />
                    </td>
                    <td className="mono" style={{ fontWeight: 600, fontSize: 11.5 }}>{al.id}</td>
                    <td className="mono" style={{ fontSize: 11 }}>
                      {new Date(al.timestamp * 1000).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                    </td>
                    <td>
                      <div style={{ fontWeight: 600, fontSize: 12 }}>{al.camera_name}</div>
                      <div style={{ fontSize: 10.5, color: 'var(--text-low)' }}>{al.location}</div>
                    </td>
                    <td><RiskBadge risk={al.risk_level}>{al.risk_level}</RiskBadge></td>
                    <td className="mono" style={{ fontWeight: 700, fontSize: 13 }}>{al.risk_score?.toFixed(1)}</td>
                    <td>
                      <span className={`badge ${al.status === 'confirmed' ? 'safe' : al.status === 'dismissed' ? 'neutral' : al.status === 'reviewing' ? 'info' : 'critical'}`}>
                        {al.status}
                      </span>
                    </td>
                    <td style={{ fontSize: 12, color: 'var(--text-mid)' }}>{al.decided_by || 'system'}</td>
                    <td className="mono" style={{ fontSize: 10, color: al.hash_prev ? 'var(--safe)' : 'var(--text-low)' }}>
                      {al.hash_prev ? al.hash_prev.slice(0, 12) + '…' : 'GENESIS'}
                    </td>
                    <td>
                      <button className="btn sm ghost" onClick={(e) => { e.stopPropagation(); onOpenIncident(al); }}>
                        {ICN.eye({ size: 12 })}
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
