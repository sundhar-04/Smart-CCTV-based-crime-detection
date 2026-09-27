import React from 'react';

export function StatusDot({ status }: { status: string }) {
  const map: Record<string, string> = {
    online: 'safe',
    offline: 'offline',
    alert: 'critical',
    maintenance: 'medium',
    recording: 'info',
    degraded: 'high'
  };
  const dotClass = map[status] || 'safe';
  return <span className={`dot ${dotClass}`} />;
}
