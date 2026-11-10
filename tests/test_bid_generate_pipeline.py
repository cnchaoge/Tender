"""批量生成和 SSE 生成共用同一条正文流水线，且不调用付费模型。"""
import asyncio
import inspect
import json

import pytest

from server.core.bidgen.pipeline import (
    SYSTEM_PROMPT,
    BidDraftPipeline,
    build_generation_prompt,
    chapter_lookup,
    match_heading_chapter,
    review_retry_prompt,
    strategy_guidance,
)
from server.models import BidGenerateReq

PARSE = {
    "project_name": "某油田地面工程",
    "deadline": "90日历天",
    "requirements": ["特种设备制造许可证"],
    "qualification": ["ISO9001"],
    "scoring": {
        "method": "综合评分法",
        "sections": [
            {
                "name": "技术标",
                "weight": 50,
                "items": [
                    {
                        "name": "焊接",
                        "score": 20,
                        "max_score": 20,
                        "type": "expert",
                        "requirements": ["埋弧焊"],
                    }
                ],
            }
        ],
        "disqualify_conditions": ["未按期递交"],
    },
    "parse_meta": {"confidence": 0.9},
}
CHAPTERS = [{"index": 0, "name": "第一章 投标函", "description": "投标函正文"}]
MATERIALS = "【技术方案】\n埋弧焊工艺"


def _req(**overrides) -> BidGenerateReq:
    payload = {
        "parse_result": dict(PARSE),
        "materials": [7],
        "chapters": list(CHAPTERS),
        "strategy": "技术优先型",
    }
    payload.update(overrides)
    return BidGenerateReq(**payload)


class FakeGenerator:
    def __init__(self, text="# 投标函\n感谢贵方。"):
        self.text = text
        self.prompts = []
        self.stream_prompts = []
        self.system = ""

    def generate(self, prompt, system="", **kwargs):
        self.prompts.append(prompt)
        self.system = system
        return self.text

    def generate_stream(self, prompt, system="", **kwargs):
        self.stream_prompts.append(prompt)
        self.system = system
        # 标题单独成块，流式章节识别才能按原规则命中。
        head, _, tail = self.text.partition("\n")
        yield head + "\n"
        if tail:
            yield tail


def test_generation_prompt_is_stable_and_includes_strategy_scoring_and_materials():
    prompt = build_generation_prompt(PARSE, MATERIALS, "技术优先型")
    assert prompt == f"""根据以下招标文件要求和素材，生成一份投标标书。

招标文件：
- 项目名称：某油田地面工程
- 工期：90日历天
- 资格要求：特种设备制造许可证
- 资质要求：ISO9001
- 评标办法：综合评分法
  技术标（权重50%）：
    - 焊接：20/20分，专家打分，埋弧焊
  废标条件：未按期递交

{strategy_guidance("技术优先型")}

可用素材（按章节分组，撰写该章节时优先使用对应素材）：
{MATERIALS}

请生成完整的投标标书，包含：
1. 投标函
2. 资格审查文件
3. 技术标
4. 商务标

输出格式：Markdown"""
    assert "【投标策略】：技术优先型" in prompt
    assert strategy_guidance("不存在的策略") == strategy_guidance("综合均衡型")
    assert "不存在的策略" not in strategy_guidance("不存在的策略")


def test_low_confidence_prompt_attaches_raw_text_once():
    raw = "甲" * 3000 + "乙"
    low = {
        **PARSE,
        "parse_meta": {"confidence": 0.4},
        "raw_text": raw,
    }
    prompt = build_generation_prompt(low, "", "综合均衡型")
    assert "【原文内容】" in prompt
    assert "甲" * 3000 in prompt
    assert "乙" not in prompt
    assert "\n无\n" in prompt

    unnamed = {**PARSE, "project_name": "未识别到项目名称", "raw_text": "请看原文"}
    assert "请看原文" in build_generation_prompt(unnamed, MATERIALS, "综合均衡型")
    failed = {**PARSE, "project_name": "解析失败", "raw_text": "失败原文"}
    assert "失败原文" in build_generation_prompt(failed, MATERIALS, "综合均衡型")
    assert "【原文内容】" not in build_generation_prompt(PARSE, MATERIALS, "综合均衡型")


