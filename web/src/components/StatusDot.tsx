import React from 'react';

export function StatusDot({ status }: { status: string }) {
  const s = (status || '').toLowerCase();
  const map: Record<string, string> = {
    connected: 'safe',
    online: 'safe',
    connecting: 'medium',
    disconnected: 'offline',
    offline: 'offline',
    error: 'critical',
    alert: 'critical',
    maintenance: 'medium',
    recording: 'info',
    degraded: 'high'
  };
  const dotClass = map[s] || 'offline';
  return <span className={`dot ${dotClass}`} />;
}
