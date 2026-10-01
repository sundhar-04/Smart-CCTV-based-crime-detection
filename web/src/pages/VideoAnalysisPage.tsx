import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  uploadAnalysisVideo,
  loadSampleAnalysisVideo,
  updateAnalysisZones,
  startAnalysis,
  getAnalysisStatus,
  getAnalysisResult,
  getAnalysisLive,
  AnalysisJobCreate,
  AnalysisJobResult,
  LiveData,
  LiveTrack,
  LiveAlert,
  DetectionItem,
  AnalysisFramePayload,
  Alert
} from '../api/client';
import { wsClient } from '../ws/client';
import { ICN } from '../components/Icon';
import { ZoneEditor } from '../components/ZoneEditor';
import { RiskBadge } from '../components/RiskBadge';
import { ConfidenceBar } from '../components/ConfidenceBar';

const ANALYSIS_STAGES = ['Upload', 'Zone Setup', 'Processing', 'Detection', 'Risk Scoring', 'Report'];

function riskColor(levelOrScore: string | number, thr = 60): string {
  if (typeof levelOrScore === 'string') {
    const l = levelOrScore.toUpperCase();
    if (l === 'CRITICAL') return 'var(--critical)';
    if (l === 'HIGH') return 'var(--high)';
    if (l === 'ELEVATED') return 'var(--medium)';
    return 'var(--safe)';
  }
  const score = levelOrScore;
  if (score >= 400) return 'var(--critical)';
  if (score >= 140) return 'var(--high)';
  if (score >= 50) return 'var(--medium)';
  return 'var(--safe)';
}

function riskLabel(score: number, types?: string[], reasons?: string[]): string {
  const all = [...(types || []), ...(reasons || [])].join(' ').toUpperCase();
  const hasViolence = all.includes('KNOCKOUT') || all.includes('STRIKE') || all.includes('OVERHEAD') || all.includes('SWING');
  if (hasViolence || score >= 400) return 'CRITICAL';
  if (all.includes('FIGHT') || (all.includes('WEAPON') && (all.includes('SPRINT') || all.includes('APPROACH'))) || score >= 140) return 'HIGH';
  if (all.includes('WEAPON') || all.includes('SPRINT') || all.includes('APPROACH') || score >= 50) return 'ELEVATED';
  return 'LOW';
}

interface DetectionOverlayProps {
  detections: DetectionItem[];
  origW: number;
  origH: number;
  displayedW: number;
  displayedH: number;
  thr?: number;
}

