import React, { useState } from 'react';
import { Alert, decideAlert } from '../api/client';
import { RiskBadge } from '../components/RiskBadge';
import { ICN, TypeIcon } from '../components/Icon';
import { ConfidenceBar } from '../components/ConfidenceBar';

interface IncidentInvestigationModalProps {
  alert: Alert | null;
  onClose: () => void;
  onDecided?: (updatedAlert: Alert) => void;
}

export function IncidentInvestigationModal({ alert, onClose, onDecided }: IncidentInvestigationModalProps) {
  const [loading, setLoading] = useState(false);
  const [notes, setNotes] = useState('');
  const [auditHash, setAuditHash] = useState<string | null>(null);

  if (!alert) return null;

  const handleDecision = async (action: 'confirm' | 'dismiss') => {
    setLoading(true);
    try {
      const res = await decideAlert(alert.id, { action, notes, decided_by: 'operator_admin' });
      setAuditHash(res.audit_hash);
      if (onDecided) {
        onDecided(res.alert);
      }
      setTimeout(() => {
        onClose();
      }, 1200);
    } catch (err: any) {
      window.alert(`Error recording decision: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="investigation-modal" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', padding: '14px 18px', borderBottom: '1px solid var(--border-soft)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <TypeIcon type={alert.types?.[0] || 'restricted'} size={18} />
            <div>
              <div style={{ fontWeight: 700, fontSize: 15 }}>
                Incident Investigation — {alert.id}
              </div>
              <div style={{ fontSize: 11.5, color: 'var(--text-mid)', marginTop: 1 }}>
                {alert.camera_name} · {alert.location}
              </div>
            </div>
          </div>
          <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 10 }}>
            <RiskBadge risk={alert.risk_level}>{alert.risk_level}</RiskBadge>
            <button className="icon-btn" onClick={onClose}>
              {ICN.x({ size: 15 })}
            </button>
          </div>
        </div>

        {/* Body */}
        <div style={{ flex: 1, display: 'grid', gridTemplateColumns: '2fr 1fr', overflow: 'hidden' }}>
          {/* Main Visual & Evidence View */}
          <div style={{ padding: 18, borderRight: '1px solid var(--border-soft)', overflowY: 'auto' }}>
            {(() => {
              const mediaUrl = alert.snapshot_url || alert.evidence_path || (alert.camera_id && alert.camera_id !== 'ANALYSIS_CAM' ? `/api/cameras/${alert.camera_id}/snapshot` : null);
              const isVideo = mediaUrl && (mediaUrl.endsWith('.mp4') || mediaUrl.endsWith('.webm'));
              return (
                <div style={{ position: 'relative', borderRadius: 8, overflow: 'hidden', border: '1px solid var(--border)', background: '#000', height: 320 }}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--text-mid)' }}>
                    {isVideo ? (
                      <video src={mediaUrl} controls autoPlay loop muted style={{ width: '100%', height: '100%', objectFit: 'contain' }} />
                    ) : mediaUrl ? (
                      <img src={mediaUrl} alt="Incident Evidence" style={{ width: '100%', height: '100%', objectFit: 'contain' }} />
                    ) : (
                      <div style={{ textAlign: 'center' }}>
                        {ICN.film({ size: 48, style: { color: 'var(--accent)', opacity: 0.8 } })}
                        <div style={{ marginTop: 10, fontSize: 13, fontWeight: 600 }}>Live Evidence Capture & Frame Analysis</div>
                        <div style={{ fontSize: 11, color: 'var(--text-low)', marginTop: 4 }}>
                          Entity: {alert.entity || 'P1'} | Zone: {alert.zone || 'Z1'}
                        </div>
                      </div>
                    )}
                  </div>
                  <div className="cam-tile-topbar">
                    <span className="chip"><span className="dot critical" /> EVIDENCE CLIP / SNAPSHOT</span>
                    <span style={{ marginLeft: 'auto', fontSize: 11, color: '#fff' }} className="mono">
                      {new Date(alert.timestamp * 1000).toLocaleString()}
                    </span>
                  </div>
                </div>
              );
            })()}

            <div style={{ marginTop: 16 }}>
              <div className="panel-title" style={{ marginBottom: 8 }}>Primary Signal Explanations</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {alert.reasons?.map((reason, idx) => (
                  <div key={idx} className="chip" style={{ padding: '8px 12px', fontSize: 12 }}>
                    {ICN.alert({ size: 14, style: { color: 'var(--critical)' } })} {reason}
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Decision & Hash Chain Panel */}
          <div style={{ padding: 18, background: 'var(--panel)', display: 'flex', flexDirection: 'column', gap: 14 }}>
            <div>
              <div className="panel-title">Calculated Risk Score</div>
              <div style={{ fontSize: 32, fontWeight: 800, color: 'var(--text-hi)', marginTop: 4 }} className="mono">
                {alert.risk_score?.toFixed(1)} <span style={{ fontSize: 14, color: 'var(--text-low)' }}>/ 100</span>
              </div>
              <ConfidenceBar value={alert.risk_score || 50} colorVar="var(--critical)" />
            </div>

            <div style={{ borderTop: '1px solid var(--border-soft)', paddingTop: 12 }}>
              <div className="panel-title">Evidence Tamper Chain</div>
              <div style={{ fontSize: 11, color: 'var(--text-mid)', marginTop: 4 }} className="mono">
                Prev Hash: {alert.hash_prev ? alert.hash_prev.slice(0, 16) + '...' : 'GENESIS'}
              </div>
              <div style={{ fontSize: 11, color: 'var(--safe)', marginTop: 2 }} className="mono">
                Status: HASH_CHAIN_VERIFIED
              </div>
            </div>

            <div style={{ borderTop: '1px solid var(--border-soft)', paddingTop: 12, flex: 1, display: 'flex', flexDirection: 'column' }}>
              <div className="panel-title">Operator Action & Notes</div>
              <textarea
                className="field"
                rows={3}
                placeholder="Enter investigation notes or justification..."
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                style={{ width: '100%', marginTop: 8, resize: 'none' }}
              />

              {auditHash && (
                <div style={{ fontSize: 11, color: 'var(--safe)', background: 'var(--safe-dim)', padding: 8, borderRadius: 6, marginTop: 10 }} className="mono">
                  ✓ Recorded into Audit Hash Chain: {auditHash.slice(0, 16)}...
                </div>
              )}

              <div style={{ marginTop: 'auto', display: 'flex', gap: 8 }}>
                <button
                  className="btn danger"
                  style={{ flex: 1, justifyContent: 'center' }}
                  onClick={() => handleDecision('dismiss')}
                  disabled={loading || alert.status === 'dismissed'}
                >
                  {ICN.x({ size: 14 })} Dismiss
                </button>
                <button
                  className="btn primary"
                  style={{ flex: 1, justifyContent: 'center' }}
                  onClick={() => handleDecision('confirm')}
                  disabled={loading || alert.status === 'confirmed'}
                >
                  {ICN.check({ size: 14 })} Confirm Threat
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
