import asyncio
from fastapi import WebSocket, WebSocketDisconnect
import json
import logging
from typing import List, Dict, Any

logger = logging.getLogger("ws_manager")

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.loop = None

    def set_loop(self, loop):
        self.loop = loop

    async def connect(self, websocket: WebSocket):
        if not self.loop:
            try:
                self.loop = asyncio.get_running_loop()
            except Exception:
                pass
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket client connected. Total clients: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"WebSocket client disconnected. Remaining clients: {len(self.active_connections)}")

    async def broadcast(self, message: Dict[str, Any]):
        if not self.active_connections:
            return
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

    def broadcast_sync(self, message: Dict[str, Any]):
        """Thread-safe synchronous broadcast for background tasks/threads."""
        if not self.active_connections:
            return
        try:
            loop = self.loop
            if loop is None or not loop.is_running():
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    pass
            if loop and loop.is_running():
                asyncio.run_coroutine_threadsafe(self.broadcast(message), loop)
        except Exception as e:
            logger.warning(f"Failed to broadcast synchronously: {e}")

ws_manager = ConnectionManager()
