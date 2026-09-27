import React from 'react';
import { ICN } from './Icon';

interface NotificationDrawerProps {
  onClose: () => void;
  notifications: any[];
}

export function NotificationDrawer({ onClose, notifications }: NotificationDrawerProps) {
  return (
    <div className="drawer-backdrop" onClick={onClose}>
      <div className="drawer" onClick={(e) => e.stopPropagation()}>
        <div style={{ display: 'flex', alignItems: 'center', padding: '14px 16px', borderBottom: '1px solid var(--border-soft)' }}>
          <div style={{ fontWeight: 700, fontSize: 14 }}>Notifications</div>
          <button className="icon-btn" style={{ marginLeft: 'auto' }} onClick={onClose}>
            {ICN.x({ size: 15 })}
          </button>
        </div>
        <div style={{ flex: 1, overflowY: 'auto', padding: '8px 10px' }}>
          {notifications.map((n, idx) => (
            <div key={n.id || idx} style={{ display: 'flex', gap: 10, padding: '11px 8px', borderBottom: '1px solid var(--border-soft)' }}>
              <div style={{ marginTop: 2 }}>
                {n.kind === 'camera'
                  ? ICN.wifiOff({ size: 15, style: { color: 'var(--text-mid)' } })
                  : n.kind === 'system'
                  ? ICN.settings({ size: 15, style: { color: 'var(--info)' } })
                  : n.kind === 'complete'
                  ? ICN.check({ size: 15, style: { color: 'var(--safe)' } })
                  : ICN.alert({ size: 15, style: { color: 'var(--critical)' } })}
              </div>
              <div style={{ minWidth: 0, flex: 1 }}>
                <div style={{ fontSize: 12.5, fontWeight: 500 }}>{n.title}</div>
                <div style={{ fontSize: 11.5, color: 'var(--text-mid)', marginTop: 2 }}>{n.sub}</div>
                <div style={{ fontSize: 10.5, color: 'var(--text-low)', marginTop: 3 }} className="mono">
                  {n.timestamp ? new Date(n.timestamp).toLocaleTimeString() : 'Just now'}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
