import React, { useState, useEffect } from 'react';
import { getAllSettings, updateSettingCategory, listUsers, createUser, updateUser, deleteUser, User } from '../api/client';
import { ICN } from '../components/Icon';

export function SettingsPage() {
  const [activeTab, setActiveTab] = useState<string>('detection');
  const [settings, setSettings] = useState<Record<string, any>>({});
  const [saving, setSaving] = useState(false);
  const [savedMsg, setSavedMsg] = useState(false);
  const [users, setUsers] = useState<User[]>([]);
  const [showAddUser, setShowAddUser] = useState(false);
  const [newUser, setNewUser] = useState({ username: '', display_name: '', role: 'Operator', email: '' });

  useEffect(() => {
    getAllSettings().then(setSettings).catch(console.error);
    listUsers().then(setUsers).catch(console.error);
  }, []);

  const handleSave = async (category: string) => {
    setSaving(true);
    try {
      await updateSettingCategory(category, settings[category] || {});
      setSavedMsg(true);
      setTimeout(() => setSavedMsg(false), 2000);
    } catch (err: any) {
      alert(`Save failed: ${err.message}`);
    } finally {
      setSaving(false);
    }
  };

  const updateField = (category: string, key: string, val: any) => {
    setSettings((prev) => ({
      ...prev,
      [category]: {
        ...(prev[category] || {}),
        [key]: val
      }
    }));
  };

  const handleCreateUser = async () => {
    try {
      await createUser(newUser);
      const updated = await listUsers();
      setUsers(updated);
      setShowAddUser(false);
      setNewUser({ username: '', display_name: '', role: 'Operator', email: '' });
    } catch (err: any) {
      alert(`Failed: ${err.message}`);
    }
  };

  const handleDeactivateUser = async (userId: string) => {
    try {
      await deleteUser(userId);
      const updated = await listUsers();
      setUsers(updated);
    } catch (err: any) {
      alert(`Failed: ${err.message}`);
    }
  };

  const tabs = [
    { key: 'detection', label: 'Detection', icon: ICN.target },
    { key: 'risk', label: 'Risk Engine', icon: ICN.alert },
    { key: 'notifications', label: 'Notifications', icon: ICN.bell },
    { key: 'privacy', label: 'Privacy', icon: ICN.shield },
    { key: 'retention', label: 'Storage', icon: ICN.hardDrive },
    { key: 'system', label: 'System', icon: ICN.cpu },
    { key: 'users', label: 'Users & RBAC', icon: ICN.users }
  ];

  const currentSettings = settings[activeTab] || {};

  const SettingRow = ({ label, children }: { label: string; children: React.ReactNode }) => (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 0', borderBottom: '1px solid var(--border-soft)' }}>
      <span style={{ fontSize: 13, fontWeight: 600 }}>{label}</span>
      {children}
    </div>
  );

  const SwitchRow = ({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) => (
    <SettingRow label={label}>
      <label className="switch">
        <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
        <span className="switch-track" />
      </label>
    </SettingRow>
  );

  return (
    <div className="fade-in">
      <div className="page-header">
        <div>
          <div className="page-title">Platform Settings</div>
          <div className="page-sub">Configure AI detection, risk scoring, notifications & user access controls</div>
        </div>
        <div className="page-actions">
          {savedMsg && <span style={{ color: 'var(--safe)', fontSize: 12, fontWeight: 600 }}>{ICN.check({ size: 14 })} Saved</span>}
          {activeTab !== 'users' && (
            <button className="btn primary" onClick={() => handleSave(activeTab)} disabled={saving}>
              {ICN.check({ size: 14 })} {saving ? 'Saving...' : 'Save Settings'}
            </button>
          )}
        </div>
      </div>

      <div className="tabs-row" style={{ marginBottom: 16 }}>
        {tabs.map((t) => (
          <div
            key={t.key}
            className={`tab-btn ${activeTab === t.key ? 'active' : ''}`}
            onClick={() => setActiveTab(t.key)}
          >
            {t.icon({ size: 13 })} {t.label}
          </div>
        ))}
      </div>

      <div className="panel">
        <div className="panel-body" style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
          {activeTab === 'detection' && (
            <>
              <SettingRow label="YOLOv8 Model Variant">
                <select className="role-select" style={{ width: 280 }}
                  value={currentSettings.detector_model || 'yolov8n'}
                  onChange={(e) => updateField('detection', 'detector_model', e.target.value)}>
                  <option value="yolov8n">yolov8n (Nano — Fast)</option>
                  <option value="yolov8s">yolov8s (Small — Balanced)</option>
                  <option value="yolov8m">yolov8m (Medium — Accurate)</option>
                </select>
              </SettingRow>
              <SettingRow label={`Confidence Threshold (${currentSettings.confidence_threshold || 0.25})`}>
                <input type="range" min="0.1" max="0.9" step="0.05" style={{ width: 200 }}
                  value={currentSettings.confidence_threshold || 0.25}
                  onChange={(e) => updateField('detection', 'confidence_threshold', parseFloat(e.target.value))} />
              </SettingRow>
              <SettingRow label={`IOU Threshold (${currentSettings.iou_threshold || 0.45})`}>
                <input type="range" min="0.1" max="0.9" step="0.05" style={{ width: 200 }}
                  value={currentSettings.iou_threshold || 0.45}
                  onChange={(e) => updateField('detection', 'iou_threshold', parseFloat(e.target.value))} />
              </SettingRow>
              <SettingRow label="Max Detections Per Frame">
                <input type="number" className="field" style={{ width: 100 }}
                  value={currentSettings.max_detections || 30}
                  onChange={(e) => updateField('detection', 'max_detections', parseInt(e.target.value))} />
              </SettingRow>
              <SwitchRow label="Enable Motion Gating" checked={currentSettings.enable_motion_gating ?? true}
                onChange={(v) => updateField('detection', 'enable_motion_gating', v)} />
            </>
          )}

          {activeTab === 'risk' && (
            <>
              <SettingRow label="Loitering Threshold (s)">
                <input type="number" className="field" style={{ width: 120 }}
                  value={currentSettings.loitering_threshold_s || 15}
                  onChange={(e) => updateField('risk', 'loitering_threshold_s', parseInt(e.target.value))} />
              </SettingRow>
              <SettingRow label="Restricted Zone Weight">
                <input type="number" className="field" style={{ width: 120 }}
                  value={currentSettings.restricted_zone_weight || 40}
                  onChange={(e) => updateField('risk', 'restricted_zone_weight', parseInt(e.target.value))} />
              </SettingRow>
              <SettingRow label="Critical Alert Threshold">
                <input type="number" className="field" style={{ width: 120 }}
                  value={currentSettings.critical_alert_threshold || 80}
                  onChange={(e) => updateField('risk', 'critical_alert_threshold', parseInt(e.target.value))} />
              </SettingRow>
              <SettingRow label="High Alert Threshold">
                <input type="number" className="field" style={{ width: 120 }}
                  value={currentSettings.high_alert_threshold || 60}
                  onChange={(e) => updateField('risk', 'high_alert_threshold', parseInt(e.target.value))} />
              </SettingRow>
            </>
          )}

          {activeTab === 'notifications' && (
            <>
              <SwitchRow label="Browser Toast Notifications" checked={currentSettings.enable_browser_toasts ?? true}
                onChange={(v) => updateField('notifications', 'enable_browser_toasts', v)} />
              <SwitchRow label="Sound Alerts" checked={currentSettings.enable_sound_alerts ?? true}
                onChange={(v) => updateField('notifications', 'enable_sound_alerts', v)} />
              <SwitchRow label="Email Alerts" checked={currentSettings.email_alerts_enabled ?? false}
                onChange={(v) => updateField('notifications', 'email_alerts_enabled', v)} />
              <SettingRow label="Webhook URL">
                <input className="field" style={{ width: 300 }}
                  value={currentSettings.webhook_url || ''}
                  onChange={(e) => updateField('notifications', 'webhook_url', e.target.value)} />
              </SettingRow>
            </>
          )}

          {activeTab === 'privacy' && (
            <>
              <SwitchRow label="Face Blur in Exported Clips" checked={currentSettings.face_blur_enabled ?? true}
                onChange={(v) => updateField('privacy', 'face_blur_enabled', v)} />
              <SwitchRow label="License Plate Masking" checked={currentSettings.license_plate_masking ?? true}
                onChange={(v) => updateField('privacy', 'license_plate_masking', v)} />
              <SwitchRow label="Data Anonymization" checked={currentSettings.data_anonymization ?? false}
                onChange={(v) => updateField('privacy', 'data_anonymization', v)} />
            </>
          )}

          {activeTab === 'retention' && (
            <>
              <SettingRow label="Evidence Retention (Days)">
                <input type="number" className="field" style={{ width: 120 }}
                  value={currentSettings.evidence_retention_days || 90}
                  onChange={(e) => updateField('retention', 'evidence_retention_days', parseInt(e.target.value))} />
              </SettingRow>
              <SettingRow label="Auto-Purge Dismissed Alerts (Days)">
                <input type="number" className="field" style={{ width: 120 }}
                  value={currentSettings.auto_purge_dismissed_days || 30}
                  onChange={(e) => updateField('retention', 'auto_purge_dismissed_days', parseInt(e.target.value))} />
              </SettingRow>
              <SettingRow label="Max Storage (GB)">
                <input type="number" className="field" style={{ width: 120 }}
                  value={currentSettings.max_storage_gb || 500}
                  onChange={(e) => updateField('retention', 'max_storage_gb', parseInt(e.target.value))} />
              </SettingRow>
            </>
          )}

          {activeTab === 'system' && (
            <>
              <SettingRow label="Max Worker Threads">
                <input type="number" className="field" style={{ width: 120 }}
                  value={currentSettings.max_worker_threads || 4}
                  onChange={(e) => updateField('system', 'max_worker_threads', parseInt(e.target.value))} />
              </SettingRow>
              <SettingRow label="Log Level">
                <select className="role-select" value={currentSettings.log_level || 'INFO'}
                  onChange={(e) => updateField('system', 'log_level', e.target.value)}>
                  <option value="DEBUG">DEBUG</option>
                  <option value="INFO">INFO</option>
                  <option value="WARNING">WARNING</option>
                  <option value="ERROR">ERROR</option>
                </select>
              </SettingRow>
              <SwitchRow label="GPU Acceleration" checked={currentSettings.gpu_acceleration ?? true}
                onChange={(v) => updateField('system', 'gpu_acceleration', v)} />
            </>
          )}

          {activeTab === 'users' && (
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                <span style={{ fontSize: 12, color: 'var(--text-mid)' }}>{users.length} registered user accounts</span>
                <button className="btn sm primary" onClick={() => setShowAddUser(!showAddUser)}>
                  {showAddUser ? ICN.x({ size: 12 }) : ICN.users({ size: 12 })} {showAddUser ? 'Cancel' : 'Add User'}
                </button>
              </div>

              {showAddUser && (
                <div className="decision-panel" style={{ marginBottom: 12 }}>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr auto', gap: 8, alignItems: 'end' }}>
                    <div>
                      <div style={{ fontSize: 10, color: 'var(--text-low)', marginBottom: 4 }}>Username</div>
                      <input className="field" style={{ width: '100%' }} value={newUser.username}
                        onChange={e => setNewUser({...newUser, username: e.target.value})} placeholder="username" />
                    </div>
                    <div>
                      <div style={{ fontSize: 10, color: 'var(--text-low)', marginBottom: 4 }}>Display Name</div>
                      <input className="field" style={{ width: '100%' }} value={newUser.display_name}
                        onChange={e => setNewUser({...newUser, display_name: e.target.value})} placeholder="Full Name" />
                    </div>
                    <div>
                      <div style={{ fontSize: 10, color: 'var(--text-low)', marginBottom: 4 }}>Role</div>
                      <select className="role-select" style={{ width: '100%' }} value={newUser.role}
                        onChange={e => setNewUser({...newUser, role: e.target.value})}>
                        <option>Admin</option><option>Operator</option><option>Auditor</option>
                      </select>
                    </div>
                    <div>
                      <div style={{ fontSize: 10, color: 'var(--text-low)', marginBottom: 4 }}>Email</div>
                      <input className="field" style={{ width: '100%' }} value={newUser.email}
                        onChange={e => setNewUser({...newUser, email: e.target.value})} placeholder="email@example.com" />
                    </div>
                    <button className="btn primary" onClick={handleCreateUser}>{ICN.check({ size: 12 })} Create</button>
                  </div>
                </div>
              )}

              <table className="data-table">
                <thead>
                  <tr>
                    <th>Username</th>
                    <th>Display Name</th>
                    <th>Role</th>
                    <th>Email</th>
                    <th>Status</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map(u => (
                    <tr key={u.id}>
                      <td className="mono" style={{ fontWeight: 600, fontSize: 12 }}>{u.username}</td>
                      <td style={{ fontWeight: 600 }}>{u.display_name}</td>
                      <td><span className="badge info">{u.role}</span></td>
                      <td style={{ color: 'var(--text-mid)', fontSize: 12 }}>{u.email}</td>
                      <td><span className={`badge ${u.active ? 'safe' : 'neutral'}`}>{u.active ? 'Active' : 'Inactive'}</span></td>
                      <td>
                        {u.active && (
                          <button className="btn sm danger" onClick={() => handleDeactivateUser(u.id)}>
                            {ICN.x({ size: 11 })} Deactivate
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
