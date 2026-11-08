"""一次请求内的标书生成。

非流式接口仍直接调用 `BidDraftPipeline`。流式接口是作业的兼容壳：
创建 `bid.generate`，由进程内运行器执行 `execute_generate_job`，再把事件推出去。
提示词、质检和最多重写一轮不在这里改。
"""
import asyncio
import json

from server.core.generator.llm import get_generator
from server.core.reviewer import _check_format_compliance
from server.domain.export.docx import _write_bid_docx
from server.domain.generation.draft import BidDraftPipeline, chapter_lookup, match_heading_chapter
from server.domain.generation.materials import _retrieve_materials_text, generation_material_ids
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


def insert_draft_version(**kwargs) -> int:
    from server.domain.generation.versions import insert_draft_version as _insert

    return _insert(**kwargs)


def update_draft_version(version_id: int, **kwargs) -> None:
    from server.domain.generation.versions import update_draft_version as _update

    _update(version_id, **kwargs)


def discard_empty_draft(version_id: int) -> None:
    from server.domain.generation.versions import discard_empty_draft as _discard

    _discard(version_id)


def _project_parse_id(project_id: int | None) -> int | None:
    if not project_id:
        return None
    from server.domain.projects.service import require_project

    try:
        project = require_project(int(project_id))
    except Exception:
        return None
    parse_id = project.get("parse_id")
    return int(parse_id) if parse_id else None


def _emit(job_id: int, payload: dict) -> None:
    from server.domain.jobs.store import append_event

    append_event(job_id, str(payload.get("stage") or "message"), payload)


def execute_generate_job(req: BidGenerateReq, job_id: int) -> dict:
    """跑一笔生成。取消留在章节边界或下一次模型调用之前。"""
    from server.domain.export.docx import write_version_docx
    from server.domain.jobs.runtime import pinned_runtime, raise_if_cancelled, runtime_public
    from server.domain.jobs.store import JobCancelled, JobFailed

    generator = get_generator()
    materials_text = _retrieve_materials_text(
        req.parse_result,
        generation_material_ids(req.materials, req.project_id),
        req.chapters,
    )
    runtime = runtime_public(pinned_runtime() or {})
    version_id = insert_draft_version(
        project_name=req.parse_result.get("project_name", ""),
        parse_result=req.parse_result,
        strategy=req.strategy or "",
        material_ids=req.materials or [],
        project_id=req.project_id,
        parse_id=_project_parse_id(req.project_id),
        outline=req.chapters or [],
        runtime=runtime,
        job_id=job_id,
    )
    pipe = BidDraftPipeline(generator, req.parse_result, materials_text, req.strategy)
    chapters = req.chapters or []
    chapter_name_to_idx = chapter_lookup(chapters)
    active_chapter_idx = None
    active_chapter_name = ""

    def save_draft(content: str, status: str = "draft") -> None:
        update_draft_version(version_id, bid_content=content, status=status)

    _emit(job_id, {"stage": "violation_check", "progress": 5, "message": "正在检测废标项风险...", "job_id": job_id})
    violation_checker = get_violation_checker()
    violation_result = None
    if req.parse_result:
        violation_result = violation_checker.check_bid_content("", req.parse_result)
        if not violation_result["passed"]:
            _emit(job_id, {
                "stage": "violation_fail",
                "progress": 0,
                "message": "检测到废标风险，生成已中止",
                "job_id": job_id,
                "violation_result": {
                    "passed": False,
                    "violations": violation_result["violations"],
                    "summary": violation_result["summary"],
                },
            })
            discard_empty_draft(version_id)
            raise JobFailed("检测到废标风险，生成已中止", {"violation_result": violation_result})

    _emit(job_id, {"stage": "generating", "progress": 10, "message": "正在生成标书正文...", "job_id": job_id})
    raise_if_cancelled()

    # pipe.content 要等这一轮模型调用结束才赋值。章节边界用已经吐出的增量。
    accumulated: list[str] = []
    for delta in pipe.iter_deltas(stream=True):
        if chapters:
            matched = match_heading_chapter(delta, chapter_name_to_idx)
            if matched:
                ch_idx, ch_name = matched
                if active_chapter_idx != ch_idx:
                    if active_chapter_idx is not None:
                        written = "".join(accumulated)
                        save_draft(written)
                        _emit(job_id, {
                            "stage": "chapter_done",
                            "chapter_index": active_chapter_idx,
                            "chapter_name": active_chapter_name,
                            "job_id": job_id,
                        })
                        if _cancel_requested(job_id):
                            save_draft(written, "cancelled")
                            _emit(job_id, {
                                "stage": "cancelled",
                                "progress": 30,
                                "message": "生成已停止",
                                "job_id": job_id,
                                "version_id": version_id,
                            })
                            raise JobCancelled()
                    active_chapter_idx = ch_idx
                    active_chapter_name = ch_name
                    _emit(job_id, {
                        "stage": "chapter_start",
                        "chapter_index": ch_idx,
                        "chapter_name": ch_name,
                        "job_id": job_id,
                    })
        accumulated.append(delta)
        _emit(job_id, {"stage": "generating", "progress": 30, "message": "生成中...", "delta": delta, "job_id": job_id})

    content = pipe.content
    save_draft(content)
    if active_chapter_idx is not None:
        _emit(job_id, {
            "stage": "chapter_done",
            "chapter_index": active_chapter_idx,
            "chapter_name": active_chapter_name,
            "job_id": job_id,
        })
    if _cancel_requested(job_id):
        save_draft(content, "cancelled")
        _emit(job_id, {
            "stage": "cancelled",
            "progress": 30,
            "message": "生成已停止",
            "job_id": job_id,
            "version_id": version_id,
        })
        raise JobCancelled()

    _emit(job_id, {"stage": "violation_check", "progress": 65, "message": "废标项合规性检测...", "job_id": job_id})
    if req.parse_result:
        violation_result = violation_checker.check_bid_content(content, req.parse_result)
        if not violation_result["passed"]:
            _emit(job_id, {
                "stage": "violation_warn",
                "progress": 65,
                "message": "存在废标风险项，请留意",
                "job_id": job_id,
                "violation_result": violation_result,
            })

    raise_if_cancelled()
    _emit(job_id, {"stage": "reviewing", "progress": 70, "message": "AI 质检审核中...", "job_id": job_id})
    review = pipe.review_draft()
    if pipe.needs_retry():
        raise_if_cancelled()
        _emit(job_id, {"stage": "retry", "progress": 75, "message": "质检未通过，重新生成中...", "job_id": job_id})
        for delta in pipe.iter_deltas(stream=True):
            _emit(job_id, {"stage": "retry", "progress": 85, "message": "重新生成中...", "delta": delta, "job_id": job_id})
        content = pipe.content
        save_draft(content)
        if _cancel_requested(job_id):
            save_draft(content, "cancelled")
            _emit(job_id, {
                "stage": "cancelled",
                "progress": 85,
                "message": "生成已停止",
                "job_id": job_id,
                "version_id": version_id,
            })
            raise JobCancelled()
        review = pipe.review_draft()
        _emit(job_id, {"stage": "reviewing", "progress": 90, "message": "重新审核中...", "job_id": job_id})

    _emit(job_id, {"stage": "format_check", "progress": 86, "message": "格式规范检测...", "job_id": job_id})
    format_result = _check_format_compliance(content, req.parse_result)

    _emit(job_id, {"stage": "plagiarism_check", "progress": 88, "message": "标书查重检测...", "job_id": job_id})
    plagiarism_checker = get_plagiarism_checker()
    plagiarism_result = plagiarism_checker.check(
        bid_content=content,
        exclude_doc_ids=req.materials or [],
    )

    raise_if_cancelled()
    _emit(job_id, {"stage": "word", "progress": 95, "message": "正在生成 Word 文件...", "job_id": job_id})
    output_path = write_version_docx(content, req.parse_result.get("project_name", "投标标书"), version_id)
    update_draft_version(
        version_id,
        bid_content=content,
        status="ready",
        file_path=str(output_path),
        strategy=req.strategy or "",
        material_ids=req.materials or [],
    )
    _touch_project(req.project_id)

    final_chapters = []
    for ch in chapters:
        idx = ch.get("index", 0)
        final_chapters.append({
            "index": idx,
            "name": ch.get("name", ""),
            "status": "completed",
            "progress": 100,
        })
    done = {
        "stage": "done",
        "progress": 100,
        "message": "生成完成",
        "job_id": job_id,
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
            "sections": [
                {
                    "section_name": s["section_name"],
                    "risk_level": s["risk_level"],
                    "similarity_score": s["similarity_score"],
                }
                for s in plagiarism_result["sections"]
            ],
        },
    }
    _emit(job_id, done)
    return {
        "version_id": version_id,
        "file_path": str(output_path),
        "filename": output_path.name,
        "review": done["review"],
    }


