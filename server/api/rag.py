"""
Tender - RAG 问答 API
"""
from fastapi import APIRouter
from server.core.retriever.retriever import retrieve, build_context
from server.core.generator.llm import get_generator
from server.models import QueryReq, QueryResp, Resp

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
 

@router.post("/query", response_model=QueryResp)
def query(req: QueryReq):
    # 1. 检索相关切片
    retrieved = retrieve(req.question, top_k=req.top_k)
    
    # 2. 构建上下文
    context = build_context(retrieved)
    
    # 3. 生成回答
    generator = get_generator()
    prompt = f"参考文档：\n{context}\n\n用户问题：{req.question}"
    answer = generator.generate(prompt, system=SYSTEM_PROMPT)
    
    # 4. 构建来源
    sources = [{
        "doc_id": r["doc_id"],
        "filename": r["filename"],
        "chunk_index": r["metadata"].get("chunk_index", 0),
        "text": r["text"][:200] + "..." if len(r["text"]) > 200 else r["text"],
        "score": round(r["score"], 4),
    } for r in retrieved]
    
    return QueryResp(answer=answer, sources=sources)
