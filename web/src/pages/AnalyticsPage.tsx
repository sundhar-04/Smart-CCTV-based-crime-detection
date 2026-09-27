import React, { useState, useEffect } from 'react';
import { ChartCanvas } from '../components/ChartCanvas';
import { getMetricsSummary, getCameraMetrics } from '../api/client';

export function AnalyticsPage() {
  const [metrics, setMetrics] = useState<any>(null);
  const [camMetrics, setCamMetrics] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([getMetricsSummary(), getCameraMetrics()])
      .then(([m, cm]) => { setMetrics(m); setCamMetrics(cm); })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  if (loading || !metrics) {
    return <div className="fade-in" style={{ padding: 32, color: 'var(--text-mid)' }}>Loading analytics...</div>;
  }

  const peakHours = metrics.peak_hours || {};
  const allHours = Array.from({ length: 24 }, (_, i) => String(i).padStart(2, '0'));
  const trendData = {
    labels: allHours,
    datasets: [{
      label: 'Detections by Hour',
      data: allHours.map(h => peakHours[h] || 0),
      borderColor: '#4C9EFF',
      backgroundColor: 'rgba(76,158,255,0.15)',
      fill: true,
      tension: 0.3
    }]
  };

  const cats = metrics.category_totals || {};
  const catLabels = Object.keys(cats);
  const categoryData = {
    labels: catLabels.length > 0 ? catLabels : ['No Data'],
    datasets: [{
      data: catLabels.length > 0 ? catLabels.map(k => cats[k]) : [1],
      backgroundColor: ['#E5484D', '#F0883E', '#E6C560', '#4C9EFF', '#3DD68C', '#A78BFA', '#FB923C', '#22D3EE']
    }]
  };

  const rd = metrics.risk_distribution || {};
  const riskData = {
    labels: ['CRITICAL', 'HIGH', 'ELEVATED', 'LOW'],
    datasets: [{
      label: 'Alerts by Risk',
      data: [rd.CRITICAL || 0, rd.HIGH || 0, rd.ELEVATED || 0, rd.LOW || 0],
      backgroundColor: ['#E5484D', '#F0883E', '#E6C560', '#3DD68C']
    }]
  };

  const hist = metrics.confidence_histogram || {};
  const histLabels = Object.keys(hist).sort();
  const histData = {
    labels: histLabels.length > 0 ? histLabels : ['0-10'],
    datasets: [{
      label: 'Risk Score Distribution',
      data: histLabels.length > 0 ? histLabels.map(k => hist[k]) : [0],
      backgroundColor: '#4C9EFF'
    }]
  };

  const camData = {
    labels: camMetrics.map(c => c.camera_name),
    datasets: [{
      label: 'False Positive Rate (%)',
      data: camMetrics.map(c => c.false_positive_rate),
      backgroundColor: '#F0883E'
    }, {
      label: 'Avg Risk Score',
      data: camMetrics.map(c => c.avg_risk_score),
      backgroundColor: '#4C9EFF'
    }]
  };

  return (
    <div className="fade-in">
      <div className="page-header">
        <div>
          <div className="page-title">Surveillance Analytics</div>
          <div className="page-sub">
            Real-time threat metrics computed from {metrics.total_incidents} incidents across all cameras
          </div>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: 12, marginBottom: 16 }}>
        <div className="kpi-card">
          <div className="kpi-label">Total Incidents</div>
          <div className="kpi-value">{metrics.total_incidents}</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-label">Critical</div>
          <div className="kpi-value" style={{ color: 'var(--critical)' }}>{rd.CRITICAL || 0}</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-label">High</div>
          <div className="kpi-value" style={{ color: 'var(--warning)' }}>{rd.HIGH || 0}</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-label">Categories</div>
          <div className="kpi-value">{catLabels.length}</div>
        </div>
      </div>

      <div className="grid-2col">
        <div className="panel">
          <div className="panel-title-row">
            <span className="panel-title">Detection Velocity (24 Hours)</span>
          </div>
          <div className="panel-body">
            <ChartCanvas type="line" data={trendData} height="260px" />
          </div>
        </div>

        <div className="panel">
          <div className="panel-title-row">
            <span className="panel-title">Incident Category Distribution</span>
          </div>
          <div className="panel-body">
            <ChartCanvas type="doughnut" data={categoryData} height="260px" />
          </div>
        </div>
      </div>

      <div className="grid-2col" style={{ marginTop: 16 }}>
        <div className="panel">
          <div className="panel-title-row">
            <span className="panel-title">Risk Level Distribution</span>
          </div>
          <div className="panel-body">
            <ChartCanvas type="bar" data={riskData} height="260px" />
          </div>
        </div>

        <div className="panel">
          <div className="panel-title-row">
            <span className="panel-title">Risk Score Histogram</span>
          </div>
          <div className="panel-body">
            <ChartCanvas type="bar" data={histData} height="260px" />
          </div>
        </div>
      </div>

      <div className="panel" style={{ marginTop: 16 }}>
        <div className="panel-title-row">
          <span className="panel-title">Camera Performance Metrics</span>
        </div>
        <div className="panel-body">
          {camMetrics.length > 0 ? (
            <ChartCanvas type="bar" data={camData} height="260px" />
          ) : (
            <div style={{ color: 'var(--text-mid)', padding: 24, textAlign: 'center' }}>No camera metrics available</div>
          )}
        </div>
      </div>
    </div>
  );
}