def test_review_retry_prompt_appends_suggestions():
    base = build_generation_prompt(PARSE, MATERIALS, "成本控制型")
    retried = review_retry_prompt(base, {"suggestions": ["补充分项报价", "补充工期"]})
    assert retried == base + "\n\n[审核意见] 补充分项报价；补充工期"


def test_chapter_heading_match_strips_prefix():
    lookup = chapter_lookup(CHAPTERS + [{"index": 2, "name": "分项报价表"}])
    assert lookup == {"投标函": 0, "分项报价表": 2}
    assert match_heading_chapter("# 投标函\n", lookup) == (0, "投标函")
    assert match_heading_chapter("投标函\n", lookup) is None
    assert match_heading_chapter("# 其他\n", lookup) is None
    assert match_heading_chapter("# 投标函\n", {}) is None


def test_pipeline_uses_generate_or_stream_and_retries_once(monkeypatch):
    reviews = [
        {"passed": False, "score": 40, "issues": ["缺报价"], "suggestions": ["补充分项报价"]},
        {"passed": True, "score": 88, "issues": [], "suggestions": []},
    ]

    def fake_review(content, parse_result):
        assert "投标函" in content
        assert parse_result["project_name"] == PARSE["project_name"]
        return reviews.pop(0)

    monkeypatch.setattr("server.domain.generation.draft.review_bid", fake_review)
    gen = FakeGenerator()
    pipe = BidDraftPipeline(gen, PARSE, MATERIALS, "技术优先型")
    assert list(pipe.iter_deltas(stream=False)) == ["# 投标函\n感谢贵方。"]
    first = pipe.review_draft()
    assert first["passed"] is False
    assert pipe.needs_retry()
    assert list(pipe.iter_deltas(stream=False)) == ["# 投标函\n感谢贵方。"]
    assert "补充分项报价" in gen.prompts[1]
    assert gen.system == SYSTEM_PROMPT
    assert pipe.needs_retry() is False
    with pytest.raises(RuntimeError):
        list(pipe.iter_deltas(stream=False))

    reviews.append({"passed": True, "score": 90, "issues": [], "suggestions": []})
    streamed = BidDraftPipeline(FakeGenerator(), PARSE, MATERIALS, "技术优先型")
    deltas = list(streamed.iter_deltas(stream=True))
    assert deltas == ["# 投标函\n", "感谢贵方。"]
    assert streamed.review_draft()["passed"] is True
    assert streamed.needs_retry() is False


def test_routes_delegate_prompt_building():
    """路由只转发。非流式生成路由已删除。提示词和重写仍在领域模块。"""
    from server.api import bid
    from server.domain.generation import run as generation_run

    assert not hasattr(bid, "generate_bid")
    stream_route = inspect.getsource(bid.generate_bid_stream)
    assert "iter_generate_events" in stream_route
    assert "根据以下招标文件要求" not in stream_route
    assert "_get_strategy_guidance" not in stream_route

    for fn in (generation_run.generate_bid, generation_run.execute_generate_job):
        source = inspect.getsource(fn)
        assert "BidDraftPipeline" in source
        assert "_retrieve_materials_text" in source
        assert "根据以下招标文件要求" not in source
        assert "_get_strategy_guidance" not in source


class _Doc:
    def save(self, path):
        self.path = path


class _Violation:
    def __init__(self, passed=True):
        self.passed = passed
        self.calls = []

    def check_bid_content(self, content, parse_result):
        self.calls.append(content)
        return {
            "passed": self.passed,
            "violations": [] if self.passed else [{"rule": "保证金"}],
            "summary": {"disqualify_count": 0 if self.passed else 1},
        }


