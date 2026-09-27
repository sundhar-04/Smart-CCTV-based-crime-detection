import React from 'react';

export function ConfidenceBar({ value, colorVar }: { value: number; colorVar?: string }) {
  const color = colorVar || 'var(--accent)';
  return (
    <div className="conf-bar-track">
      <div className="conf-bar-fill" style={{ width: `${Math.min(100, Math.max(0, value))}%`, background: color }} />
    </div>
  );
}
