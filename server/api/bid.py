"""标书 HTTP 适配层。

URL、请求体和响应形状保持不变。解析、规划、生成、版本、模板、推荐、
废标和查重的规则在 server.domain。本文件做鉴权、查询参数和转发。
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from server.config import GENERATED_DIR
from server.deps import get_current_user
from server.domain.generation.outline import plan_bid as plan_outline
from server.domain.generation.parse import parse_bid_file as parse_tender_file
from server.domain.generation.run import generate_bid as run_generate_bid
from server.domain.generation.run import iter_generate_events
from server.domain.generation.templates import (
    create_template as create_template_row,
    delete_template as delete_template_row,
    get_template as get_template_row,
    list_templates as list_template_rows,
    update_template as update_template_row,
)
from server.domain.generation.versions import (
    compare_bid_versions as compare_version_rows,
    get_bid_version as get_version_row,
    list_bid_versions as list_version_rows,
    restore_bid_version as restore_version_row,
)
from server.domain.retrieval.analyze import (
    analyze_old_bid as analyze_old_document,
    get_analyzed_sections as load_analyzed_sections,
)
from server.domain.retrieval.recommend import (
    _PREVIEW_DEFAULT_K,
    _PREVIEW_MAX_K,
    recommend_sections,
)
from server.domain.review.match import match_check as match_materials
from server.domain.review.plagiarism import check_plagiarism as run_plagiarism_check
from server.domain.review.violation import (
    check_violations as run_violation_check,
    list_disqualify_rules as load_disqualify_rules,
    list_violation_cases as load_violation_cases,
)
from server.models import (
    BidGenerateReq,
    BidMatchCheckReq,
    BidParseReq,
    BidParseResp,
    BidPlanReq,
    BidPlanResp,
    BidTemplateCreateReq,
    BidTemplateUpdateReq,
)

router = APIRouter(prefix="/api/bid", tags=["标书生成"], dependencies=[Depends(get_current_user)])


class RecommendPreviewReq(BaseModel):
    """当前招标解析结果，用来给某一份历史素材排序。"""
    q: Optional[str] = None
    parse_result: Optional[dict] = None
    chapter: Optional[dict] = None
    top_k: int = _PREVIEW_DEFAULT_K


class ViolationCheckReq(BaseModel):
    parse_result: Optional[dict] = None        # 招标文件解析结果
    bid_content: Optional[str] = None          # 标书正文（generate 阶段检测）
    raw_text: Optional[str] = None             # 招标文件原文（parse 阶段检测）
    check_stage: Optional[str] = "auto"       # auto | parse | generate | review


class ViolationCheckResp(BaseModel):
    passed: bool
    violations: List[dict]
    warnings: List[dict]
    summary: dict


class PlagiarismCheckReq(BaseModel):
    bid_content: str                    # 待检测的标书正文（Markdown）
    exclude_doc_ids: Optional[List[int]] = None   # 排除的文档ID


class PlagiarismCheckResp(BaseModel):
    passed: bool
    overall_score: float
    total_sections: int
    high_risk_sections: int
    sections: List[dict]
    summary: dict


@router.post("/parse", response_model=BidParseResp)
def parse_bid_file(req: BidParseReq):
    """解析招标文件，提取关键信息"""
    return parse_tender_file(req)


@router.post("/plan", response_model=BidPlanResp)
def plan_bid(req: BidPlanReq):
    """生成标书目录大纲（规划阶段）"""
    return plan_outline(req)


@router.post("/generate", response_model=dict)
def generate_bid(req: BidGenerateReq):
    """根据招标文件生成标书（带 AI 质检，非流式）。正文生成走 BidDraftPipeline。"""
    return run_generate_bid(req)


@router.post("/generate/stream")
async def generate_bid_stream(req: BidGenerateReq):
    """SSE 流式生成标书。组 prompt、调用模型和质检重写与非流式接口共用 BidDraftPipeline。"""
    return StreamingResponse(
        iter_generate_events(req),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/download/{filename}")
def download_bid(filename: str):
    path = GENERATED_DIR / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(
        str(path),
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


@router.get("/recommend/{doc_id}/preview")
def recommend_preview(
    doc_id: int,
    q: Optional[str] = None,
    project_name: Optional[str] = None,
    deadline: Optional[str] = None,
    requirements: Optional[List[str]] = Query(default=None),
    qualification: Optional[List[str]] = Query(default=None),
    chapter_name: Optional[str] = None,
    chapter_description: Optional[str] = None,
    top_k: int = Query(default=_PREVIEW_DEFAULT_K, ge=1, le=_PREVIEW_MAX_K),
):
    """按当前招标内容，返回该素材中最相似的章节。"""
    parse_result = {
        "project_name": project_name or "",
        "deadline": deadline or "",
        "requirements": requirements or [],
        "qualification": qualification or [],
    }
    chapter = None
    if chapter_name or chapter_description:
        chapter = {
            "name": chapter_name or "",
            "description": chapter_description or "",
        }
    return recommend_sections(
        doc_id,
        q=q,
        parse_result=parse_result,
        chapter=chapter,
        top_k=top_k,
    )


@router.post("/recommend/{doc_id}/preview")
def recommend_preview_post(doc_id: int, req: RecommendPreviewReq):
    """同预览接口，请求体携带完整的招标解析结果。"""
    return recommend_sections(
        doc_id,
        q=req.q,
        parse_result=req.parse_result,
        chapter=req.chapter,
        top_k=req.top_k,
    )


@router.post("/analyze-old/{doc_id}")
def analyze_old_bid(doc_id: int):
    """拆解历史投标标书为结构化章节并存入向量库"""
    return analyze_old_document(doc_id)


@router.get("/analyze-old/{doc_id}/sections")
def get_analyzed_sections(doc_id: int):
    """查看历史标书拆解结果"""
    return load_analyzed_sections(doc_id)


@router.post("/match_check")
def match_check(req: BidMatchCheckReq):
    """
    招标文件与素材的匹配度检测。
    对每个选中素材，用 parse_result 关键字段（项目名称、资格要求、评分标准）
    构造检索 query，查对应素材的 chunks，计算平均 relevance score。
    """
    return match_materials(req)


@router.get("/versions")
def list_bid_versions(project_name: Optional[str] = None):
    """获取标书历史版本列表（按时间倒序）"""
    return list_version_rows(project_name)


@router.get("/versions/{version_id}")
def get_bid_version(version_id: int):
    """获取指定版本详情"""
    return get_version_row(version_id)


@router.get("/versions/compare")
def compare_bid_versions(from_id: int, to_id: int):
    """对比两个版本的差异（简单行对比）"""
    return compare_version_rows(from_id, to_id)


@router.post("/versions/{version_id}/restore")
def restore_bid_version(version_id: int):
    """恢复指定版本：返回该版本的解析结果和素材ID，供前端重新生成"""
    return restore_version_row(version_id)


@router.get("/templates")
def list_templates(category: Optional[str] = None):
    """获取标书模板列表，可按分类筛选"""
    return list_template_rows(category)


@router.get("/templates/{template_id}")
def get_template(template_id: int):
    """获取单个模板详情"""
    return get_template_row(template_id)


@router.post("/templates")
def create_template(req: BidTemplateCreateReq):
    """创建自定义模板"""
    return create_template_row(req)


@router.put("/templates/{template_id}")
def update_template(template_id: int, req: BidTemplateUpdateReq):
    """更新自定义模板"""
    return update_template_row(template_id, req)


@router.delete("/templates/{template_id}")
def delete_template(template_id: int):
    """删除自定义模板"""
    return delete_template_row(template_id)


@router.post("/violation_check", response_model=ViolationCheckResp)
def check_violations(req: ViolationCheckReq):
    """
    废标项检查接口

    - check_stage=parse：检测招标文件本身的合规性（是否有废标条件）
    - check_stage=generate：检测生成的标书正文是否满足招标文件要求
    - check_stage=review：合并两阶段检测
    """
    return run_violation_check(
        req.parse_result,
        req.bid_content,
        req.raw_text,
        req.check_stage,
    )


@router.get("/disqualify_rules")
def list_disqualify_rules():
    """获取废标红线规则列表（供管理后台展示）"""
    return load_disqualify_rules()


@router.get("/violation_cases")
def list_violation_cases(category: str = None):
    """获取违规案例库（可按类别过滤）"""
    return load_violation_cases(category)


@router.post("/plagiarism_check", response_model=PlagiarismCheckResp)
def check_plagiarism(req: PlagiarismCheckReq):
    """
    标书查重接口
    检测新生成的标书与知识库中已有标书的相似程度。
    相似度超过 85% 的章节会被标记为高风险。
    """
    return run_plagiarism_check(req.bid_content, req.exclude_doc_ids)
