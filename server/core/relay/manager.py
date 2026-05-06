"""
ClawOS X - 云端中转 WebSocket 管理器
客户机连接到此模块，保持长连接，接收飞书消息并回传回复
"""
import asyncio
import json
import uuid
import logging
from typing import Optional
from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


class RelayManager:
    """WebSocket 连接管理器"""

    def __init__(self):
        # client_id -> WebSocket connection
        self.connections: dict[str, WebSocket] = {}
        # client_id -> metadata
        self.metadata: dict[str, dict] = {}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, client_id: str, metadata: dict = None):
        """客户机连接注册"""
        await websocket.accept()
        async with self._lock:
            # 踢掉旧连接（同一 client_id 只能有一个活跃连接）
            if client_id in self.connections:
                try:
                    await self.connections[client_id].close(1000, "replaced by new connection")
                except Exception:
                    pass
            self.connections[client_id] = websocket
            self.metadata[client_id] = metadata or {}
        logger.info(f"[Relay] 客户机已连接: {client_id}, 当前连接数: {len(self.connections)}")

    async def disconnect(self, client_id: str):
        """客户机断开"""
        async with self._lock:
            if client_id in self.connections:
                del self.connections[client_id]
            if client_id in self.metadata:
                del self.metadata[client_id]
        logger.info(f"[Relay] 客户机已断开: {client_id}, 当前连接数: {len(self.connections)}")

    async def send_to_client(self, client_id: str, message: dict) -> bool:
        """发送消息给指定客户机"""
        async with self._lock:
            if client_id not in self.connections:
                return False
            try:
                await self.connections[client_id].send_json(message)
                return True
            except Exception as e:
                logger.warning(f"[Relay] 发送消息失败 {client_id}: {e}")
                del self.connections[client_id]
                return False

    async def broadcast(self, message: dict):
        """广播给所有客户机"""
        async with self._lock:
            disconnected = []
            for cid, ws in self.connections.items():
                try:
                    await ws.send_json(message)
                except Exception:
                    disconnected.append(cid)
            for cid in disconnected:
                del self.connections[cid]

    def list_clients(self) -> list[dict]:
        """列出所有已连接客户机"""
        return [
            {"client_id": cid, **meta}
            for cid, meta in self.metadata.items()
            if cid in self.connections
        ]

    @property
    def client_count(self) -> int:
        return len(self.connections)


# 全局单例
relay_manager = RelayManager()
