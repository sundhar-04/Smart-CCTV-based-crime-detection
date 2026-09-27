import React, { useState, useEffect, useRef, useMemo } from 'react';
import { ICN } from './Icon';

interface CommandPaletteProps {
  onClose: () => void;
  onNavigate: (pageKey: string) => void;
  cameras?: any[];
  incidents?: any[];
}

export function CommandPalette({ onClose, onNavigate, cameras = [], incidents = [] }: CommandPaletteProps) {
  const [q, setQ] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose();
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const suggestions = useMemo(() => {
    const query = q.trim().toLowerCase();
    const staticCmds: Array<{ icon: any; label: string; sub?: string; action: () => void }> = [
      { icon: ICN.alert, label: 'Show high-risk incidents today', action: () => onNavigate('incidents') },
      { icon: ICN.bell, label: 'Show alerts from the last hour', action: () => onNavigate('alerts') },
      { icon: ICN.map, label: 'Open camera network map', action: () => onNavigate('map') },
      { icon: ICN.weapon, label: 'Find weapon detections', action: () => onNavigate('incidents') },
      { icon: ICN.chart, label: 'Open analytics overview', action: () => onNavigate('analytics') },
      { icon: ICN.film, label: 'Open Video Analysis (real YOLOv8 pipeline)', action: () => onNavigate('analysis') },
    ];
    if (!query) return staticCmds;

    const camMatches = cameras
      .filter((c) => (c.id + c.name + (c.location || '')).toLowerCase().includes(query))
      .slice(0, 5)
      .map((c) => ({ icon: ICN.camera, label: `${c.id} — ${c.name}`, sub: c.location, action: () => onNavigate('map') }));

    const incMatches = incidents
      .filter((i) => (i.id + (i.types ? i.types.join(' ') : '') + (i.camera_name || '')).toLowerCase().includes(query))
      .slice(0, 5)
      .map((i) => ({ icon: ICN.alert, label: i.id, sub: `${i.risk_level || ''} · ${i.camera_name || ''}`, action: () => onNavigate('incidents') }));

    const cmdMatches = staticCmds.filter((c) => c.label.toLowerCase().includes(query));

    return [...incMatches, ...camMatches, ...cmdMatches];
  }, [q, cameras, incidents, onNavigate]);

  return (
    <div className="cmdk-backdrop" onClick={onClose}>
      <div className="cmdk-box" onClick={(e) => e.stopPropagation()}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '12px 14px', borderBottom: '1px solid var(--border-soft)' }}>
          {ICN.search({ size: 15, style: { color: 'var(--text-mid)' } })}
          <input
            ref={inputRef}
            value={q}
            onInput={(e: any) => setQ(e.target.value)}
            placeholder="Type a command or search..."
            style={{ flex: 1, background: 'transparent', border: 'none', outline: 'none', color: 'var(--text-hi)', fontSize: 13.5 }}
          />
          <span className="kbd-key">ESC</span>
        </div>
        <div style={{ maxHeight: 360, overflowY: 'auto' }}>
          {suggestions.length === 0 && (
            <div style={{ padding: 20, color: 'var(--text-low)', fontSize: 12.5 }}>No matches for "{q}".</div>
          )}
          {suggestions.map((s, i) => (
            <div
              key={i}
              className="list-row"
              style={{ padding: '10px 14px' }}
              onClick={() => {
                s.action();
                onClose();
              }}
            >
              <span style={{ color: 'var(--text-mid)' }}>{s.icon({ size: 15 })}</span>
              <div style={{ minWidth: 0, flex: 1 }}>
                <div style={{ fontSize: 12.5, fontWeight: 500 }}>{s.label}</div>
                {s.sub && (
                  <div style={{ fontSize: 11, color: 'var(--text-low)' }} className="mono">
                    {s.sub}
                  </div>
                )}
              </div>
              {ICN.chevronRight({ size: 13, style: { color: 'var(--text-low)' } })}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