class _Plagiarism:
    def check(self, bid_content, exclude_doc_ids=None, **kwargs):
        return {
            "passed": True,
            "overall_score": 3,
            "high_risk_sections": 0,
            "sections": [
                {"section_name": "投标函", "risk_level": "low", "similarity_score": 3}
            ],
        }


def _parse_sse(raw: bytes) -> list[dict]:
    events = []
    text = raw.decode()
    for block in text.split("\n\n"):
        for line in block.split("\n"):
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
    return events


def _install(monkeypatch, gen, reviews, violation=None):
    import sqlite3
    import tempfile
    from pathlib import Path

    from server.api import bid
    from server.db import sqlite as sqlite_mod
    from server.domain.export import docx
    from server.domain.generation import draft
    from server.domain.generation import run as generation_run
    from server.workers.runner import shutdown_runner

    shutdown_runner(wait=True)
    data = Path(tempfile.mkdtemp())
    db_path = data / "jobs.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'queued',
            progress INTEGER NOT NULL DEFAULT 0,
            message TEXT NOT NULL DEFAULT '',
            payload_json TEXT NOT NULL DEFAULT '{}',
            result_json TEXT,
            cancel_requested INTEGER NOT NULL DEFAULT 0,
            runtime_json TEXT NOT NULL DEFAULT '{}',
            idempotency_key TEXT,
            project_id INTEGER,
            document_id INTEGER,
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            started_at TIMESTAMP,
            finished_at TIMESTAMP
        );
        CREATE TABLE job_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL,
            seq INTEGER NOT NULL,
            kind TEXT NOT NULL,
            payload_json TEXT NOT NULL DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    conn.commit()
    conn.close()

    def getter():
        link = sqlite3.connect(db_path, check_same_thread=False)
        link.row_factory = sqlite3.Row
        return link

    monkeypatch.setattr(sqlite_mod, "DB_PATH", db_path)
    monkeypatch.setattr(sqlite_mod, "get_db", getter)

    violation = violation or _Violation()
    saved = {}
    retrievals = []

    def fake_retrieve(parse_result, materials, chapters=None, per_doc_k=None, max_chars=6000):
        retrievals.append({"materials": list(materials), "chapters": chapters, "per_doc_k": per_doc_k})
        return MATERIALS

    def fake_review(content, parse_result):
        return reviews.pop(0)

    def fake_insert(**kwargs):
        saved.update(kwargs)
        return 11

    def fake_update(version_id, **kwargs):
        saved["version_id"] = version_id
        saved.update({key: value for key, value in kwargs.items() if value is not None})

    monkeypatch.setattr(generation_run, "get_generator", lambda: gen)
    monkeypatch.setattr(generation_run, "_retrieve_materials_text", fake_retrieve)
    monkeypatch.setattr(docx, "_docx_from_markdown", lambda content, title="投标标书": _Doc())
    monkeypatch.setattr(generation_run, "_check_format_compliance", lambda content, parse: {"passed": True, "score": 80, "warnings": []})
    monkeypatch.setattr(generation_run, "get_violation_checker", lambda: violation)
    monkeypatch.setattr(generation_run, "get_plagiarism_checker", lambda: _Plagiarism())
    monkeypatch.setattr(generation_run, "insert_draft_version", fake_insert)
    monkeypatch.setattr(generation_run, "update_draft_version", fake_update)
    monkeypatch.setattr(generation_run, "discard_empty_draft", lambda version_id: None)
    monkeypatch.setattr(draft, "review_bid", fake_review)
    return bid, saved, retrievals, violation


def _collect_sse(bid, req) -> list[dict]:
    async def _run():
        response = await bid.generate_bid_stream(req)
        chunks = []
        async for chunk in response.body_iterator:
            chunks.append(chunk if isinstance(chunk, (bytes, bytearray)) else str(chunk).encode())
        return b"".join(chunks)

    try:
        return _parse_sse(asyncio.run(_run()))
    finally:
        from server.workers.runner import shutdown_runner

        shutdown_runner(wait=True)


