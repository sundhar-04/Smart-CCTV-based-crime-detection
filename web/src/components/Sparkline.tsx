import React, { useEffect, useRef } from 'react';

export function Sparkline({ data, color }: { data: number[]; color?: string }) {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas || !data || data.length === 0) return;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const rect = canvas.parentElement?.getBoundingClientRect();
    const w = rect?.width || 120, h = 34;
    canvas.width = w * dpr; canvas.height = h * dpr;
    canvas.style.width = w + 'px'; canvas.style.height = h + 'px';
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);

    const max = Math.max(...data, 1);
    const min = Math.min(...data, 0);
    const range = Math.max(max - min, 1);
    const step = w / Math.max(data.length - 1, 1);

    ctx.beginPath();
    data.forEach((v, i) => {
      const x = i * step;
      const y = h - ((v - min) / range) * (h - 4) - 2;
      if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    });
    ctx.strokeStyle = color || '#4C9EFF';
    ctx.lineWidth = 1.6;
    ctx.stroke();

    const grad = ctx.createLinearGradient(0, 0, 0, h);
    grad.addColorStop(0, (color || '#4C9EFF') + '33');
    grad.addColorStop(1, (color || '#4C9EFF') + '00');
    ctx.lineTo(w, h); ctx.lineTo(0, h); ctx.closePath();
    ctx.fillStyle = grad;
    ctx.fill();
  }, [data, color]);

  return <canvas ref={ref} style={{ width: '100%', height: '34px', display: 'block' }} />;
}
