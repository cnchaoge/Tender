"""
ClawOS X - 飞书集成 API（云端中转模式）
手机飞书 → webhook → relay → 客户机WebSocket → ClawOS X处理 → 回复回传 → 飞书
"""
from typing import Optional
import asyncio
import json
import time
import logging
from fastapi import APIRouter, HTTPException, Header, WebSocket
from server.config import get_settings
from server.core.relay import relay_manager
from server.models import FeishuConfig, Resp

router = APIRouter(prefix="/api/feishu", tags=["飞书"])
settings = get_settings()
logger = logging.getLogger(__name__)

# 待处理的飞书消息（message_id -> event data）
pending_messages: dict[str, dict] = {}


def get_feishu_access_token() -> Optional[str]:
    """获取飞书 access_token"""
    if not settings.FEISHU_APP_ID:
        return None
    import httpx
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    resp = httpx.post(url, json={
        "app_id": settings.FEISHU_APP_ID,
        "app_secret": settings.FEISHU_APP_SECRET
    }, timeout=10)
    data = resp.json()
    return data.get("tenant_access_token")


def send_feishu_message(chat_id: str, text: str) -> bool:
    """发送飞书消息"""
    if not settings.FEISHU_APP_ID or not settings.FEISHU_APP_SECRET:
        logger.warning("[Feishu] 未配置飞书应用")
        return False

    token = get_feishu_access_token()
    if not token:
        return False

    import httpx
    url = "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    payload = {
        "receive_id": chat_id,
        "msg_type": "text",
        "content": json.dumps({"text": text})
    }
    try:
        resp = httpx.post(url, json=payload, headers=headers, timeout=10)
        return resp.status_code == 200
    except Exception as e:
        logger.error(f"[Feishu] 发送消息失败: {e}")
        return False


def verify_feishu_signature(signature: str, body: bytes, timestamp: str) -> bool:
    """验证飞书签名"""
    if not settings.FEISHU_APP_SECRET:
        return True  # 未配置时跳过验证
    import hashlib
    import hmac
    import base64
    string_to_sign = timestamp + body.decode("utf-8")
    sign = base64.b64encode(
        hmac.new(
            settings.FEISHU_APP_SECRET.encode("utf-8"),
            string_to_sign.encode("utf-8"),
            hashlib.sha256
        ).digest()
    ).decode("utf-8")
    return sign == signature


@router.get("/config", response_model=FeishuConfig)
def get_feishu_config():
    """获取飞书配置状态"""
    if not settings.FEISHU_APP_ID:
        return FeishuConfig(app_id="", app_name="", status="not_configured")
    return FeishuConfig(
        app_id=settings.FEISHU_APP_ID,
        app_name="ClawOS X Bot",
        status="relay_connected" if relay_manager.client_count > 0 else "waiting_client"
    )


@router.post("/webhook")
async def feishu_webhook(
    body: dict,
    x_lark_signature: str = Header(None),
    x_lark_timestamp: str = Header(None),
):
    """
    接收飞书消息（使用长连接模式）

    流程：
    1. 接收飞书事件
    2. 通过 relay 推送给所有在线客户机
    3. 等待客户机回复（通过 WebSocket 回传）
    4. 将回复发回飞书
    """
    # 签名验证
    # 注意：飞书长连接模式下，签名验证方式与 webhook 模式不同
    # 这里暂时跳过严格签名验证（生产环境建议启用）

    event = body.get("event", {})
    event_type = body.get("event_type", "")

    # 过滤只处理消息事件
    if event_type != "im.message.receive_v1":
        return {"message": "ok"}

    sender = event.get("sender", {})
    chat_id = event.get("chat_id", "")
    message_id = event.get("message_id", "")
    msg_type = event.get("message_type", "text")

    # 获取消息内容
    content_str = event.get("content", "{}")
    try:
        content = json.loads(content_str)
    except Exception:
        content = {}

    text = ""
    if msg_type == "text":
        text = content.get("text", "").strip()
    elif msg_type == "image":
        text = "[图片消息，暂不支持]"

    # 忽略空消息
    if not text:
        return {"message": "ok"}

    logger.info(f"[Feishu] 收到消息 from {sender.get('sender_id', {}).get('open_id', '?')}: {text[:50]}")

    # 构建 relay 消息
    feishu_event = {
        "type": "feishu_message",
        "message_id": message_id,
        "chat_id": chat_id,
        "open_id": sender.get("sender_id", {}).get("open_id", ""),
        "text": text,
        "msg_type": msg_type,
        "timestamp": time.time(),
    }

    # 推送给所有在线客户机
    online_clients = relay_manager.list_clients()
    if not online_clients:
        # 没有客户机在线，立即回复
        logger.warning("[Feishu] 没有客户机在线，无法处理消息")
        asyncio.create_task(send_feishu_message(
            chat_id,
            "抱歉，当前没有客户机在线，请稍后再试。"
        ))
        return {"message": "ok"}

    # 广播给所有客户机（抢答模式：谁先回复用谁的）
    delivered = False
    for client in online_clients:
        ok = await relay_manager.send_to_client(client["client_id"], feishu_event)
        if ok:
            delivered = True
            logger.info(f"[Feishu] 消息已推送给客户机: {client['client_id']}")

    if not delivered:
        asyncio.create_task(send_feishu_message(
            chat_id,
            "抱歉，当前客户机连接异常，请稍后再试。"
        ))

    return {"message": "ok"}


@router.get("/clients")
def list_relay_clients():
    """查看当前在线的客户机"""
    return {
        "count": relay_manager.client_count,
        "clients": relay_manager.list_clients()
    }