def test_batch_and_stream_share_one_prompt_and_section_retrieval(monkeypatch):
    gen = FakeGenerator()
    reviews = [
        {"passed": True, "score": 91, "issues": [], "suggestions": []},
        {"passed": True, "score": 92, "issues": ["无"], "suggestions": []},
    ]
    from server.domain.generation import run as generation_run

    bid, saved, retrievals, violation = _install(monkeypatch, gen, reviews)
    req = _req()

    batch = generation_run.generate_bid(req)
    events = _collect_sse(bid, req)

    assert len(gen.prompts) == 1
    assert len(gen.stream_prompts) == 1
    assert gen.prompts[0] == gen.stream_prompts[0] == build_generation_prompt(PARSE, MATERIALS, "技术优先型")
    assert gen.system == SYSTEM_PROMPT
    assert [item["chapters"] for item in retrievals] == [CHAPTERS, CHAPTERS]
    assert retrievals[0]["materials"] == [7]
    assert batch["review"] == {"passed": True, "score": 91, "issues": []}
    assert batch["filename"].startswith("bid_") and batch["filename"].endswith(".docx")

    stages = [event["stage"] for event in events]
    assert stages[0] == "violation_check"
    assert "chapter_start" in stages
    assert "chapter_done" in stages
    assert stages[-1] == "done"
    start = next(event for event in events if event["stage"] == "chapter_start")
    assert start["chapter_index"] == 0
    assert start["chapter_name"] == "投标函"
    done = events[-1]
    assert done["review"]["score"] == 92
    assert done["version_id"] == 11
    assert done["filename"].endswith(".docx")
    assert done["plagiarism_result"]["sections"][0]["section_name"] == "投标函"
    assert "".join(event.get("delta", "") for event in events if event["stage"] == "generating") == "# 投标函\n感谢贵方。"
    assert saved["strategy"] == "技术优先型"
    assert saved["bid_content"].startswith("# 投标函")
    assert saved["material_ids"] == [7]
    assert violation.calls[0] == ""
    assert violation.calls[1].startswith("# 投标函")


def test_batch_keeps_first_review_and_stream_rereviews(monkeypatch):
    gen = FakeGenerator(text="# 投标函\n第二稿也从这里开始。")
    reviews = [
        {"passed": False, "score": 30, "issues": ["缺报价"], "suggestions": ["补充分项报价"]},
        {"passed": False, "score": 35, "issues": ["仍缺报价"], "suggestions": ["再补报价"]},
        {"passed": True, "score": 86, "issues": [], "suggestions": []},
    ]
    from server.domain.generation import run as generation_run

    bid, saved, _retrievals, _violation = _install(monkeypatch, gen, reviews)

    batch = generation_run.generate_bid(_req())
    assert batch["review"]["passed"] is False
    assert batch["review"]["score"] == 30
    assert len(gen.prompts) == 2
    assert gen.prompts[1].endswith("\n\n[审核意见] 补充分项报价")

    events = _collect_sse(bid, _req())
    assert len(gen.stream_prompts) == 2
    assert gen.stream_prompts[1].endswith("\n\n[审核意见] 再补报价")
    assert [event["stage"] for event in events].count("retry") >= 1
    assert events[-1]["stage"] == "done"
    assert events[-1]["review"]["passed"] is True
    assert events[-1]["review"]["score"] == 86
    assert saved["strategy"] == "技术优先型"


def test_stream_stops_before_llm_when_precheck_fails(monkeypatch):
    gen = FakeGenerator()
    bid, saved, retrievals, violation = _install(
        monkeypatch, gen, [], violation=_Violation(passed=False)
    )
    events = _collect_sse(bid, _req())
    assert [event["stage"] for event in events] == ["violation_check", "violation_fail"]
    assert events[1]["violation_result"]["violations"][0]["rule"] == "保证金"
    assert gen.prompts == []
    assert gen.stream_prompts == []
    assert saved.get("file_path", "") == ""
    assert saved.get("bid_content", "") == ""
    assert retrievals and violation.calls == [""]
