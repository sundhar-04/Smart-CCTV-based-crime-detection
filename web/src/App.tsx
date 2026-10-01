import React, { useState, useEffect } from 'react';
import { ICN } from './components/Icon';
import { ToastStack, ToastItem } from './components/ToastStack';
import { CommandPalette } from './components/CommandPalette';
import { NotificationDrawer } from './components/NotificationDrawer';
import { IncidentInvestigationModal } from './modals/IncidentInvestigationModal';
import { Alert, listCameras } from './api/client';
import { wsClient } from './ws/client';

function fmtTime(d: Date) {
  return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
}

// Page imports
import { CommandCenterPage } from './pages/CommandCenterPage';
import { VideoAnalysisPage } from './pages/VideoAnalysisPage';
import { IncidentsPage } from './pages/IncidentsPage';
import { AlertsPage } from './pages/AlertsPage';
import { CameraMapPage } from './pages/CameraMapPage';
import { CameraGridPage } from './pages/CameraGridPage';
import { IdentityTopologyPage } from './pages/IdentityTopologyPage';
import { HistoryPage } from './pages/HistoryPage';
import { AnalyticsPage } from './pages/AnalyticsPage';
import { IntegrityAuditPage } from './pages/IntegrityAuditPage';
import { SystemHealthPage } from './pages/SystemHealthPage';
import { SettingsPage } from './pages/SettingsPage';

const NAV_GROUPS = [
  {
    label: 'Operations',
    items: [
      { key: 'command', label: 'Command Center', icon: ICN.grid },
      { key: 'analysis', label: 'Video Analysis', icon: ICN.film },
      { key: 'incidents', label: 'Incidents', icon: ICN.alert },
      { key: 'alerts', label: 'Alert Center', icon: ICN.bell }
    ]
  },
  {
    label: 'Surveillance',
    items: [
      { key: 'map', label: 'Camera Map', icon: ICN.map },
      { key: 'gridview', label: 'Camera Grid', icon: ICN.layers },
      { key: 'identity', label: 'Identity & Topology', icon: ICN.link }
    ]
  },
  {
    label: 'Reporting',
    items: [
      { key: 'history', label: 'Incident History', icon: ICN.history },
      { key: 'analytics', label: 'Analytics', icon: ICN.chart },
      { key: 'integrity', label: 'Integrity & Audit', icon: ICN.shield }
    ]
  },
  {
    label: 'Administration',
    items: [
      { key: 'health', label: 'System Health', icon: ICN.cpu },
      { key: 'settings', label: 'Settings', icon: ICN.settings }
    ]
  }
];

