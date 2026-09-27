import React from 'react';

export function RiskBadge({ risk, children }: { risk: string; children?: React.ReactNode }) {
  const label = children || risk;
  const riskClass = risk?.toLowerCase() || 'neutral';
  return <span className={`badge ${riskClass}`}>{label}</span>;
}
