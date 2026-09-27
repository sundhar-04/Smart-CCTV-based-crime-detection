type WsCallback = (eventData: any) => void;

class WebSocketClient {
  private ws: WebSocket | null = null;
  private listeners: Map<string, Set<WsCallback>> = new Map();
  private reconnectTimer: any = null;

  connect() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1' ? '127.0.0.1:8000' : window.location.host;
    const wsUrl = `${protocol}//${host}/ws`;

    try {
      this.ws = new WebSocket(wsUrl);

      this.ws.onopen = () => {
        console.log('[WS] Connected to SmartCCTV backend WebSocket');
        if (this.reconnectTimer) {
          clearTimeout(this.reconnectTimer);
          this.reconnectTimer = null;
        }
      };

      this.ws.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);
          const eventName = payload.event;
          if (eventName && this.listeners.has(eventName)) {
            this.listeners.get(eventName)!.forEach((cb) => cb(payload.data));
          }
          if (this.listeners.has('*')) {
            this.listeners.get('*')!.forEach((cb) => cb(payload));
          }
        } catch (err) {
          console.warn('[WS] Non-JSON message:', event.data);
        }
      };

      this.ws.onclose = () => {
        console.warn('[WS] Connection lost. Reconnecting in 3s...');
        this.scheduleReconnect();
      };

      this.ws.onerror = (err) => {
        console.error('[WS] Error:', err);
      };
    } catch (e) {
      this.scheduleReconnect();
    }
  }

  private scheduleReconnect() {
    if (!this.reconnectTimer) {
      this.reconnectTimer = setTimeout(() => this.connect(), 3000);
    }
  }

  subscribe(eventName: string, callback: WsCallback) {
    if (!this.listeners.has(eventName)) {
      this.listeners.set(eventName, new Set());
    }
    this.listeners.get(eventName)!.add(callback);
    return () => {
      this.listeners.get(eventName)?.delete(callback);
    };
  }
}

export const wsClient = new WebSocketClient();
