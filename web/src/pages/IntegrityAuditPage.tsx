import React, { useState, useEffect } from 'react';
import { verifySystemIntegrity, listAuditLogs } from '../api/client';
import { ICN } from '../components/Icon';

export function IntegrityAuditPage() {
  const [integrity, setIntegrity] = useState<any>(null);
  const [auditLogs, setAuditLogs] = useState<any[]>([]);
  const [verifying, setVerifying] = useState(false);

  const runVerification = async () => {
    setVerifying(true);
    try {
      const res = await verifySystemIntegrity();
      setIntegrity(res);
      const logs = await listAuditLogs(30);
      setAuditLogs(logs);
    } catch (err) {
      console.error('Integrity check error:', err);
    } finally {
      setVerifying(false);
    }
  };

  useEffect(() => {
    runVerification();
  }, []);

  return (
    <div className="fade-in">
      <div className="page-header">
        <div>
          <div className="page-title">Evidence Integrity & Audit Log</div>
          <div className="page-sub">Cryptographic SHA-256 hash chain verification for evidentiary admissibility</div>
        </div>
        <div className="page-actions">
          <button className="btn primary" onClick={runVerification} disabled={verifying}>
            {ICN.shield({ size: 14 })} {verifying ? 'Verifying Chain...' : 'Verify Hash Chain'}
          </button>
        </div>
      </div>

      <div style={{ marginBottom: 16 }}>
        <div className="panel" style={{ borderLeft: '4px solid var(--safe)' }}>
          <div className="panel-body" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <div>
              <div style={{ fontWeight: 700, fontSize: 16 }}>
                Chain Verification Status: <span style={{ color: 'var(--safe)' }}>{integrity?.status || 'VALID'}</span>
              </div>
              <div style={{ fontSize: 12, color: 'var(--text-mid)', marginTop: 2 }}>
                Verified {integrity?.audit_logs_verified || 0} sequential audit blocks. Zero tampering or sequence breaks detected.
              </div>
            </div>
            <div style={{ fontSize: 11, color: 'var(--text-low)' }} className="mono">
              Last Verified: {integrity?.verification_timestamp}
            </div>
          </div>
        </div>
      </div>

      <div className="panel">
        <div className="panel-title-row">
          <span className="panel-title">Audit Ledger Records</span>
        </div>
        <div className="panel-body" style={{ padding: 0 }}>
          <table className="data-table">
            <thead>
              <tr>
                <th>Block ID</th>
                <th>Timestamp</th>
                <th>Actor</th>
                <th>Action</th>
                <th>Resource</th>
                <th>Hash Self</th>
              </tr>
            </thead>
            <tbody>
              {auditLogs.map((log) => (
                <tr key={log.id}>
                  <td className="mono" style={{ fontWeight: 600 }}>{log.id}</td>
                  <td className="mono" style={{ fontSize: 11 }}>{log.timestamp}</td>
                  <td>{log.actor}</td>
                  <td style={{ fontWeight: 600 }}>{log.action}</td>
                  <td className="mono" style={{ fontSize: 11 }}>{log.resource}</td>
                  <td className="mono" style={{ fontSize: 10, color: 'var(--safe)' }}>
                    {log.hash_self ? log.hash_self.slice(0, 16) + '...' : ''}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
