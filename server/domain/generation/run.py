"""一次请求内的标书生成。

两条路径都调用 `BidDraftPipeline`：非流式整段生成，流式按增量往外推。
废标预检、质检、格式、查重和 Word 导出仍在这一次调用里做完。

阶段 4 才引入 jobs 表。关闭浏览器即停、草稿落盘和取消不在本阶段。
"""
import json

from server.core.generator.llm import get_generator
from server.core.reviewer import _check_format_compliance
from server.domain.export.docx import _write_bid_docx
from server.domain.generation.draft import BidDraftPipeline, chapter_lookup, match_heading_chapter
from server.domain.generation.materials import _retrieve_materials_text, generation_material_ids
from server.domain.generation.versions import _save_bid_version
from server.models import BidGenerateReq
from server.tools.plagiarism_checker import get_plagiarism_checker
from server.tools.violation_checker import get_violation_checker


def _sse_event(data: dict, event: str = "message") -> bytes:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n".encode()


def generate_bid(req: BidGenerateReq):
    """根据招标文件生成标书（带 AI 质检，非流式）。正文生成走 BidDraftPipeline。"""
    generator = get_generator()

    # 按章节检索素材。该项目的招标文件切片一并纳入，不进入全局问答。
    materials_text = _retrieve_materials_text(
        req.parse_result,
        generation_material_ids(req.materials, req.project_id),
        req.chapters,
    )
    pipe = BidDraftPipeline(generator, req.parse_result, materials_text, req.strategy)
    for _delta in pipe.iter_deltas(stream=False):
        pass
    review = pipe.review_draft()
    # 与原非流式接口一致：重写后仍返回首轮质检，不把第二轮结果写进响应。
    if pipe.needs_retry():
        for _delta in pipe.iter_deltas(stream=False):
            pass

    output_path = _write_bid_docx(pipe.content, req.parse_result.get("project_name", "投标标书"))
    return {
        "file_path": str(output_path),
        "filename": output_path.name,
        "review": {
            "passed": review["passed"],
            "score": review.get("score", 0),
            "issues": review.get("issues", []),
        }
    }


