from fastapi import WebSocket, WebSocketDisconnect
import json
import logging
from typing import List, Dict, Any

logger = logging.getLogger("ws_manager")

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket client connected. Total clients: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"WebSocket client disconnected. Remaining clients: {len(self.active_connections)}")

    async def broadcast(self, message: Dict[str, Any]):
        msg_str = json.dumps(message)
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_text(msg_str)
            except Exception as e:
                logger.warning(f"Error broadcasting to websocket client: {e}")
                disconnected.append(connection)

        for conn in disconnected:
            self.disconnect(conn)

ws_manager = ConnectionManager()
