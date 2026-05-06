"""
ClawOS X - WebSocket relay 端点
客户机通过此端点建立长连接到 relay
"""
import asyncio
import json
import uuid
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from server.core.relay import relay_manager

router = APIRouter(tags=["Relay"])
logger = logging.getLogger(__name__)


@router.websocket("/ws/relay")
async def websocket_relay(
    websocket: WebSocket,
    client_id: str = Query(..., description="客户机唯一ID"),
    machine_name: str = Query("", description="机器名称"),
):
    """
    客户机 WebSocket 连接端点

    连接建立后，客户机保持此连接。
    飞书消息通过 /api/feishu/webhook 接收后，会通过此连接推送给对应客户机。

    客户机发送的消息格式:
      {"type": "ping"}  # 保活
      {"type": "register", "client_id": "...", "machine_name": "..."}  # 注册
      {"type": "reply", "message_id": "...", "text": "..."}  # 回复飞书

    服务端推送的消息格式:
      {"type": "feishu_message", "message_id": "...", "sender": "...", "text": "...", "chat_id": "..."}
      {"type": "ping"}  # 服务端保活探测
    """
    await relay_manager.connect(
        websocket,
        client_id,
        metadata={"machine_name": machine_name}
    )

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")

            if msg_type == "ping":
                await websocket.send_json({"type": "pong"})

            elif msg_type == "register":
                # 客户机重新注册，确认连接
                await websocket.send_json({
                    "type": "registered",
                    "client_id": client_id,
                    "status": "ok"
                })

            elif msg_type == "reply":
                # 客户机处理完飞书消息，回传回复
                # 这个回复由 webhook 处通过同一 client_id 找到连接并发送
                # 这里只是确认收到，reply 本身通过 relay_manager.send_to_client 发回飞书
                logger.info(f"[Relay] 收到客户机回复: {client_id} -> {data.get('text', '')[:50]}")

            else:
                logger.warning(f"[Relay] 未知消息类型: {msg_type}")

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"[Relay] WebSocket 异常: {e}")
    finally:
        await relay_manager.disconnect(client_id)
