import React, { useState, useEffect } from 'react';
import { RiskBadge } from './RiskBadge';

export interface ToastItem {
  id: string;
  title: string;
  sub?: string;
  risk?: string;
  timestamp: number;
}

interface ToastStackProps {
  toasts: ToastItem[];
  onDismiss?: (id: string) => void;
}

function SingleToast({ toast, onDismiss }: { toast: ToastItem; onDismiss: (id: string) => void }) {
  useEffect(() => {
    const timer = setTimeout(() => {
      onDismiss(toast.id);
    }, 5000); // auto-dismiss after 5s
    return () => clearTimeout(timer);
  }, [toast.id, onDismiss]);

  return (
    <div
      className="toast"
      style={{
        position: 'relative',
        animation: 'fadeIn 0.2s ease-out',
        cursor: 'pointer'
      }}
      onClick={() => onDismiss(toast.id)}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 3 }}>
        <RiskBadge risk={toast.risk || 'info'} />
        <span style={{ fontSize: 11, color: 'var(--text-low)', marginLeft: 'auto' }} className="mono">
          {new Date(toast.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
        </span>
        <button
          onClick={(e) => {
            e.stopPropagation();
            onDismiss(toast.id);
          }}
          title="Dismiss notification"
          style={{
            background: 'none',
            border: 'none',
            color: 'var(--text-low)',
            cursor: 'pointer',
            fontSize: 14,
            lineHeight: 1,
            padding: '0 2px',
            marginLeft: 4,
            opacity: 0.7
          }}
          onMouseEnter={(e) => (e.currentTarget.style.opacity = '1')}
          onMouseLeave={(e) => (e.currentTarget.style.opacity = '0.7')}
        >
          ✕
        </button>
      </div>
      <div style={{ fontSize: 12, fontWeight: 600 }}>{toast.title}</div>
      {toast.sub && <div style={{ fontSize: 11, color: 'var(--text-mid)', marginTop: 2 }}>{toast.sub}</div>}
    </div>
  );
}

export function ToastStack({ toasts, onDismiss }: ToastStackProps) {
  const [internalDismissed, setInternalDismissed] = useState<Set<string>>(new Set());

  const handleDismiss = (id: string) => {
    setInternalDismissed((prev) => new Set(prev).add(id));
    if (onDismiss) {
      onDismiss(id);
    }
  };

  const visibleToasts = (toasts || []).filter((t) => !internalDismissed.has(t.id));

  if (visibleToasts.length === 0) return null;

  return (
    <div className="toast-stack">
      {visibleToasts.map((t) => (
        <SingleToast key={t.id} toast={t} onDismiss={handleDismiss} />
      ))}
    </div>
  );
}
