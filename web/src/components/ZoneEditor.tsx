import React, { useState, useRef, useEffect } from 'react';
import { ICN } from './Icon';

interface Point {
  x: number;
  y: number;
}

interface Zone {
  name: string;
  points: Point[];
}

interface ZoneEditorProps {
  imageSrc: string;
  initialZones?: Zone[];
  onChangeZones?: (zones: Zone[]) => void;
}

export function ZoneEditor({ imageSrc, initialZones = [], onChangeZones }: ZoneEditorProps) {
  const [zones, setZones] = useState<Zone[]>(initialZones);
  const [activePoints, setActivePoints] = useState<Point[]>([]);
  const [currentZoneName, setCurrentZoneName] = useState<string>('Restricted Zone 1');
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    drawCanvas();
  }, [imageSrc, zones, activePoints]);

  const drawCanvas = () => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const img = new Image();
    img.src = imageSrc;
    img.onload = () => {
      canvas.width = img.width || 640;
      canvas.height = img.height || 360;

      // Draw base image
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height);

      // Draw completed zones
      zones.forEach((zone, idx) => {
        if (zone.points.length === 0) return;
        ctx.beginPath();
        ctx.moveTo(zone.points[0].x, zone.points[0].y);
        for (let i = 1; i < zone.points.length; i++) {
          ctx.lineTo(zone.points[i].x, zone.points[i].y);
        }
        ctx.closePath();
        ctx.fillStyle = 'rgba(229, 72, 77, 0.25)';
        ctx.fill();
        ctx.strokeStyle = '#E5484D';
        ctx.lineWidth = 2;
        ctx.stroke();

        // Label
        const firstPt = zone.points[0];
        ctx.fillStyle = '#E5484D';
        ctx.font = '12px var(--font-mono)';
        ctx.fillText(zone.name || `Zone ${idx + 1}`, firstPt.x + 5, firstPt.y - 5);
      });

      // Draw active in-progress polygon points
      if (activePoints.length > 0) {
        ctx.beginPath();
        ctx.moveTo(activePoints[0].x, activePoints[0].y);
        for (let i = 1; i < activePoints.length; i++) {
          ctx.lineTo(activePoints[i].x, activePoints[i].y);
        }
        ctx.strokeStyle = '#4C9EFF';
        ctx.lineWidth = 2;
        ctx.stroke();

        activePoints.forEach((pt) => {
          ctx.beginPath();
          ctx.arc(pt.x, pt.y, 4, 0, Math.PI * 2);
          ctx.fillStyle = '#4C9EFF';
          ctx.fill();
        });
      }
    };
  };

  const handleCanvasClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const scaleX = canvas.width / rect.width;
    const scaleY = canvas.height / rect.height;

    const x = Math.round((e.clientX - rect.left) * scaleX);
    const y = Math.round((e.clientY - rect.top) * scaleY);

    setActivePoints([...activePoints, { x, y }]);
  };

  const completeZone = () => {
    if (activePoints.length < 3) {
      alert('Please click at least 3 points to define a valid polygon zone.');
      return;
    }
    const newZones = [...zones, { name: currentZoneName, points: activePoints }];
    setZones(newZones);
    setActivePoints([]);
    setCurrentZoneName(`Restricted Zone ${newZones.length + 1}`);
    if (onChangeZones) onChangeZones(newZones);
  };

  const clearZones = () => {
    setZones([]);
    setActivePoints([]);
    if (onChangeZones) onChangeZones([]);
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-mid)' }}>
          Click on frame to draw polygon zone boundaries ({activePoints.length} points added)
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn sm primary" onClick={completeZone} disabled={activePoints.length < 3}>
            {ICN.check({ size: 13 })} Complete Zone
          </button>
          <button className="btn sm danger" onClick={clearZones} disabled={zones.length === 0 && activePoints.length === 0}>
            {ICN.x({ size: 13 })} Clear All
          </button>
        </div>
      </div>

      <div style={{ position: 'relative', border: '1px solid var(--border)', borderRadius: 8, overflow: 'hidden', background: '#000' }}>
        <canvas
          ref={canvasRef}
          onClick={handleCanvasClick}
          style={{ width: '100%', maxHeight: '420px', objectFit: 'contain', cursor: 'crosshair', display: 'block' }}
        />
      </div>

      {zones.length > 0 && (
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          {zones.map((z, idx) => (
            <span key={idx} className="chip">
              <span className="dot critical" /> {z.name} ({z.points.length} pts)
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
