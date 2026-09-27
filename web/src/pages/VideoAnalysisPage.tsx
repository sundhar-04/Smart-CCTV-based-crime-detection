import React, { useState, useEffect } from 'react';
import {
  uploadAnalysisVideo,
  loadSampleAnalysisVideo,
  updateAnalysisZones,
  startAnalysis,
  getAnalysisStatus,
  getAnalysisResult,
  AnalysisJobCreate,
  AnalysisJobStatus,
  AnalysisJobResult,
  Alert
} from '../api/client';
import { ICN } from '../components/Icon';
import { ZoneEditor } from '../components/ZoneEditor';
import { RiskBadge } from '../components/RiskBadge';
import { ConfidenceBar } from '../components/ConfidenceBar';

export function VideoAnalysisPage({ onOpenIncident }: { onOpenIncident?: (alert: Alert) => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [job, setJob] = useState<AnalysisJobCreate | null>(null);
  const [zones, setZones] = useState<any[]>([]);
  const [status, setStatus] = useState<AnalysisJobStatus | null>(null);
  const [result, setResult] = useState<AnalysisJobResult | null>(null);
  const [uploading, setUploading] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);

  // Poll job status during analysis execution
  useEffect(() => {
    if (!job || !analyzing) return;

    const interval = setInterval(async () => {
      try {
        const st = await getAnalysisStatus(job.job_id);
        setStatus(st);
        if (st.status === 'completed' || st.status === 'failed') {
          setAnalyzing(false);
          clearInterval(interval);
          const res = await getAnalysisResult(job.job_id);
          setResult(res);
        }
      } catch (err) {
        console.error('Error fetching job status:', err);
      }
    }, 1000);

    return () => clearInterval(interval);
  }, [job, analyzing]);

  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files || e.target.files.length === 0) return;
    const selectedFile = e.target.files[0];
    setFile(selectedFile);
    setUploading(true);
    setJob(null);
    setStatus(null);
    setResult(null);

    try {
      const createdJob = await uploadAnalysisVideo(selectedFile);
      setJob(createdJob);
    } catch (err: any) {
      alert(`Upload failed: ${err.message}`);
    } finally {
      setUploading(false);
    }
  };

  const handleLoadSample = async () => {
    setUploading(true);
    setJob(null);
    setStatus(null);
    setResult(null);
    try {
      const createdJob = await loadSampleAnalysisVideo();
      setJob(createdJob);
    } catch (err: any) {
      alert(`Load sample failed: ${err.message}`);
    } finally {
      setUploading(false);
    }
  };

  const handleStartAnalysis = async () => {
    let currentJob = job;
    setAnalyzing(true);
    try {
      if (!currentJob) {
        currentJob = await loadSampleAnalysisVideo();
        setJob(currentJob);
      }
      if (zones.length > 0) {
        await updateAnalysisZones(currentJob.job_id, zones);
      }
      await startAnalysis(currentJob.job_id);
    } catch (err: any) {
      alert(`Start analysis failed: ${err.message}`);
      setAnalyzing(false);
    }
  };

  return (
    <div className="fade-in">
      <div className="page-header">
        <div>
          <div className="page-title">Video Analysis Pipeline</div>
          <div className="page-sub">
            Real YOLOv8 detection, object tracking & RiskEngine multi-signal evaluation on recorded clips
          </div>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 340px', gap: 16 }}>
        {/* Left Column: Upload & Zone Editor & Result */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {/* Step 1: File Upload */}
          <div className="panel">
            <div className="panel-title-row">
              <span className="panel-title">1. Upload Video Clip</span>
            </div>
            <div className="panel-body">
              {!job ? (
                <div>
                  <div
                    style={{
                      border: '2px dashed var(--border)',
                      borderRadius: 8,
                      padding: 24,
                      textAlign: 'center',
                      background: 'var(--panel)',
                      cursor: 'pointer'
                    }}
                    onClick={() => document.getElementById('video-upload-input')?.click()}
                  >
                    <input
                      type="file"
                      id="video-upload-input"
                      accept="video/mp4,video/avi,video/mkv"
                      style={{ display: 'none' }}
                      onChange={handleFileSelect}
                    />
                    {ICN.upload({ size: 32, style: { color: 'var(--accent)', margin: '0 auto 8px' } })}
                    <div style={{ fontWeight: 600, fontSize: 13.5 }}>
                      {uploading ? 'Uploading & Extracting Frame...' : 'Click or drop video clip here to analyze'}
                    </div>
                    <div style={{ fontSize: 11, color: 'var(--text-low)', marginTop: 4 }}>
                      Supports MP4, AVI (Full frame-by-frame YOLOv8 + Risk Engine processing)
                    </div>
                  </div>

                  <div style={{ marginTop: 12, textAlign: 'center' }}>
                    <span style={{ fontSize: 11, color: 'var(--text-low)', marginRight: 8 }}>OR</span>
                    <button className="btn sm primary" onClick={handleLoadSample} disabled={uploading}>
                      {ICN.film({ size: 14 })} Load Sample Video (demo_annotated.mp4)
                    </button>
                  </div>
                </div>
              ) : (
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    {ICN.film({ size: 20, style: { color: 'var(--accent)' } })}
                    <div>
                      <div style={{ fontWeight: 600, fontSize: 13 }}>{job.filename}</div>
                      <div style={{ fontSize: 11, color: 'var(--text-mid)' }} className="mono">
                        Job ID: {job.job_id} · Status: {job.status}
                      </div>
                    </div>
                  </div>
                  <button
                    className="btn sm"
                    onClick={() => {
                      setJob(null);
                      setResult(null);
                      setStatus(null);
                    }}
                  >
                    Change Video
                  </button>
                </div>
              )}
            </div>
          </div>

          {/* Step 2: Zone Draw Canvas */}
          {job && (
            <div className="panel">
              <div className="panel-title-row">
                <span className="panel-title">2. Draw Restricted Security Zones (Optional)</span>
                <span style={{ fontSize: 11, color: 'var(--text-low)' }}>
                  Draw zones on extracted frame for zone intrusion scoring
                </span>
              </div>
              <div className="panel-body">
                <ZoneEditor
                  imageSrc={job.extracted_frame_url}
                  initialZones={zones}
                  onChangeZones={(newZones) => setZones(newZones)}
                />
              </div>
            </div>
          )}

          {/* Step 3: Real Analysis Results */}
          {result && (
            <div className="panel">
              <div className="panel-title-row">
                <span className="panel-title">Analysis Execution Summary</span>
                <span className="chip"><span className="dot safe" /> REAL PIPELINE COMPLETE</span>
              </div>
              <div className="panel-body">
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12, marginBottom: 16 }}>
                  <div className="kpi-card">
                    <div className="kpi-label">Frames Processed</div>
                    <div className="kpi-value">{result.total_frames}</div>
                  </div>
                  <div className="kpi-card">
                    <div className="kpi-label">Peak Risk Score</div>
                    <div className="kpi-value" style={{ color: result.peak_risk_score >= 35 ? 'var(--critical)' : 'var(--safe)' }}>
                      {result.peak_risk_score.toFixed(1)} / 35
                    </div>
                  </div>
                  <div className="kpi-card">
                    <div className="kpi-label">Incidents Flagged</div>
                    <div className="kpi-value">{result.alerts.length}</div>
                  </div>
                </div>

                {/* Honest empty-state message */}
                <div style={{ background: 'var(--panel)', padding: 14, borderRadius: 8, border: '1px solid var(--border-soft)' }}>
                  <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-hi)', marginBottom: 4 }}>
                    Pipeline Explanation:
                  </div>
                  <div style={{ fontSize: 12.5, color: 'var(--text-mid)', lineHeight: 1.5 }}>
                    {result.no_alert_reason}
                  </div>
                </div>

                {/* List generated alerts if any */}
                {result.alerts.length > 0 && (
                  <div style={{ marginTop: 16 }}>
                    <div className="panel-title" style={{ marginBottom: 8 }}>
                      Generated Incidents ({result.alerts.length})
                    </div>
                    {result.alerts.map((al) => (
                      <div
                        key={al.id}
                        className="list-row"
                        style={{ padding: 10, background: 'var(--panel-hover)', borderRadius: 6, marginBottom: 6 }}
                        onClick={() => onOpenIncident && onOpenIncident(al)}
                      >
                        <RiskBadge risk={al.risk_level}>{al.risk_level}</RiskBadge>
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div style={{ fontWeight: 600, fontSize: 13 }}>{al.reasons?.[0] || al.id}</div>
                          <div style={{ fontSize: 11, color: 'var(--text-mid)' }} className="mono">
                            Zone: {al.zone || 'Z1'} · Risk Score: {al.risk_score}
                          </div>
                        </div>
                        <button className="btn sm primary">Inspect Evidence</button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Right Column: Execution Controls & Live Risk Timeline */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div className="panel">
            <div className="panel-title-row">
              <span className="panel-title">Execute Pipeline</span>
            </div>
            <div className="panel-body">
              <button
                className="btn primary"
                style={{ width: '100%', justifyContent: 'center', padding: 12, fontSize: 13 }}
                onClick={handleStartAnalysis}
                disabled={analyzing}
              >
                {analyzing ? ICN.restart({ size: 16, className: 'spin' }) : ICN.play({ size: 16 })}
                {analyzing ? ' Running YOLOv8 Detection...' : ' Start YOLOv8 Video Analysis'}
              </button>

              {status && (
                <div style={{ marginTop: 16 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, marginBottom: 4 }}>
                    <span>Processing Progress</span>
                    <span className="mono">{status.progress?.toFixed(0)}%</span>
                  </div>
                  <div className="progress-track">
                    <div className="progress-fill" style={{ width: `${status.progress}%` }} />
                  </div>
                  <div style={{ fontSize: 11, color: 'var(--text-low)', marginTop: 8 }} className="mono">
                    Frame {status.current_frame} / {status.total_frames} | Peak Risk: {status.peak_risk_score?.toFixed(1)}
                  </div>
                </div>
              )}
            </div>
          </div>

          <div className="panel">
            <div className="panel-title-row">
              <span className="panel-title">Pipeline Architecture</span>
            </div>
            <div className="panel-body" style={{ fontSize: 11.5, color: 'var(--text-mid)', lineHeight: 1.6 }}>
              <p>✓ <b>YOLOv8 Object Detection:</b> Real neural network frame inference for person/object bounding boxes.</p>
              <p>✓ <b>SimpleIOU / ByteTrack:</b> Multi-object tracking across frames.</p>
              <p>✓ <b>RiskEngine:</b> Evaluates motion, dwell time, loitering, and polygon zone intrusion.</p>
              <p>✓ <b>Evidence Chain:</b> Appends hash-backed tamper-evident evidence logs on alert trigger.</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