/** Overlay canvas that draws bounding boxes on top of the live frame image with exact coordinate scaling */
function DetectionOverlay({
  detections,
  origW,
  origH,
  displayedW,
  displayedH,
  thr = 60
}: DetectionOverlayProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !displayedW || !displayedH) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // Set canvas internal resolution to match displayed screen dimensions
    canvas.width = displayedW;
    canvas.height = displayedH;

    ctx.clearRect(0, 0, canvas.width, canvas.height);

    if (!detections || detections.length === 0) return;

    const baseW = origW > 0 ? origW : displayedW;
    const baseH = origH > 0 ? origH : displayedH;
    const scaleX = displayedW / baseW;
    const scaleY = displayedH / baseH;

    detections.forEach(det => {
      const [x1, y1, x2, y2] = det.bbox;
      const displayX1 = x1 * scaleX;
      const displayY1 = y1 * scaleY;
      const displayX2 = x2 * scaleX;
      const displayY2 = y2 * scaleY;
      const boxW = Math.max(2, displayX2 - displayX1);
      const boxH = Math.max(2, displayY2 - displayY1);

      const cls = det.class;
      const sc = det.risk_score || 0;
      const isWeapon = ['knife', 'baseball bat', 'scissors', 'Gun', 'Weapon', 'gun', 'weapon'].includes(cls);
      const violenceSignals = [
        'FIGHT_SUSPECTED', 'AGGRESSIVE_APPROACH', 'PERSON_DOWN',
        'PHYSICAL_STRIKE', 'OVERHEAD_STANCE', 'VIOLENT_SWING', 'KNOCKOUT_FALL'
      ];
      const hasViolence = (det.signals || []).some(s => violenceSignals.includes(s));

      const col = isWeapon || hasViolence ? '#FF3B3B' : riskColor(sc, thr);

      // 1. Draw crisp bounding box
      ctx.strokeStyle = col;
      ctx.lineWidth = 2;
      ctx.strokeRect(displayX1, displayY1, boxW, boxH);

      // 2. Tactical corner accents
      const cs = Math.min(14, boxW * 0.25, boxH * 0.25);
      ctx.lineWidth = 3;
      // Top-Left
      ctx.beginPath(); ctx.moveTo(displayX1, displayY1 + cs); ctx.lineTo(displayX1, displayY1); ctx.lineTo(displayX1 + cs, displayY1); ctx.stroke();
      // Top-Right
      ctx.beginPath(); ctx.moveTo(displayX2 - cs, displayY1); ctx.lineTo(displayX2, displayY1); ctx.lineTo(displayX2, displayY1 + cs); ctx.stroke();
      // Bottom-Left
      ctx.beginPath(); ctx.moveTo(displayX1, displayY2 - cs); ctx.lineTo(displayX1, displayY2); ctx.lineTo(displayX1 + cs, displayY2); ctx.stroke();
      // Bottom-Right
      ctx.beginPath(); ctx.moveTo(displayX2 - cs, displayY2); ctx.lineTo(displayX2, displayY2); ctx.lineTo(displayX2, displayY2 - cs); ctx.stroke();

      // 3. Label badges matching UI requirement
      // Line 1: Class + Conf (e.g. "PERSON 91%")
      const confPct = Math.round(det.confidence * 100);
      const classStr = isWeapon ? `WEAPON: ${cls.toUpperCase()}` : cls.toUpperCase();
      const line1 = `${classStr} ${confPct}%`;
      // Line 2: Track ID + Risk score (e.g. "ID: 12 · r=42")
      const line2 = `ID: ${det.track_id}${sc > 10 ? ` · r=${sc.toFixed(0)}` : ''}`;

      ctx.font = 'bold 10px JetBrains Mono, monospace';
      const tw1 = ctx.measureText(line1).width;
      ctx.font = '9px JetBrains Mono, monospace';
      const tw2 = ctx.measureText(line2).width;
      const badgeW = Math.max(tw1, tw2) + 14;
      const badgeH = 26;

      // Position badge right above box or inside top if near canvas edge
      const badgeX = Math.max(0, Math.min(displayX1, displayedW - badgeW));
      const badgeY = displayY1 >= badgeH + 4 ? displayY1 - badgeH - 2 : displayY1 + 4;

      // Card background
      ctx.fillStyle = 'rgba(5, 10, 20, 0.90)';
      ctx.fillRect(badgeX, badgeY, badgeW, badgeH);
      ctx.strokeStyle = col;
      ctx.lineWidth = 1;
      ctx.strokeRect(badgeX, badgeY, badgeW, badgeH);

      // Line 1 text
      ctx.fillStyle = col;
      ctx.font = 'bold 10px JetBrains Mono, monospace';
      ctx.fillText(line1, badgeX + 6, badgeY + 11);

      // Line 2 text
      ctx.fillStyle = '#CBD5E1';
      ctx.font = '9px JetBrains Mono, monospace';
      ctx.fillText(line2, badgeX + 6, badgeY + 22);

      // Signal tag if violence detected
      if (hasViolence) {
        const vSignal = (det.signals || []).find(s => violenceSignals.includes(s)) || 'ALERT';
        const sigText = `⚠ ${vSignal}`;
        ctx.font = 'bold 9px JetBrains Mono, monospace';
        const stw = ctx.measureText(sigText).width + 8;
        const sigY = badgeY + badgeH + 2;
        ctx.fillStyle = '#FF3B3B';
        ctx.fillRect(badgeX, sigY, stw, 14);
        ctx.fillStyle = '#05070A';
        ctx.fillText(sigText, badgeX + 4, sigY + 10);
      }
    });
  }, [detections, origW, origH, displayedW, displayedH, thr]);

  return (
    <canvas
      ref={canvasRef}
      style={{
        position: 'absolute',
        top: 0,
        left: 0,
        width: '100%',
        height: '100%',
        pointerEvents: 'none',
      }}
    />
  );
}