def _cancel_requested(job_id: int) -> bool:
    from server.domain.jobs.store import is_cancel_requested

    return is_cancel_requested(job_id)


def _touch_project(project_id: int | None) -> None:
    if not project_id:
        return
    from server.db.sqlite import get_db

    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            """UPDATE projects
               SET updated_at = CURRENT_TIMESTAMP,
                   status = CASE WHEN status = 'draft' THEN 'active' ELSE status END
               WHERE id = ?""",
            (int(project_id),),
        )
        conn.commit()
    except Exception:
        return
    finally:
        conn.close()


async def iter_generate_events(req: BidGenerateReq):
    """兼容壳。创建作业并把 `job_events` 按原来的 SSE 形状推出去。

    断开这条流（浏览器关闭、刷新、读端取消）时置 `cancel_requested`。
    入库作业不走这里，页面关掉后仍会跑完。
    """
    from server.domain.jobs.service import enqueue_generate
    from server.domain.jobs.store import get_job_row, list_events, request_cancel

    job = enqueue_generate(req)
    completed = False
    last = 0
    try:
        while True:
            events = list_events(job["id"], last)
            current = get_job_row(job["id"])
            for event in events:
                last = event["seq"]
                payload = dict(event["payload"])
                yield _sse_event(payload)
                if payload.get("stage") in {"done", "violation_fail", "cancelled", "error"}:
                    completed = True
                    return
            if current["status"] in {"succeeded", "failed", "cancelled", "interrupted"} and not events:
                completed = True
                return
            await asyncio.sleep(0.05)
    finally:
        if not completed:
            try:
                request_cancel(job["id"])
            except Exception:
                pass

