import React, { useState } from 'react';
import { Camera, saveCamera, updateCamera, testCameraConnection, CameraTestConnectionResult } from '../api/client';
import { ICN } from './Icon';

interface AddCameraModalProps {
  camera?: Camera | null;
  isOpen: boolean;
  onClose: () => void;
  onSaved: (camera: Camera) => void;
}

export function AddCameraModal({ camera, isOpen, onClose, onSaved }: AddCameraModalProps) {
  const isEdit = Boolean(camera && camera.id);

  const [name, setName] = useState(camera?.name || 'Phone Camera 01');
  const [streamUrl, setStreamUrl] = useState(camera?.stream_url || camera?.rtsp_url || '');
  const [protocol, setProtocol] = useState<'mjpeg' | 'http' | 'rtsp'>((camera?.protocol as any) || 'mjpeg');
  const [location, setLocation] = useState(camera?.location || 'Mobile CCTV Unit 1');
  const [enabled, setEnabled] = useState(camera?.enabled !== false);
  const [zoneType, setZoneType] = useState(camera?.zone_type || 'interior');

  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<CameraTestConnectionResult | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleTestConnection = async () => {
    if (!streamUrl.trim()) {
      setTestResult({ status: 'FAILED', error: 'Please enter a valid Stream URL before testing.' });
      return;
    }

    setTesting(true);
    setTestResult(null);
    try {
      const res = await testCameraConnection(streamUrl.trim(), protocol);
      setTestResult(res);
    } catch (err: any) {
      setTestResult({
        status: 'FAILED',
        error: err.message || 'Network error attempting to contact SmartCCTV server.'
      });
    } finally {
      setTesting(false);
    }
  };

  const handlePreset = (type: 'ipwebcam' | 'droidcam' | 'rtsp') => {
    if (type === 'ipwebcam') {
      setStreamUrl('http://192.168.1.25:8080/video');
      setProtocol('mjpeg');
      setName('Android IP Webcam');
    } else if (type === 'droidcam') {
      setStreamUrl('http://192.168.1.25:4747/video');
      setProtocol('mjpeg');
      setName('DroidCam Mobile');
    } else if (type === 'rtsp') {
      setStreamUrl('rtsp://192.168.1.25:8554/live');
      setProtocol('rtsp');
      setName('RTSP Mobile Stream');
    }
    setTestResult(null);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) {
      setSubmitError('Camera Name is required.');
      return;
    }
    if (!streamUrl.trim()) {
      setSubmitError('Stream URL is required.');
      return;
    }

    setSubmitting(true);
    setSubmitError(null);

    try {
      const payload: Partial<Camera> = {
        name: name.trim(),
        stream_url: streamUrl.trim(),
        rtsp_url: streamUrl.trim(),
        protocol,
        location: location.trim() || 'Mobile Unit',
        zone_type: zoneType,
        enabled,
        fps: testResult?.fps || camera?.fps || 25.0,
        map_x: camera?.map_x || 0.5,
        map_y: camera?.map_y || 0.5,
        zones: camera?.zones || {}
      };

      let saved: Camera;
      if (isEdit && camera?.id) {
        payload.id = camera.id;
        saved = await updateCamera(camera.id, payload);
      } else {
        payload.id = `cam_phone_${Math.floor(Date.now() / 1000) % 10000}`;
        saved = await saveCamera(payload);
      }

      onSaved(saved);
      onClose();
    } catch (err: any) {
      setSubmitError(err.message || 'Failed to save camera.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="modal-backdrop" style={{
      position: 'fixed',
      top: 0, left: 0, right: 0, bottom: 0,
      background: 'rgba(5, 7, 10, 0.75)',
      backdropFilter: 'blur(4px)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      zIndex: 1000,
      padding: 16
    }}>
      <div className="modal-card" style={{
        background: '#0d1117',
        border: '1px solid var(--border-subtle, rgba(255,255,255,0.12))',
        borderRadius: 8,
        width: '100%',
        maxWidth: 580,
        maxHeight: '90vh',
        overflowY: 'auto',
        boxShadow: '0 20px 40px rgba(0,0,0,0.6)',
        display: 'flex',
        flexDirection: 'column'
      }}>
        {/* Header */}
        <div style={{
          padding: '16px 20px',
          borderBottom: '1px solid rgba(255,255,255,0.08)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between'
        }}>
          <div>
            <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--text-hi, #fff)', display: 'flex', alignItems: 'center', gap: 8 }}>
              {ICN.camera({ size: 18, style: { color: 'var(--accent, #4C9EFF)' } })}
              {isEdit ? 'Edit Mobile Camera' : 'Add Mobile Phone Camera'}
            </div>
            <div style={{ fontSize: 11, color: 'var(--text-low, #8b949e)', marginTop: 2 }}>
              Stream live video directly into SmartCCTV's real-time detection & risk pipeline
            </div>
          </div>
          <button
            className="btn ghost sm"
            onClick={onClose}
            style={{ padding: 4, minWidth: 28, height: 28 }}
            title="Close"
          >
            {ICN.x({ size: 16 })}
          </button>
        </div>

        {/* Content Form */}
        <form onSubmit={handleSubmit} style={{ padding: '20px' }}>
          {/* Quick Preset Buttons */}
          <div style={{ marginBottom: 16 }}>
            <label style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-mid, #c9d1d9)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
              Quick App Presets
            </label>
            <div style={{ display: 'flex', gap: 8, marginTop: 6 }}>
              <button
                type="button"
                className="btn sm"
                onClick={() => handlePreset('ipwebcam')}
                style={{ fontSize: 11, padding: '4px 10px' }}
              >
                IP Webcam (Android)
              </button>
              <button
                type="button"
                className="btn sm"
                onClick={() => handlePreset('droidcam')}
                style={{ fontSize: 11, padding: '4px 10px' }}
              >
                DroidCam
              </button>
              <button
                type="button"
                className="btn sm"
                onClick={() => handlePreset('rtsp')}
                style={{ fontSize: 11, padding: '4px 10px' }}
              >
                RTSP Stream
              </button>
            </div>
          </div>

          {/* Camera Name */}
          <div style={{ marginBottom: 14 }}>
            <label style={{ display: 'block', fontSize: 12, fontWeight: 600, marginBottom: 5, color: '#e6edf3' }}>
              Camera Name <span style={{ color: 'var(--critical, #f85149)' }}>*</span>
            </label>
            <input
              type="text"
              className="input-field"
              placeholder="e.g. Phone Camera 01"
              value={name}
              onChange={(e) => setName(e.target.value)}
              style={{
                width: '100%',
                padding: '8px 12px',
                background: 'rgba(255,255,255,0.04)',
                border: '1px solid rgba(255,255,255,0.14)',
                borderRadius: 6,
                color: '#fff',
                fontSize: 13
              }}
              required
            />
          </div>

          {/* Stream URL + Protocol Row */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 140px', gap: 10, marginBottom: 14 }}>
            <div>
              <label style={{ display: 'block', fontSize: 12, fontWeight: 600, marginBottom: 5, color: '#e6edf3' }}>
                Stream URL <span style={{ color: 'var(--critical, #f85149)' }}>*</span>
              </label>
              <input
                type="text"
                className="input-field mono"
                placeholder="http://192.168.1.25:8080/video"
                value={streamUrl}
                onChange={(e) => {
                  setStreamUrl(e.target.value);
                  setTestResult(null);
                }}
                style={{
                  width: '100%',
                  padding: '8px 12px',
                  background: 'rgba(255,255,255,0.04)',
                  border: '1px solid rgba(255,255,255,0.14)',
                  borderRadius: 6,
                  color: '#fff',
                  fontSize: 12
                }}
                required
              />
            </div>

            <div>
              <label style={{ display: 'block', fontSize: 12, fontWeight: 600, marginBottom: 5, color: '#e6edf3' }}>
                Protocol
              </label>
              <select
                value={protocol}
                onChange={(e) => {
                  setProtocol(e.target.value as any);
                  setTestResult(null);
                }}
                style={{
                  width: '100%',
                  padding: '8px 10px',
                  background: '#161b22',
                  border: '1px solid rgba(255,255,255,0.14)',
                  borderRadius: 6,
                  color: '#fff',
                  fontSize: 13
                }}
              >
                <option value="mjpeg">MJPEG / HTTP</option>
                <option value="http">HTTP Video</option>
                <option value="rtsp">RTSP</option>
              </select>
            </div>
          </div>

          {/* Test Connection Button & Status Box */}
          <div style={{
            background: 'rgba(255,255,255,0.02)',
            border: '1px solid rgba(255,255,255,0.08)',
            borderRadius: 6,
            padding: 12,
            marginBottom: 16
          }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
              <div style={{ fontSize: 11, color: 'var(--text-low, #8b949e)' }}>
                Probe camera stream and decode initial video frame before registration
              </div>
              <button
                type="button"
                className={`btn sm ${testResult?.status === 'CONNECTED' ? 'safe' : 'secondary'}`}
                onClick={handleTestConnection}
                disabled={testing || !streamUrl.trim()}
                style={{ minWidth: 120, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6 }}
              >
                {testing ? (
                  <>
                    <span className="dot medium" style={{ width: 6, height: 6 }} /> Testing...
                  </>
                ) : (
                  <>
                    {ICN.radio({ size: 13 })} Test Connection
                  </>
                )}
              </button>
            </div>

            {/* Test Connection Result Display */}
            {testResult && (
              <div style={{
                marginTop: 10,
                padding: '8px 12px',
                borderRadius: 4,
                fontSize: 11,
                background: testResult.status === 'CONNECTED' ? 'rgba(46, 160, 67, 0.15)' : 'rgba(248, 81, 73, 0.15)',
                border: `1px solid ${testResult.status === 'CONNECTED' ? 'rgba(46, 160, 67, 0.4)' : 'rgba(248, 81, 73, 0.4)'}`,
                color: testResult.status === 'CONNECTED' ? '#3fb950' : '#f85149'
              }}>
                {testResult.status === 'CONNECTED' ? (
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      {ICN.check({ size: 14 })}
                      <strong>CONNECTED</strong> — Stream decoded successfully
                    </div>
                    <div className="mono" style={{ fontSize: 10, color: '#3fb950' }}>
                      {testResult.width}×{testResult.height} · {testResult.fps} FPS
                    </div>
                  </div>
                ) : (
                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontWeight: 600 }}>
                      {ICN.wifiOff({ size: 14 })} FAILED
                    </div>
                    <div style={{ marginTop: 4, color: '#ff7b72' }}>
                      {testResult.error || 'Connection failed.'}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Location & Zone Type Row */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 14 }}>
            <div>
              <label style={{ display: 'block', fontSize: 12, fontWeight: 600, marginBottom: 5, color: '#e6edf3' }}>
                Location / Area
              </label>
              <input
                type="text"
                className="input-field"
                placeholder="e.g. Mobile Unit 1 / Main Entrance"
                value={location}
                onChange={(e) => setLocation(e.target.value)}
                style={{
                  width: '100%',
                  padding: '8px 12px',
                  background: 'rgba(255,255,255,0.04)',
                  border: '1px solid rgba(255,255,255,0.14)',
                  borderRadius: 6,
                  color: '#fff',
                  fontSize: 13
                }}
              />
            </div>

            <div>
              <label style={{ display: 'block', fontSize: 12, fontWeight: 600, marginBottom: 5, color: '#e6edf3' }}>
                Zone Classification
              </label>
              <select
                value={zoneType}
                onChange={(e) => setZoneType(e.target.value)}
                style={{
                  width: '100%',
                  padding: '8px 10px',
                  background: '#161b22',
                  border: '1px solid rgba(255,255,255,0.14)',
                  borderRadius: 6,
                  color: '#fff',
                  fontSize: 13
                }}
              >
                <option value="interior">Interior / Room</option>
                <option value="perimeter">Perimeter / Gate</option>
                <option value="restricted">Restricted Area</option>
                <option value="high-value">High Value Vault</option>
                <option value="hallway">Corridor / Hallway</option>
              </select>
            </div>
          </div>

          {/* Enabled Checkbox */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
            <input
              type="checkbox"
              id="cam-enabled-toggle"
              checked={enabled}
              onChange={(e) => setEnabled(e.target.checked)}
              style={{ width: 16, height: 16, cursor: 'pointer', accentColor: 'var(--accent, #4C9EFF)' }}
            />
            <label htmlFor="cam-enabled-toggle" style={{ fontSize: 12, color: '#e6edf3', cursor: 'pointer' }}>
              <strong>Enabled</strong> — Ingest frames and run motion, YOLO detection, ByteTrack & risk analysis
            </label>
          </div>

          {/* Security & Network Note */}
          <div style={{
            fontSize: 11,
            color: 'var(--text-low, #8b949e)',
            background: 'rgba(56, 139, 253, 0.08)',
            border: '1px solid rgba(56, 139, 253, 0.2)',
            borderRadius: 6,
            padding: '8px 12px',
            marginBottom: 16
          }}>
            <strong style={{ color: '#58a6ff' }}>Local Network & Security:</strong> Mobile stream is kept on your local Wi-Fi network. For remote monitoring, connect via VPN or secure tunnel (WireGuard / Tailscale) rather than exposing camera ports to the public internet.
          </div>

          {submitError && (
            <div style={{
              padding: '8px 12px',
              borderRadius: 6,
              background: 'rgba(248, 81, 73, 0.15)',
              border: '1px solid rgba(248, 81, 73, 0.4)',
              color: '#f85149',
              fontSize: 12,
              marginBottom: 14
            }}>
              {submitError}
            </div>
          )}

          {/* Footer Actions */}
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 8 }}>
            <button type="button" className="btn ghost" onClick={onClose} disabled={submitting}>
              Cancel
            </button>
            <button type="submit" className="btn primary" disabled={submitting}>
              {submitting ? 'Saving...' : isEdit ? 'Save Changes' : 'Register Camera'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
