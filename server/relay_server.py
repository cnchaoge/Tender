"""
ClawOS X 轻量级云端 relay 服务
- 接收飞书 webhook 事件
- 通过 WebSocket 广播给所有已连接的客户机
- 接收客户机回复，发回飞书
"""

import asyncio
import hashlib
import hmac
import json
import logging
import time
from datetime import datetime
from typing import Optional

import websockets
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Header, Request
from pydantic import BaseModel
import httpx

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("relay")

app = FastAPI()

# ── 飞书配置 ──────────────────────────────────────────────
FEISHU_APP_ID = "cli_a928f49d39b81cca"
FEISHU_APP_SECRET = "Yil9ZChwNkqC3eeNKwawXbDXFL6udwHw"
FEISHU_API = "https://open.feishu.cn/open-apis"

# ── 内部状态 ──────────────────────────────────────────────
class Client:
    def __init__(self, websocket: WebSocket, client_id: str, machine_name: str = ""):
        self.websocket = websocket
        self.client_id = client_id
        self.machine_name = machine_name
        self.last_pong = time.time()

clients: dict[str, Client] = {}
clients_lock = asyncio.Lock()

# 飞书消息缓冲：message_id → 事件体（等客户机回复）
pending_messages: dict[str, dict] = {}

# ── 飞书 API ──────────────────────────────────────────────
async def get_feishu_token() -> str:
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(
            f"{FEISHU_API}/auth/v3/tenant_access_token/internal",
            json={"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET},
        )
        r.raise_for_status()
        return r.json()["tenant_access_token"]

async def send_feishu_message(open_id: str, text: str, token: str):
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(
            f"{FEISHU_API}/im/v1/messages?receive_id_type=open_id",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "receive_id": open_id,
                "msg_type": "text",
                "content": json.dumps({"text": text}),
            },
        )
        if r.status_code != 200:
            logger.error(f"Feishu send failed: {r.text}")

# ── WebSocket 端点（客户机长连接） ───────────────────────
@app.websocket("/ws/relay")
async def ws_relay(websocket: WebSocket, client_id: str = "", machine_name: str = ""):
    await websocket.accept()
    if not client_id:
        client_id = str(id(websocket))

    async with clients_lock:
        clients[client_id] = Client(websocket, client_id, machine_name)
        logger.info(f"Client connected: {client_id} ({machine_name}), total={len(clients)}")

    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)

            if msg.get("type") == "ping":
                async with clients_lock:
                    if client_id in clients:
                        clients[client_id].last_pong = time.time()
                await websocket.send_text(json.dumps({"type": "pong"}))
            elif msg.get("type") == "feishu_reply":
                # 客户机处理完飞书消息，发回复
                message_id = msg.get("message_id", "")
                reply_text = msg.get("text", "")
                token = await get_feishu_token()
                if message_id in pending_messages:
                    open_id = pending_messages[message_id]["sender"]["open_id"]
                    await send_feishu_message(open_id, reply_text, token)
                    del pending_messages[message_id]
                    logger.info(f"Reply sent for message {message_id}")
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        async with clients_lock:
            if client_id in clients:
                del clients[client_id]
                logger.info(f"Client disconnected: {client_id}, total={len(clients)}")

# ── 飞书 webhook 端点 ───────────────────────────────────
@app.post("/feishu/webhook")
async def feishu_webhook(request: Request, x_feishu_encryption_ticket: Optional[str] = Header(None)):
    body = await request.json()
    logger.info(f"Feishu webhook: {json.dumps(body, ensure_ascii=False)[:200]}")

    event = body.get("event", {})
    event_type = body.get("event_type", "")

    # 过滤心跳
    if event_type == "im.message.receive_v1":
        message = event.get("message", {})
        msg_type = message.get("message_type", "")
        content = message.get("content", "{}")
        sender = event.get("sender", {})
        message_id = message.get("message_id", "")

        # 只处理文本消息，且来自用户（不是机器人）
        if msg_type == "text" and sender.get("sender_type") == "user":
            try:
                content_obj = json.loads(content)
                text = content_obj.get("text", "").strip()
            except:
                text = content

            # 存入 pending_messages
            pending_messages[message_id] = {
                "text": text,
                "sender": sender,
                "chat_id": message.get("chat_id", ""),
                "create_time": message.get("create_time", ""),
            }

            # 广播给所有已连接的客户机
            broadcast_msg = {
                "type": "feishu_message",
                "message_id": message_id,
                "text": text,
                "sender_open_id": sender.get("open_id", ""),
                "sender_nickname": sender.get("sender_nickname", ""),
                "chat_id": message.get("chat_id", ""),
                "timestamp": datetime.now().isoformat(),
            }
            async with clients_lock:
                disconnected = []
                for cid, client in list(clients.items()):
                    try:
                        await client.websocket.send_text(json.dumps(broadcast_msg))
                    except:
                        disconnected.append(cid)
                # 清理断开的客户端
                for cid in disconnected:
                    del clients[cid]

            return {"code": 0, "msg": "ok"}

    return {"code": 0, "msg": "no_action"}

# ── 飞书事件订阅验证 ─────────────────────────────────────
@app.get("/feishu/webhook")
async def feishu_verify(
    challenge: str = "",
    hook_id: str = "",
    timestamp: str = "",
    sign: str = "",
):
    # 飞书第一次配置 webhook 时会发 GET 请求验证
    if challenge:
        return {"challenge": challenge}
    raise HTTPException(400, "invalid verify request")

# ── 管理接口 ─────────────────────────────────────────────
@app.get("/relay/clients")
async def list_clients():
    async with clients_lock:
        return {
            "count": len(clients),
            "clients": [
                {"client_id": c.client_id, "machine_name": c.machine_name}
                for c in clients.values()
            ],
        }

@app.get("/health")
async def health():
    return {"status": "ok", "clients": len(clients), "pending": len(pending_messages)}

# ── 启动 ─────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=18001, log_level="info")
