"""
Tender - RAG 问答 API
"""
import json
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from server.core.retriever.retriever import retrieve, build_context
from server.core.generator.llm import get_generator
from server.models import QueryReq, QueryResp

router = APIRouter(prefix="/api/rag", tags=["RAG问答"])

SYSTEM_PROMPT = """你是一个专业的制造业文档助手，基于提供的参考文档回答用户问题。

回答规则：
1. 只基于参考文档中的信息回答，不要编造
2. 如果文档中没有相关信息，明确说明"根据当前文档无法回答此问题"
3. 回答要清晰、准确，标注信息来源
4. 如果涉及数据，尽量引用原文

输出格式：
回答内容
---
参考来源：[文件名]"""


def _build_sources(retrieved):
    return [{
        "doc_id": r["doc_id"],
        "filename": r["filename"],
        "chunk_index": r["metadata"].get("chunk_index", 0),
        "text": r["text"][:200] + "..." if len(r["text"]) > 200 else r["text"],
        "score": round(r["score"], 4),
    } for r in retrieved]


@router.post("/query")
def query(req: QueryReq):
    retrieved = retrieve(req.question, top_k=req.top_k)
    context = build_context(retrieved)
    sources = _build_sources(retrieved)

    if req.stream:
        return _query_stream(context, req.question, sources)

    generator = get_generator()
    prompt = f"参考文档：\n{context}\n\n用户问题：{req.question}"
    answer = generator.generate(prompt, system=SYSTEM_PROMPT)
    return QueryResp(answer=answer, sources=sources)


def _query_stream(context: str, question: str, sources: list):
    """SSE 流式返回生成结果"""
    generator = get_generator()
    prompt = f"参考文档：\n{context}\n\n用户问题：{question}"

    async def event_stream():
        # 先发来源
        yield f"data: {json.dumps({'type': 'sources', 'content': sources}, ensure_ascii=False)}\n\n"

        # 流式生成
        try:
            for chunk in generator.generate_stream(prompt, system=SYSTEM_PROMPT):
                if chunk:
                    yield f"data: {json.dumps({'type': 'text', 'content': chunk}, ensure_ascii=False)}\n\n"
        except (NotImplementedError, AttributeError):
            # 不支持 stream 的 generator 降级为一次性返回
            answer = generator.generate(prompt, system=SYSTEM_PROMPT)
            yield f"data: {json.dumps({'type': 'text', 'content': answer}, ensure_ascii=False)}\n\n"

        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