export function App() {
  const [page, setPage] = useState<string>('command');
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [role, setRole] = useState<'Admin' | 'Operator' | 'Auditor'>('Admin');
  const [cmdOpen, setCmdOpen] = useState(false);
  const [notifOpen, setNotifOpen] = useState(false);
  const [activeModalAlert, setActiveModalAlert] = useState<Alert | null>(null);
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const [clock, setClock] = useState(new Date());
  const [offlineCams, setOfflineCams] = useState(0);
  const [notifications, setNotifications] = useState<any[]>([
    { id: '1', title: 'SmartCCTV Backend Online', sub: 'FastAPI connected with SQLite DB & YOLOv8 engine', kind: 'system', timestamp: Date.now() }
  ]);

  useEffect(() => {
    wsClient.connect();
    // Live clock
    const clockTimer = setInterval(() => setClock(new Date()), 1000);
    // Camera status polling
    listCameras().then(cams => setOfflineCams(cams.filter(c => c.status === 'offline').length)).catch(() => {});

    // Keydown shortcut for Cmd+K / Ctrl+K
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setCmdOpen((prev) => !prev);
      }
    };
    window.addEventListener('keydown', handleKeyDown);

    const recentAlertsMap: { [key: string]: number } = {};
    const handleNewAlert = (eventData: any) => {
      const alertItem = eventData.data || eventData;
      const suspectId = alertItem.entity || alertItem.id || 'general';
      const now = Date.now();
      // Suppress repeat popup toasts & notifications for the same suspect across all cameras (120s cooldown)
      if (recentAlertsMap[suspectId] && now - recentAlertsMap[suspectId] < 120000) {
        return;
      }
      recentAlertsMap[suspectId] = now;

      const primaryReason = alertItem.reasons?.[0] || alertItem.types?.[0] || 'Suspicious Action Detected';
      const newToast: ToastItem = {
        id: `toast-${Date.now()}-${Math.random()}`,
        title: `🚨 CRIME ALERT: [${suspectId}] at ${alertItem.camera_name || 'Camera'}`,
        sub: `${primaryReason} (Risk: ${Math.round(alertItem.risk_score || 0)})`,
        risk: alertItem.risk_level?.toLowerCase() || 'critical',
        timestamp: Date.now()
      };
      setToasts((prev) => [newToast, ...prev.slice(0, 3)]);
      setNotifications((prev) => [
        {
          id: alertItem.id,
          title: `🚨 ${alertItem.risk_level || 'CRITICAL'} — [${suspectId}] at ${alertItem.camera_name || 'Camera'}`,
          sub: primaryReason,
          kind: 'alert',
          risk: alertItem.risk_level?.toLowerCase() || 'critical',
          timestamp: Date.now()
        },
        ...prev
      ]);
    };

    const unsubNewAlert = wsClient.subscribe('new_alert', handleNewAlert);

    const unsubAlert = wsClient.subscribe('alert.updated', (eventData: any) => {
      const alertItem = eventData.data || eventData;
      setNotifications((prev) => [
        {
          id: alertItem.id,
          title: `Alert ${alertItem.id} — ${alertItem.status}`,
          sub: alertItem.reasons?.[0] || 'Updated by operator',
          kind: 'alert',
          risk: alertItem.risk_level?.toLowerCase() || 'info',
          timestamp: Date.now()
        },
        ...prev
      ]);
    });

    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      unsubNewAlert();
      unsubAlert();
      clearInterval(clockTimer);
    };
  }, []);

  const renderPage = () => {
    switch (page) {
      case 'command':
        return <CommandCenterPage setPage={setPage} onOpenIncident={(al) => setActiveModalAlert(al)} />;
      case 'analysis':
        return <VideoAnalysisPage onOpenIncident={(al) => setActiveModalAlert(al)} />;
      case 'incidents':
        return <IncidentsPage onOpenIncident={(al) => setActiveModalAlert(al)} />;
      case 'alerts':
        return <AlertsPage onOpenIncident={(al) => setActiveModalAlert(al)} />;
      case 'map':
        return <CameraMapPage />;
      case 'gridview':
        return <CameraGridPage />;
      case 'identity':
        return <IdentityTopologyPage />;
      case 'history':
        return <HistoryPage onOpenIncident={(al) => setActiveModalAlert(al)} />;
      case 'analytics':
        return <AnalyticsPage />;
      case 'integrity':
        return <IntegrityAuditPage />;
      case 'health':
        return <SystemHealthPage />;
      case 'settings':
        return <SettingsPage />;
      default:
        return <CommandCenterPage setPage={setPage} onOpenIncident={(al) => setActiveModalAlert(al)} />;
    }
  };

  return (
    <div className="app-shell">
      {/* Sidebar */}
      <div className={`sidebar ${sidebarCollapsed ? 'collapsed' : ''}`}>
        <div className="sidebar-brand">
          <div className="brand-mark">{ICN.shield({ size: 15, style: { color: '#051220' } })}</div>
          {!sidebarCollapsed && (
            <div style={{ minWidth: 0 }}>
              <div className="brand-name">Meridian</div>
              <div className="brand-sub">Surveillance Operations</div>
            </div>
          )}
        </div>

        <div className="nav-scroll scroll-thin">
          {NAV_GROUPS.map((group) => (
            <div key={group.label}>
              {!sidebarCollapsed && <div className="nav-section-label">{group.label}</div>}
              {group.items.map((item) => (
                <div
                  key={item.key}
                  className={`nav-item ${page === item.key ? 'active' : ''}`}
                  onClick={() => setPage(item.key)}
                  title={item.label}
                >
                  {item.icon({ size: 16 })}
                  {!sidebarCollapsed && <span className="nav-item-label">{item.label}</span>}
                </div>
              ))}
            </div>
          ))}
        </div>

        <div className="sidebar-footer">
          <div className="sys-status-row">
            <div className="pulse-dot" />
            {!sidebarCollapsed && (
              <div style={{ minWidth: 0 }}>
                <div style={{ fontSize: 11, fontWeight: 600 }}>All Systems Nominal</div>
                <div style={{ fontSize: 10, color: 'var(--text-low)' }} className="mono">Uptime 99.2%</div>
              </div>
            )}
          </div>
          <div className="nav-item" onClick={() => setSidebarCollapsed(!sidebarCollapsed)} style={{ marginTop: 2 }}>
            {ICN.menu({ size: 15 })}
            {!sidebarCollapsed && <span className="nav-item-label">Collapse</span>}
          </div>
        </div>
      </div>

      {/* Main Column */}
      <div className="main-col">
        {/* Topbar */}
        <div className="topbar">
          <div className="search-bar" onClick={() => setCmdOpen(true)}>
            {ICN.search({ size: 14 })}
            <span style={{ fontSize: 12 }}>Search incidents, cameras, locations...</span>
            <span className="kbd">Ctrl+K</span>
          </div>

          <div className="topbar-spacer" />

          <div className="mode-chip">
            <span className="pulse-dot" style={{ background: 'var(--safe)' }} />
            OPERATIONAL
          </div>

          <select
            className="role-select"
            value={role}
            onChange={(e: any) => setRole(e.target.value)}
            title="Demo: switch role to preview RBAC"
          >
            <option value="Admin">Admin</option>
            <option value="Operator">Operator</option>
            <option value="Auditor">Auditor</option>
          </select>

          <div className="mono" style={{ fontSize: 12, color: 'var(--text-mid)', minWidth: 72, textAlign: 'right' }}>
            {fmtTime(clock)}
          </div>

          <button className="icon-btn" onClick={() => setNotifOpen(true)} title="Notifications">
            {ICN.bell({ size: 16 })}
            {notifications.length > 0 && <span className="notif-dot" />}
          </button>

          <div className="avatar" title={`Signed in as ${role}`}>{role[0]}{role[1]}</div>
        </div>

        {/* System Banner */}
        {offlineCams > 0 && (
          <div className="banner warn">
            {ICN.alert({ size: 14 })}
            <span>{offlineCams} camera{offlineCams > 1 ? 's' : ''} offline - coverage gap detected.</span>
          </div>
        )}

        {/* Page Content */}
        <div className="page-scroll">{renderPage()}</div>
      </div>

      {/* Overlays & Modals */}
      {cmdOpen && (
        <CommandPalette
          onClose={() => setCmdOpen(false)}
          onNavigate={(p) => setPage(p)}
        />
      )}

      {notifOpen && (
        <NotificationDrawer
          onClose={() => setNotifOpen(false)}
          notifications={notifications}
        />
      )}

      {activeModalAlert && (
        <IncidentInvestigationModal
          alert={activeModalAlert}
          onClose={() => setActiveModalAlert(null)}
          onDecided={() => {
            // refresh trigger if needed
          }}
        />
      )}

      <ToastStack toasts={toasts} onDismiss={(id) => setToasts((prev) => prev.filter((t) => t.id !== id))} />
    </div>
  );
}
