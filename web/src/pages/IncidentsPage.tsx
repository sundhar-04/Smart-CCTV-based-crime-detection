import React, { useState, useEffect } from 'react';
import { listAlerts, Alert } from '../api/client';
import { RiskBadge } from '../components/RiskBadge';
import { ICN, TypeIcon } from '../components/Icon';
import { ConfidenceBar } from '../components/ConfidenceBar';

function relTime(ts: number): string {
  const diff = Math.floor((Date.now() / 1000) - ts);
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

type RiskLevel = 'CRITICAL' | 'HIGH' | 'ELEVATED' | 'LOW';
const RISK_ORDER: RiskLevel[] = ['CRITICAL', 'HIGH', 'ELEVATED', 'LOW'];
const RISK_COLOR: Record<string, string> = { CRITICAL: 'var(--critical)', HIGH: 'var(--high)', ELEVATED: 'var(--medium)', LOW: 'var(--safe)' };
const RISK_DOT_CLASS: Record<string, string> = { CRITICAL: 'critical', HIGH: 'high', ELEVATED: 'medium', LOW: 'safe' };

export function IncidentsPage({ onOpenIncident }: { onOpenIncident: (alert: Alert) => void }) {
  const [incidents, setIncidents] = useState<Alert[]>([]);
  const [expandedGroups, setExpandedGroups] = useState<Record<string, boolean>>({ CRITICAL: true, HIGH: true, ELEVATED: true, LOW: false });
  const [filter, setFilter] = useState('all');

  useEffect(() => {
    listAlerts({ limit: 100 }).then(setIncidents).catch(console.error);
  }, []);

  const filtered = incidents.filter(inc => {
    if (filter === 'all') return true;
    if (filter === 'active') return inc.status === 'active' || inc.status === 'reviewing';
    if (filter === 'confirmed') return inc.status === 'confirmed';
    if (filter === 'dismissed') return inc.status === 'dismissed';
    return true;
  });

  const grouped = RISK_ORDER.reduce((acc, level) => {
    acc[level] = filtered.filter(inc => inc.risk_level === level);
    return acc;
  }, {} as Record<string, Alert[]>);

  const toggleGroup = (level: string) => {
    setExpandedGroups(prev => ({ ...prev, [level]: !prev[level] }));
  };

  return (
    <div className="fade-in">
      <div className="page-header">
        <div>
          <div className="page-title">Incidents Management</div>
          <div className="page-sub">
            Risk-grouped threat incidents — {filtered.length} total across {incidents.length} tracked events
          </div>
        </div>
        <div className="page-actions">
          <select className="role-select" value={filter} onChange={e => setFilter(e.target.value)}>
            <option value="all">All Statuses</option>
            <option value="active">Active / Reviewing</option>
            <option value="confirmed">Confirmed</option>
            <option value="dismissed">Dismissed</option>
          </select>
        </div>
      </div>

      {RISK_ORDER.map(level => {
        const items = grouped[level];
        if (!items || items.length === 0) return null;
        const isOpen = expandedGroups[level];
        return (
          <div key={level} style={{ marginBottom: 16 }}>
            {/* Risk Section Header */}
            <div className="risk-section-head" onClick={() => toggleGroup(level)} style={{ cursor: 'pointer' }}>
              <span className={`dot ${RISK_DOT_CLASS[level]}`} />
              <span style={{ fontWeight: 700, fontSize: 12, letterSpacing: '0.04em', textTransform: 'uppercase' as const, color: RISK_COLOR[level] }}>
                {level}
              </span>
              <span className="badge neutral" style={{ fontSize: 10 }}>{items.length}</span>
              <div className="risk-line" />
              <span className={`expand-caret ${isOpen ? 'open' : ''}`}>
                {ICN.chevronRight({ size: 14, style: { color: 'var(--text-low)' } })}
              </span>
            </div>

            {/* Incident Cards Grid */}
            {isOpen && (
              <div className="grid-3col" style={{ marginTop: 8 }}>
                {items.map((inc) => (
                  <div key={inc.id} className="panel" style={{ cursor: 'pointer', transition: 'border-color .15s' }} onClick={() => onOpenIncident(inc)}>
                    <div className="panel-title-row" style={{ padding: '10px 14px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <TypeIcon type={inc.types?.[0] || 'restricted'} size={15} />
                        <span style={{ fontWeight: 700, fontSize: 12.5 }}>{inc.reasons?.[0] || inc.id}</span>
                      </div>
                      <RiskBadge risk={inc.risk_level}>{inc.risk_level}</RiskBadge>
                    </div>
                    <div className="panel-body" style={{ padding: '12px 14px' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                        <div>
                          <div style={{ fontWeight: 600, fontSize: 12.5 }}>{inc.camera_name}</div>
                          <div style={{ fontSize: 10.5, color: 'var(--text-low)', marginTop: 2 }}>{inc.location}</div>
                        </div>
                        <div style={{ textAlign: 'right' }}>
                          <div className="mono" style={{ fontSize: 18, fontWeight: 700 }}>
                            {inc.risk_score?.toFixed(1)}
                          </div>
                          <div className="mono" style={{ fontSize: 10, color: 'var(--text-low)' }}>
                            {relTime(inc.timestamp)}
                          </div>
                        </div>
                      </div>

                      <ConfidenceBar value={inc.risk_score || 50} colorVar={RISK_COLOR[inc.risk_level] || 'var(--accent)'} />

                      <div style={{ display: 'flex', flexWrap: 'wrap' as const, gap: 4, marginTop: 10 }}>
                        {inc.types?.map((t, idx) => (
                          <span key={idx} className="chip">{t}</span>
                        ))}
                      </div>

                      <div style={{ marginTop: 12, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <span className={`badge ${inc.status === 'confirmed' ? 'safe' : inc.status === 'dismissed' ? 'neutral' : 'info'}`} style={{ fontSize: 9.5 }}>
                          {inc.status}
                        </span>
                        <button className="btn sm primary" onClick={(e) => { e.stopPropagation(); onOpenIncident(inc); }}>
                          {ICN.eye({ size: 12 })} Investigate
                        </button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