export function VideoAnalysisPage({ onOpenIncident }: { onOpenIncident?: (alert: Alert) => void }) {
  const [job, setJob] = useState<AnalysisJobCreate | null>(null);
  const [zones, setZones] = useState<any[]>([]);
  const [analyzing, setAnalyzing] = useState(false);
  const [result, setResult] = useState<AnalysisJobResult | null>(null);

  // Real-time live frame state
  const [live, setLive] = useState<LiveData | null>(null);
  const [liveImageSrc, setLiveImageSrc] = useState<string | null>(null);
  const [liveDetections, setLiveDetections] = useState<DetectionItem[]>([]);
  const [videoDims, setVideoDims] = useState<{ w: number; h: number }>({ w: 640, h: 360 });
  const [displayedDims, setDisplayedDims] = useState<{ w: number; h: number }>({ w: 640, h: 360 });

  const [detectionLog, setDetectionLog] = useState<LiveAlert[]>([]);
  const [uploading, setUploading] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const liveImgRef = useRef<HTMLImageElement>(null);
  const pollRef = useRef<any>(null);
  const activeJobIdRef = useRef<string | null>(null);

  // Stage index based on state
  const stageIndex = !job ? 0
    : result ? 5
    : analyzing ? 2
    : 1;

  const updateDimensions = useCallback(() => {
    if (liveImgRef.current) {
      const rect = liveImgRef.current.getBoundingClientRect();
      if (rect.width > 0 && rect.height > 0) {
        setDisplayedDims({ w: rect.width, h: rect.height });
      }
      if (liveImgRef.current.naturalWidth > 0 && liveImgRef.current.naturalHeight > 0) {
        setVideoDims(prev => ({
          w: prev.w || liveImgRef.current!.naturalWidth,
          h: prev.h || liveImgRef.current!.naturalHeight,
        }));
      }
    } else if (containerRef.current) {
      const rect = containerRef.current.getBoundingClientRect();
      if (rect.width > 0 && rect.height > 0) {
        setDisplayedDims({ w: rect.width, h: rect.height });
      }
    }
  }, []);

  useEffect(() => {
    updateDimensions();
    const handleResize = () => updateDimensions();
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, [updateDimensions]);

  useEffect(() => {
    activeJobIdRef.current = job?.job_id || null;
  }, [job]);

  // Subscribe to real-time WebSocket analysis events
  useEffect(() => {
    const unsubFrame = wsClient.subscribe('analysis_frame', (frameData: AnalysisFramePayload) => {
      if (!activeJobIdRef.current || frameData.job_id !== activeJobIdRef.current) return;

      // Update frame image directly from streaming payload
      if (frameData.image) {
        setLiveImageSrc(frameData.image);
      }
      if (frameData.orig_w && frameData.orig_h) {
        setVideoDims({ w: frameData.orig_w, h: frameData.orig_h });
      }
      setLiveDetections(frameData.detections || []);

      // Keep live state in sync
      setLive(prev => ({
        status: 'processing',
        progress: frameData.total_frames > 0 ? (frameData.frame_index / frameData.total_frames) * 100 : 0,
        current_frame: frameData.frame_index,
        total_frames: frameData.total_frames,
        peak_risk_score: Math.max(prev?.peak_risk_score || 0, frameData.risk_score),
        live_frame_url: prev?.live_frame_url || null,
        image: frameData.image,
        orig_w: frameData.orig_w,
        orig_h: frameData.orig_h,
        detections: frameData.detections,
        tracks: (frameData.detections || []).map(d => ({
          id: d.track_id,
          cls: d.class,
          box: d.bbox,
          risk_score: d.risk_score || 0,
          signals: d.signals || [],
        })),
        alerts: prev?.alerts || []
      }));
    });

    const unsubCompleted = wsClient.subscribe('analysis_completed', (completedData: any) => {
      if (!activeJobIdRef.current || completedData.job_id !== activeJobIdRef.current) return;
      setAnalyzing(false);
      getAnalysisResult(completedData.job_id).then(res => setResult(res)).catch(() => {});
    });

    const unsubProgress = wsClient.subscribe('analysis_progress', (progressData: any) => {
      if (!activeJobIdRef.current || progressData.job_id !== activeJobIdRef.current) return;
      if (progressData.alerts && progressData.alerts.length > 0) {
        setDetectionLog(prev => {
          const existingIds = new Set(prev.map(a => a.id));
          const newOnes = progressData.alerts.filter((a: any) => !existingIds.has(a.id));
          return newOnes.length > 0 ? [...newOnes, ...prev] : prev;
        });
      }
    });

    return () => {
      unsubFrame();
      unsubCompleted();
      unsubProgress();
    };
  }, []);

  // Poll /live every 400ms during analysis as network fallback
  const startPolling = useCallback((jobId: string) => {
    if (pollRef.current) clearInterval(pollRef.current);

    pollRef.current = setInterval(async () => {
      try {
        const data = await getAnalysisLive(jobId);
        setLive(data);

        // Update frame image and detections from fallback
        if (data.image) {
          setLiveImageSrc(data.image);
        } else if (data.live_frame_url) {
          setLiveImageSrc(`${data.live_frame_url}?t=${Date.now()}`);
        }
        if (data.orig_w && data.orig_h) {
          setVideoDims({ w: data.orig_w, h: data.orig_h });
        }
        if (data.detections) {
          setLiveDetections(data.detections);
        }

        // Append new alerts to detection log (deduplicate by id)
        if (data.alerts && data.alerts.length > 0) {
          setDetectionLog(prev => {
            const existingIds = new Set(prev.map(a => a.id));
            const newOnes = data.alerts.filter(a => !existingIds.has(a.id));
            return newOnes.length > 0 ? [...newOnes, ...prev] : prev;
          });
        }

        // Stop when done
        if (data.status === 'completed' || data.status === 'failed') {
          clearInterval(pollRef.current);
          setAnalyzing(false);
          // Fetch full result
          try {
            const res = await getAnalysisResult(jobId);
            setResult(res);
          } catch (_) {}
        }
      } catch (_) {}
    }, 400);
  }, []);

  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current); }, []);

  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files || e.target.files.length === 0) return;
    setUploading(true);
    setJob(null); setLive(null); setResult(null); setDetectionLog([]);
    setLiveImageSrc(null); setLiveDetections([]);
    try {
      const j = await uploadAnalysisVideo(e.target.files[0]);
      setJob(j);
    } catch (err: any) { alert(`Upload failed: ${err.message}`); }
    finally { setUploading(false); }
  };

  const handleLoadSample = async () => {
    setUploading(true);
    setJob(null); setLive(null); setResult(null); setDetectionLog([]);
    setLiveImageSrc(null); setLiveDetections([]);
    try { setJob(await loadSampleAnalysisVideo()); }
    catch (err: any) { alert(`Load sample failed: ${err.message}`); }
    finally { setUploading(false); }
  };

  const handleStartAnalysis = async () => {
    let cur = job;
    if (!cur) { cur = await loadSampleAnalysisVideo(); setJob(cur); }
    setAnalyzing(true);
    setResult(null);
    setDetectionLog([]);
    setLiveImageSrc(null);
    setLiveDetections([]);
    setLive(null);
    if (zones.length > 0) await updateAnalysisZones(cur.job_id, zones);
    await startAnalysis(cur.job_id);
    startPolling(cur.job_id);
  };

  const handleReset = () => {
    if (pollRef.current) clearInterval(pollRef.current);
    setJob(null); setLive(null); setResult(null); setDetectionLog([]);
    setLiveImageSrc(null); setLiveDetections([]); setAnalyzing(false); setZones([]);
  };

  const pct = live?.progress ?? 0;
  const isRunning = analyzing && live?.status === 'processing';
  const thr = 60;

  return (
    <div className="fade-in">
      {/* Page header */}
      <div className="page-header">
        <div>
          <div className="page-title">Video Analysis Pipeline</div>
          <div className="page-sub">Real YOLOv8 detection · ByteTrack multi-object tracking · RiskEngine scoring · live bounding boxes</div>
        </div>
        {job && (
          <button className="btn" onClick={handleReset}>{ICN.x({ size: 13 })} Reset</button>
        )}
      </div>

      {/* Stage breadcrumb */}
      <div style={{ display: 'flex', gap: 6, marginBottom: 14, flexWrap: 'wrap' }}>
        {ANALYSIS_STAGES.map((s, i) => (
          <div key={s} style={{
            display: 'flex', alignItems: 'center', gap: 6,
            padding: '5px 11px', borderRadius: 999, fontSize: 11, fontWeight: 600,
            border: `1px solid ${i <= stageIndex ? 'rgba(76,158,255,0.35)' : 'var(--border-soft)'}`,
            background: i <= stageIndex ? 'var(--info-dim)' : 'var(--panel-raised)',
            color: i <= stageIndex ? 'var(--accent)' : 'var(--text-low)',
            transition: 'all .2s',
          }}>
            <span className="mono">{String(i + 1).padStart(2, '0')}</span> {s}
          </div>
        ))}
      </div>

      {/* Main 2-col grid */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 320px', gap: 14 }}>

        {/* LEFT: Live frame viewer */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>

          {/* Live detection canvas panel */}
          <div className="panel" style={{ overflow: 'hidden' }}>
            <div className="panel-title-row">
              <span className="panel-title">Evidence Preview</span>
              {isRunning && (
                <span className="chip" style={{ color: 'var(--critical)', fontSize: 11 }}>
                  <span className="dot critical" style={{ animation: 'pulse 1s infinite' }} />
                  &nbsp;LIVE INFERENCE
                </span>
              )}
              {live && !isRunning && live.status === 'completed' && (
                <span className="chip"><span className="dot safe" /> COMPLETE</span>
              )}
            </div>
            <div className="panel-body" style={{ padding: 0 }}>

              {/* Drop zone when no job */}
              {!job && (
                <div style={{
                  border: '1.5px dashed var(--border)', borderRadius: 8, margin: 14,
                  height: 340, display: 'flex', flexDirection: 'column',
                  alignItems: 'center', justifyContent: 'center', gap: 10,
                }}>
                  {ICN.upload({ size: 28, style: { color: 'var(--text-low)' } })}
                  <div style={{ fontSize: 13, fontWeight: 600 }}>
                    {uploading ? 'Uploading & extracting frame…' : 'Drop CCTV footage here'}
                  </div>
                  <div style={{ fontSize: 11.5, color: 'var(--text-low)' }}>MP4, AVI, WEBM — or use sample clip</div>
                  <div style={{ display: 'flex', gap: 8, marginTop: 4 }}>
                    <label className="btn primary" style={{ cursor: 'pointer' }}>
                      {ICN.upload({ size: 13 })} Browse Files
                      <input type="file" accept="video/*" style={{ display: 'none' }} onChange={handleFileSelect} disabled={uploading} />
                    </label>
                    <button className="btn" onClick={handleLoadSample} disabled={uploading}>
                      {ICN.film({ size: 13 })} Load Sample
                    </button>
                  </div>
                </div>
              )}

              {/* Live inference frame with transparent canvas overlay */}
              {job && (
                <div
                  ref={containerRef}
                  style={{
                    position: 'relative',
                    background: '#05070A',
                    lineHeight: 0,
                    width: '100%',
                    aspectRatio: videoDims.w && videoDims.h ? `${videoDims.w} / ${videoDims.h}` : '16 / 9',
                    maxHeight: 460,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    overflow: 'hidden',
                  }}
                >
                  {/* Clean frame image (streamed live or fallback) */}
                  <img
                    ref={liveImgRef}
                    src={liveImageSrc || (job ? job.extracted_frame_url : undefined)}
                    alt="Live analysis frame"
                    style={{
                      width: '100%',
                      height: '100%',
                      objectFit: 'contain',
                      display: 'block',
                    }}
                    onLoad={updateDimensions}
                  />

                  {/* Real-time Detection Overlay Canvas */}
                  {isRunning && (
                    <DetectionOverlay
                      detections={liveDetections}
                      origW={videoDims.w}
                      origH={videoDims.h}
                      displayedW={displayedDims.w}
                      displayedH={displayedDims.h}
                      thr={thr}
                    />
                  )}

                  {/* Scanning line animation while processing */}
                  {isRunning && (
                    <div style={{
                      position: 'absolute', left: 0, right: 0, height: 2,
                      background: 'linear-gradient(90deg, transparent, var(--accent), transparent)',
                      animation: 'scan 2s linear infinite',
                      top: `${pct}%`,
                      pointerEvents: 'none',
                    }} />
                  )}

                  {/* HUD overlay: frame counter + status */}
                  {live && (
                    <div style={{
                      position: 'absolute', bottom: 0, left: 0, right: 0,
                      background: 'linear-gradient(transparent, rgba(5,7,10,0.85))',
                      padding: '24px 10px 8px', display: 'flex', alignItems: 'flex-end', gap: 8,
                      pointerEvents: 'none',
                    }}>
                      <span className="mono" style={{
                        fontSize: 10, background: isRunning ? 'rgba(229,72,77,0.85)' : 'rgba(0,0,0,0.6)',
                        padding: '2px 6px', borderRadius: 3, color: '#fff', fontWeight: 700
                      }}>
                        {isRunning ? '● LIVE DETECT' : live.status.toUpperCase()}
                      </span>
                      <span className="mono" style={{ fontSize: 10, color: 'var(--text-mid)', marginLeft: 'auto' }}>
                        FRAME {(live.current_frame || 0).toLocaleString()} / {(live.total_frames || 0).toLocaleString()}
                      </span>
                      <span className="mono" style={{
                        fontSize: 10,
                        color: riskColor(live.peak_risk_score, thr),
                        background: 'rgba(0,0,0,0.6)', padding: '2px 6px', borderRadius: 3
                      }}>
                        PEAK RISK {live.peak_risk_score.toFixed(0)}
                      </span>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>

          {/* Zone drawing panel */}
          {job && !analyzing && !result && (
            <div className="panel">
              <div className="panel-title-row">
                <span className="panel-title">2. Draw Restricted Zones (Optional)</span>
                <span style={{ fontSize: 11, color: 'var(--text-low)' }}>
                  Zone signals: ZONE_ENTER, ZONE_DWELL — skipped if no zone drawn
                </span>
              </div>
              <div className="panel-body">
                <ZoneEditor
                  imageSrc={job.extracted_frame_url}
                  initialZones={zones}
                  onChangeZones={setZones}
                />
              </div>
            </div>
          )}

          {/* Final result summary */}
          {result && (
            <div className="panel">
              <div className="panel-title-row">
                <span className="panel-title">Analysis Report</span>
                <span className="chip"><span className="dot safe" /> REAL PIPELINE</span>
              </div>
              <div className="panel-body">
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 10, marginBottom: 14 }}>
                  {[
                    ['Frames Processed', result.total_frames.toLocaleString()],
                    ['Peak Risk Score', result.peak_risk_score.toFixed(1) + ' / ' + thr],
                    ['Incidents Flagged', String(result.alerts.length)],
                  ].map(([l, v]) => (
                    <div key={l} className="kpi-card">
                      <div className="kpi-label">{l}</div>
                      <div className="kpi-value mono" style={{ fontSize: 18 }}>{v}</div>
                    </div>
                  ))}
                </div>

                <div style={{ background: 'var(--panel)', padding: 12, borderRadius: 8, border: '1px solid var(--border-soft)', fontSize: 12.5, color: 'var(--text-mid)', lineHeight: 1.6 }}>
                  {result.no_alert_reason}
                </div>

                {result.alerts.length > 0 && (
                  <div style={{ marginTop: 14 }}>
                    <div className="panel-title" style={{ marginBottom: 8 }}>Generated Incidents ({result.alerts.length})</div>
                    {result.alerts.map(al => (
                      <div key={al.id} className="list-row"
                        style={{ padding: 10, background: 'var(--panel-hover)', borderRadius: 6, marginBottom: 6, cursor: 'pointer' }}
                        onClick={() => onOpenIncident && onOpenIncident(al)}
                      >
                        <RiskBadge risk={al.risk_level}>{al.risk_level}</RiskBadge>
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div style={{ fontWeight: 600, fontSize: 12.5 }}>{al.reasons?.[0] || al.id}</div>
                          <div className="mono" style={{ fontSize: 10.5, color: 'var(--text-low)', marginTop: 2 }}>
                            Score: {al.risk_score} · Zone: {al.zone || 'unzoned'} · Entity: {al.entity || '—'}
                          </div>
                        </div>
                        <button className="btn sm primary">Inspect</button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>

        {/* RIGHT: Controls + live detection feed */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>

          {/* Processing controls */}
          <div className="panel">
            <div className="panel-title-row"><span className="panel-title">Execute Pipeline</span></div>
            <div className="panel-body">
              {!job ? (
                <button className="btn primary" style={{ width: '100%', justifyContent: 'center', padding: 11 }}
                  onClick={handleLoadSample} disabled={uploading}>
                  {ICN.film({ size: 14 })} Load Sample & Analyze
                </button>
              ) : (
                <button className="btn primary" style={{ width: '100%', justifyContent: 'center', padding: 11, fontSize: 13 }}
                  onClick={handleStartAnalysis} disabled={analyzing}>
                  {analyzing ? ICN.restart({ size: 15, className: 'spin' }) : ICN.play({ size: 15 })}
                  {analyzing ? ' Running YOLOv8...' : ' Start Analysis'}
                </button>
              )}

              {/* Progress bar */}
              {live && (
                <div style={{ marginTop: 14 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, marginBottom: 5 }}>
                    <span style={{ color: 'var(--text-mid)' }}>Progress</span>
                    <span className="mono" style={{ fontWeight: 700 }}>{pct.toFixed(0)}%</span>
                  </div>
                  <div className="progress-track">
                    <div className="progress-fill" style={{ width: `${pct}%`, transition: 'width 0.4s' }} />
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginTop: 10 }}>
                    {[
                      ['Frames', (live.current_frame || 0).toLocaleString()],
                      ['Remaining', Math.max(0, (live.total_frames || 0) - (live.current_frame || 0)).toLocaleString()],
                      ['Live Tracks', String((live.tracks || []).length)],
                      ['Peak Risk', live.peak_risk_score.toFixed(1)],
                    ].map(([label, val]) => (
                      <div key={label} style={{
                        background: 'var(--panel)', border: '1px solid var(--border-soft)',
                        borderRadius: 6, padding: '7px 9px',
                      }}>
                        <div style={{ fontSize: 9.5, color: 'var(--text-low)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>{label}</div>
                        <div className="mono" style={{ fontSize: 15, fontWeight: 700, marginTop: 2 }}>{val}</div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Live track table */}
          {isRunning && (
            <div className="panel">
              <div className="panel-title-row">
                <span className="panel-title">Active Tracks</span>
                <span className="badge info">{liveDetections.length}</span>
              </div>
              <div style={{ overflowY: 'auto', maxHeight: 180 }}>
                {liveDetections.length === 0 ? (
                  <div style={{ padding: '12px 15px', fontSize: 11.5, color: 'var(--text-low)' }}>
                    No detections in current frame
                  </div>
                ) : (
                  liveDetections.map(det => (
                    <div key={det.track_id} style={{
                      display: 'flex', alignItems: 'center', gap: 8,
                      padding: '7px 14px', borderBottom: '1px solid var(--border-soft)'
                    }}>
                      <span style={{
                        width: 8, height: 8, borderRadius: '50%', flexShrink: 0,
                        background: riskColor(det.risk_score || 0, thr),
                        boxShadow: `0 0 6px ${riskColor(det.risk_score || 0, thr)}88`
                      }} />
                      <span className="mono" style={{ fontSize: 11, color: 'var(--text-hi)', fontWeight: 700, minWidth: 70 }}>
                        {['knife', 'baseball bat', 'scissors', 'Gun', 'Weapon', 'gun', 'weapon'].includes(det.class) ? `⚠ ${det.class.toUpperCase()}` : `${det.class.toUpperCase()} #${det.track_id}`}
                      </span>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ fontSize: 9.5, color: 'var(--text-low)' }}>
                          {(det.signals && det.signals.length > 0) ? det.signals.join(', ') : `conf ${(det.confidence * 100).toFixed(0)}%`}
                        </div>
                      </div>
                      <span className="mono" style={{ fontSize: 11, color: riskColor(det.risk_score || 0, thr), fontWeight: 700 }}>
                        r={(det.risk_score || 0).toFixed(0)}
                      </span>
                    </div>
                  ))
                )}
              </div>
            </div>
          )}

          {/* Live detection event log */}
          <div className="panel" style={{ flex: 1, minHeight: 200, display: 'flex', flexDirection: 'column' }}>
            <div className="panel-title-row">
              <span className="panel-title">Live Detections</span>
              <span className="badge info">{detectionLog.length}</span>
            </div>
            <div style={{ overflowY: 'auto', flex: 1, padding: '4px 0' }}>
              {detectionLog.length === 0 ? (
                <div style={{ padding: '14px 15px', fontSize: 11.5, color: 'var(--text-low)' }}>
                  {analyzing ? 'Running inference pipeline…' : 'No alerts fired yet. Start analysis to begin.'}
                </div>
              ) : (
                detectionLog.map((d, i) => (
                  <div key={d.id + i} className="list-row" style={{ padding: '8px 14px', borderBottom: '1px solid var(--border-soft)' }}>
                    <span style={{
                      width: 7, height: 7, borderRadius: '50%', flexShrink: 0,
                      background: riskColor(d.score, thr),
                    }} />
                    <div style={{ minWidth: 0, flex: 1 }}>
                      <div style={{ fontSize: 11.5, fontWeight: 600, color: 'var(--text-hi)' }}>
                        {d.types.join(', ') || 'ALERT'}
                      </div>
                      <div className="mono" style={{ fontSize: 10, color: 'var(--text-low)', marginTop: 2 }}>
                        {d.entity} · {d.reasons?.[0] || ''} · score {d.score.toFixed(0)}
                      </div>
                    </div>
                    <span className="mono" style={{
                      fontSize: 10.5, fontWeight: 700,
                      color: riskColor(d.risk_level || riskLabel(d.score, d.types, d.reasons)),
                      background: riskColor(d.risk_level || riskLabel(d.score, d.types, d.reasons)) + '22',
                      padding: '2px 6px', borderRadius: 4
                    }}>
                      {d.risk_level || riskLabel(d.score, d.types, d.reasons)}
                    </span>
                  </div>
                ))
              )}
            </div>
          </div>

          {/* Pipeline info */}
          <div className="panel">
            <div className="panel-title-row"><span className="panel-title">Pipeline</span></div>
            <div className="panel-body" style={{ fontSize: 11, color: 'var(--text-mid)', lineHeight: 1.7 }}>
              <div>✓ <b>YOLOv8n</b> — person / knife / baseball bat / luggage</div>
              <div>✓ <b>YOLOv8n-pose</b> — strike, overhead weapon & fall classifier (60 FPS)</div>
              <div>✓ <b>ByteTrack / IOU</b> — multi-object tracking</div>
              <div>✓ <b>RiskEngine</b> — FIGHT / ASSAULT, SPRINT, WEAPON, FALL</div>
              <div>✓ <b>Live frames</b> — annotated JPEG polled every 400ms</div>
            </div>
          </div>
        </div>
      </div>

      {/* Scanning animation keyframes */}
      <style>{`
        @keyframes scan {
          0%   { top: 0%; opacity: 0; }
          5%   { opacity: 1; }
          95%  { opacity: 1; }
          100% { top: 100%; opacity: 0; }
        }
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50%       { opacity: 0.3; }
        }
        .spin { animation: spin 1s linear infinite; }
        @keyframes spin { to { transform: rotate(360deg); } }
      `}</style>
    </div>
  );
}