async def iter_generate_events(req: BidGenerateReq):
    generator = get_generator()

    # 与非流式生成共用按章节检索，避免流式路径仍只用项目名和工期。
    materials_text = _retrieve_materials_text(
        req.parse_result,
        generation_material_ids(req.materials, req.project_id),
        req.chapters,
    )
    pipe = BidDraftPipeline(generator, req.parse_result, materials_text, req.strategy)
    chapters = req.chapters or []
    chapter_name_to_idx = chapter_lookup(chapters)
    active_chapter_idx = None
    active_chapter_name = ""

    # 阶段0：生成前废标项预检
    yield _sse_event({"stage": "violation_check", "progress": 5, "message": "正在检测废标项风险..."})

    # 废标项检查（generate 阶段：检测标书正文是否满足招标文件要求）
    violation_checker = get_violation_checker()
    violation_result = None
    if req.parse_result:
        violation_result = violation_checker.check_bid_content(
            "",  # 还没生成，先用 parse_result 做生成前检查
            req.parse_result
        )
        # 如果有必废标项，中断生成流程
        if not violation_result["passed"]:
            yield _sse_event({
                "stage": "violation_fail",
                "progress": 0,
                "message": "检测到废标风险，生成已中止",
                "violation_result": {
                    "passed": False,
                    "violations": violation_result["violations"],
                    "summary": violation_result["summary"],
                }
            })
            return

    # 阶段1：生成中
    yield _sse_event({"stage": "generating", "progress": 10, "message": "正在生成标书正文..."})

    for delta in pipe.iter_deltas(stream=True):
        # Detect chapter headings from delta (markdown headings like "# 投标函" or "## 第一章 投标函")
        if chapters:
            matched = match_heading_chapter(delta, chapter_name_to_idx)
            if matched:
                ch_idx, ch_name = matched
                if active_chapter_idx != ch_idx:
                    if active_chapter_idx is not None:
                        yield _sse_event({
                            "stage": "chapter_done",
                            "chapter_index": active_chapter_idx,
                            "chapter_name": active_chapter_name,
                        })
                    active_chapter_idx = ch_idx
                    active_chapter_name = ch_name
                    yield _sse_event({
                        "stage": "chapter_start",
                        "chapter_index": ch_idx,
                        "chapter_name": ch_name,
                    })

        # 估算进度 10-60%
        yield _sse_event({"stage": "generating", "progress": 30, "message": "生成中...", "delta": delta})

    content = pipe.content

    # Mark last active chapter as done
    if active_chapter_idx is not None:
        yield _sse_event({
            "stage": "chapter_done",
            "chapter_index": active_chapter_idx,
            "chapter_name": active_chapter_name,
        })

    # ── 阶段2：废标项检测（基于生成的标书正文）───────────────────────
    yield _sse_event({"stage": "violation_check", "progress": 65, "message": "废标项合规性检测..."})
    if req.parse_result:
        violation_result = violation_checker.check_bid_content(content, req.parse_result)
        if not violation_result["passed"]:
            yield _sse_event({
                "stage": "violation_warn",
                "progress": 65,
                "message": "存在废标风险项，请留意",
                "violation_result": violation_result,
            })

    # 阶段3：质检
    yield _sse_event({"stage": "reviewing", "progress": 70, "message": "AI 质检审核中..."})

    review = pipe.review_draft()

    # 质检未通过则重生成一轮（流式路径会再用终稿复检）
    if pipe.needs_retry():
        yield _sse_event({"stage": "retry", "progress": 75, "message": "质检未通过，重新生成中..."})
        for delta in pipe.iter_deltas(stream=True):
            yield _sse_event({"stage": "retry", "progress": 85, "message": "重新生成中...", "delta": delta})
        content = pipe.content
        review = pipe.review_draft()
        yield _sse_event({"stage": "reviewing", "progress": 90, "message": "重新审核中..."})

    # ── 阶段3.5：格式规范检测 ────────────────────────────────────
    yield _sse_event({"stage": "format_check", "progress": 86, "message": "格式规范检测..."})
    format_result = _check_format_compliance(content, req.parse_result)

    # ── 阶段4：标书查重 ──────────────────────────────────────────
    yield _sse_event({"stage": "plagiarism_check", "progress": 88, "message": "标书查重检测..."})
    plagiarism_checker = get_plagiarism_checker()
    plagiarism_result = plagiarism_checker.check(
        bid_content=content,
        exclude_doc_ids=req.materials or [],
    )

    # 阶段5：生成 Word
    yield _sse_event({"stage": "word", "progress": 95, "message": "正在生成 Word 文件..."})
    output_path = _write_bid_docx(content, req.parse_result.get("project_name", "投标标书"))

    # 自动保存版本历史。strategy 写入请求里的策略，避免历史版本该字段一直为空。
    version_id = _save_bid_version(
        project_name=req.parse_result.get("project_name", ""),
        parse_result=req.parse_result,
        bid_content=content,
        strategy=req.strategy or "",
        file_path=str(output_path),
        material_ids=req.materials or [],
        project_id=req.project_id,
    )

    # 阶段6：完成
    final_chapters = []
    for ch in chapters:
        idx = ch.get("index", 0)
        final_chapters.append({
            "index": idx,
            "name": ch.get("name", ""),
            "status": "completed" if idx != active_chapter_idx else "completed",
            "progress": 100,
        })

    yield _sse_event({
        "stage": "done",
        "progress": 100,
        "message": "生成完成",
        "version_id": version_id,
        "file_path": str(output_path),
        "filename": output_path.name,
        "chapters": final_chapters,
        "review": {
            "passed": review["passed"],
            "score": review.get("score", 0),
            "issues": review.get("issues", []),
        },
        "format_result": {
            "passed": format_result["passed"],
            "score": format_result.get("score", 0),
            "warnings": format_result.get("warnings", []),
        },
        "violation_result": violation_result,
        "plagiarism_result": {
            "passed": plagiarism_result["passed"],
            "overall_score": plagiarism_result["overall_score"],
            "high_risk_sections": plagiarism_result["high_risk_sections"],
            "sections": [{"section_name": s["section_name"], "risk_level": s["risk_level"], "similarity_score": s["similarity_score"]} for s in plagiarism_result["sections"]],
        },
    })
