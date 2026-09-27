import React, { useEffect, useRef } from 'react';
import Chart from 'chart.js/auto';

interface ChartCanvasProps {
  type: any;
  data: any;
  options?: any;
  height?: string;
}

export function ChartCanvas({ type, data, options, height = '220px' }: ChartCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const chartRef = useRef<Chart | null>(null);

  useEffect(() => {
    if (!canvasRef.current) return;
    chartRef.current = new Chart(canvasRef.current, {
      type,
      data,
      options: Object.assign(
        {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { display: false } },
        },
        options || {}
      ),
    });

    return () => {
      if (chartRef.current) {
        chartRef.current.destroy();
      }
    };
  }, [type, data, options]);

  return (
    <div style={{ height, position: 'relative' }}>
      <canvas ref={canvasRef} />
    </div>
  );
}
