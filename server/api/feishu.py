"""
ClawOS X - 飞书集成 API
"""
from fastapi import APIRouter, HTTPException, Header
from server.config import get_settings
from server.core.retriever.retriever import retrieve, build_context
from server.core.generator.llm import get_generator
from server.models import FeishuConfig, Resp

router = APIRouter(prefix="/api/feishu", tags=["飞书"])
settings = get_settings()


@router.get("/config", response_model=FeishuConfig)
def get_feishu_config():
    """获取飞书配置状态"""
    if not settings.FEISHU_APP_ID:
        return FeishuConfig(app_id="", app_name="", status="not_configured")
    return FeishuConfig(
        app_id=settings.FEISHU_APP_ID,
        app_name="ClawOS X Bot",
        status="connected"
    )


@router.post("/webhook")
def feishu_webhook(body: dict, x_lark_signature: str = Header(None)):
    """接收飞书消息"""
    # 验证签名（生产环境需要）
    # if not verify_signature(x_lark_signature, body):
    #     raise HTTPException(status_code=403, detail="签名验证失败")
    
    event = body.get("event", {})
    msg_type = event.get("msg_type", "text")
    content = event.get("content", {})
    sender = event.get("sender", {})
    chat_id = event.get("chat_id", "")
    
    # 处理文本消息
    if msg_type == "text":
        text = content.get("text", "").strip()
        if not text:
            return {"message": "ok"}
        
        # RAG 查询
        retrieved = retrieve(text, top_k=3)
        context = build_context(retrieved)
        
        generator = get_generator()
        prompt = f"参考文档：\n{context}\n\n用户问题：{text}" if context else text
        answer = generator.generate(
            prompt,
            system="你是一个专业的制造业文档助手，基于参考文档回答用户问题。"
        )
        
        # 发送回复
        send_feishu_message(chat_id, answer)
    
    return {"message": "ok"}


def send_feishu_message(chat_id: str, text: str):
    """发送飞书消息"""
    if not settings.FEISHU_BOT_TOKEN:
        return
    
    import httpx
    url = "https://open.feishu.cn/open-apis/im/v1/messages"
    headers = {
        "Authorization": f"Bearer {settings.FEISHU_BOT_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "receive_id": chat_id,
        "msg_type": "text",
        "content": {"text": text}
    }
    httpx.post(url, json=payload, headers=headers, timeout=10)


def get_feishu_access_token():
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
