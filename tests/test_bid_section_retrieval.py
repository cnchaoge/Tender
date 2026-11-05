"""标书生成的检索查询应按章节带上招标要求，而不是只有项目名和工期。"""
import inspect
import re

from server.core.retriever.section_query import (
    assemble_section_context,
    build_section_retrieval_query,
    collect_section_materials,
    section_retrieval_queries,
)

PARSE = {
    "project_name": "某油田地面工程物资采购",
    "deadline": "90日历天",
    "requirements": [
        "投标人须具备特种设备制造许可证",
        "产品须满足螺旋焊管壁厚公差与三层PE防腐技术要求",
    ],
    "qualification": ["ISO9001质量管理体系", "近三年石油石化供货业绩"],
    "scoring": {
        "method": "综合评分法",
        "sections": [
            {
                "name": "技术标",
                "weight": 50,
                "items": [
                    {
                        "name": "生产工艺与焊接质量",
                        "score": 20,
                        "max_score": 20,
                        "requirements": ["说明埋弧焊工艺及焊缝检测"],
                    },
                    {
                        "name": "防腐与规格响应",
                        "score": 15,
                        "max_score": 15,
                        "requirements": ["逐条响应壁厚、材质和防腐层"],
                    },
                ],
            },
            {
                "name": "商务标",
                "weight": 30,
                "items": [
                    {
                        "name": "分项报价完整性",
                        "score": 15,
                        "max_score": 15,
                        "requirements": ["按规格列示单价、增值税和保证金"],
                    }
                ],
            },
            {
                "name": "工期",
                "weight": 10,
                "items": [
                    {
                        "name": "交货进度",
                        "score": 10,
                        "max_score": 10,
                        "requirements": ["承诺按期交货并给出排产计划"],
                    }
                ],
            },
        ],
    },
}

TECH_CH = {
    "name": "技术方案",
    "description": "生产工艺流程与焊接质量控制",
    "key_points": "突出埋弧焊和防腐层",
}
PRICE_CH = {
    "name": "分项报价表",
    "description": "按规格逐项报价",
    "key_points": "单价、增值税与保证金",
}
SCHED_CH = {
    "name": "生产进度与交货计划",
    "description": "排产计划与交货节点",
    "key_points": "给出产能和进度节点",
}
QUAL_CH = {
    "name": "投标人资格审查资料",
    "description": "许可证、体系证书和供货业绩",
    "key_points": "证书需在有效期内",
}

CORPUS = {
    "tech": "埋弧焊工艺：螺旋焊管焊缝检测、壁厚公差控制、三层PE防腐层逐条技术响应。",
    "price": "分项报价表列示单价、增值税和投标保证金，付款方式为到货款。",
    "qual": "须提供特种设备制造许可证、ISO9001证书及近三年石油石化供货业绩。",
    "schedule": "排产计划承诺90日历天交货，并列出产能保障和进度节点。",
    "noise": "公司年会安排与食堂菜单，与本次采购规格无关。",
}


def _lexical_score(query: str, text: str) -> int:
    """用中文词面重合给素材打分，用来对比新旧查询谁更能命中对应章节。"""
    score = 0
    seen = set()
    for size in (8, 6, 4, 3, 2):
        if len(query) < size:
            continue
        for index in range(len(query) - size + 1):
            gram = query[index : index + size]
            if gram in seen or not re.fullmatch(r"[\u4e00-\u9fff]+", gram):
                continue
            seen.add(gram)
            if gram in text:
                score += size * size
    return score


def _top_chunk(query: str) -> str:
    return max(CORPUS, key=lambda key: _lexical_score(query, CORPUS[key]))


def _coarse_query() -> str:
    return f"招标文件：{PARSE['project_name']} {PARSE['deadline']}"


def test_technical_chapter_query_uses_section_and_scoring():
    query = build_section_retrieval_query(PARSE, TECH_CH)

    assert query.startswith("技术方案")
    assert "生产工艺流程与焊接质量控制" in query
    assert "埋弧焊" in query
    assert "壁厚公差" in query
    assert "生产工艺与焊接质量" in query
    assert "防腐与规格响应" in query
    assert PARSE["project_name"] in query
    assert query.index("技术方案") < query.index(PARSE["project_name"])
    # 技术章不应被工期或报价评分项带走
    assert "90日历天" not in query
    assert "分项报价" not in query
    assert "交货进度" not in query


def test_other_chapters_pick_their_own_signals():
    price = build_section_retrieval_query(PARSE, PRICE_CH)
    assert price.startswith("分项报价表")
    assert "分项报价完整性" in price
    assert "增值税" in price
    assert "埋弧焊" not in price
    assert "90日历天" not in price

    schedule = build_section_retrieval_query(PARSE, SCHED_CH)
    assert schedule.startswith("生产进度与交货计划")
    assert "交货进度" in schedule
    assert "90日历天" in schedule
    assert schedule.index("生产进度与交货计划") < schedule.index("90日历天")

    qual = build_section_retrieval_query(PARSE, QUAL_CH)
    assert "特种设备制造许可证" in qual
    assert "供货业绩" in qual
    assert "埋弧焊" not in qual

    letter = build_section_retrieval_query(
        PARSE, {"name": "第一章 投标函", "description": "投标报价与工期承诺"}
    )
    assert letter.startswith("第一章 投标函")
    assert "90日历天" in letter
    assert letter.index("投标函") < letter.index("90日历天")


def test_document_level_query_is_not_only_project_and_deadline():
    query = build_section_retrieval_query(PARSE, None)

    assert "特种设备制造许可证" in query
    assert "生产工艺与焊接质量" in query
    assert "分项报价完整性" in query
    assert PARSE["project_name"] in query
    assert "90日历天" in query
    assert query != _coarse_query()
    assert not query.startswith("招标文件")
    without_identity = query.replace(PARSE["project_name"], "").replace("90日历天", "").strip()
    assert len(without_identity) > 20


def test_placeholders_and_optional_technical_fields():
    query = build_section_retrieval_query(
        {
            "project_name": "未识别到项目名称",
            "deadline": "未知",
            "requirements": ["未识别到资格要求"],
            "qualification": ["解析失败"],
            "scoring": [{"name": "施工组织设计", "requirements": ["说明主要施工方法"]}],
        },
        {"name": "第三章 技术方案", "description": "焊接工艺"},
    )
    assert query.startswith("第三章 技术方案")
    assert "焊接工艺" in query
    assert "施工组织设计" in query
    assert "未识别" not in query
    assert "解析失败" not in query

    with_specs = build_section_retrieval_query(
        {**PARSE, "technical_requirements": ["必须采用埋弧焊并控制焊缝余高"]},
        TECH_CH,
    )
    assert "焊缝余高" in with_specs
    assert build_section_retrieval_query({}, None) == ""
    assert build_section_retrieval_query(None, None) == ""


def test_section_queries_follow_chapters():
    queries = section_retrieval_queries(PARSE, [TECH_CH, {}, PRICE_CH])
    assert [item["name"] for item in queries] == ["技术方案", "分项报价表"]
    assert queries[0]["query"] != queries[1]["query"]
    assert section_retrieval_queries(PARSE, None)[0]["name"] == ""


def test_section_query_retrieves_more_relevant_chunk_than_coarse_query():
    coarse = _coarse_query()
    technical = build_section_retrieval_query(PARSE, TECH_CH)
    commercial = build_section_retrieval_query(PARSE, PRICE_CH)

    assert _top_chunk(coarse) == "schedule"
    assert _top_chunk(technical) == "tech"
    assert _lexical_score(technical, CORPUS["tech"]) > _lexical_score(coarse, CORPUS["tech"])
    assert _top_chunk(commercial) == "price"
    assert _lexical_score(commercial, CORPUS["price"]) > _lexical_score(commercial, CORPUS["tech"])

    def retrieve(query, top_k=3, doc_ids=None):
        ranked = sorted(CORPUS, key=lambda key: _lexical_score(query, CORPUS[key]), reverse=True)
        hits = []
        for key in ranked:
            if _lexical_score(query, CORPUS[key]) <= 0:
                continue
            hits.append({"id": key, "text": CORPUS[key], "filename": "历史标书.docx"})
            if len(hits) >= top_k:
                break
        return hits

    context = collect_section_materials(
        [{"id": 1, "filename": "历史标书.docx"}],
        PARSE,
        [TECH_CH, PRICE_CH],
        retrieve_fn=retrieve,
    )
    tech_part, price_part = context.split("【分项报价表】")
    assert "【技术方案】" in tech_part
    assert "埋弧焊" in tech_part
    assert "增值税" not in tech_part
    assert "增值税" in price_part or "保证金" in price_part
    assert "埋弧焊" not in price_part


def test_context_budget_keeps_every_section():
    sections = [
        {"name": "技术方案", "chunks": [{"filename": "a.docx", "text": "甲" * 5000}]},
        {"name": "分项报价表", "chunks": [{"filename": "a.docx", "text": "乙" * 500}]},
    ]
    text = assemble_section_context(sections, max_chars=1000, chunk_chars=800)
    assert "【技术方案】" in text
    assert "【分项报价表】" in text
    assert len(text) <= 1000


def test_generate_paths_share_section_retrieval(monkeypatch):
    from server.api import bid

    for name in ("generate_bid", "generate_bid_stream", "plan_bid"):
        source = inspect.getsource(getattr(bid, name))
        assert "_retrieve_materials_text" in source
        assert "query_for_retrieve" not in source

    source_file = inspect.getsource(bid)
    assert "query_for_retrieve" not in source_file
    assert "招标文件：{req.parse_result" not in source_file

    calls = []

    def fake_retrieve(query, top_k=5, doc_ids=None):
        calls.append({"query": query, "top_k": top_k, "doc_ids": list(doc_ids or [])})
        return [{"id": f"c{len(calls)}", "text": "素材正文", "filename": "历史标书.docx"}]

    monkeypatch.setattr(bid, "retrieve", fake_retrieve)
    monkeypatch.setattr(
        bid, "_load_material_docs", lambda ids: [{"id": 7, "filename": "历史标书.docx"}]
    )

    grouped = bid._retrieve_materials_text(PARSE, [7], [TECH_CH, PRICE_CH])
    assert len(calls) == 2
    assert calls[0]["top_k"] == 2
    assert calls[0]["doc_ids"] == [7]
    assert "技术方案" in calls[0]["query"]
    assert "埋弧焊" in calls[0]["query"]
    assert "分项报价" in calls[1]["query"]
    assert "【技术方案】" in grouped
    assert "【分项报价表】" in grouped

    calls.clear()
    bid._retrieve_materials_text(PARSE, [7], None)
    assert len(calls) == 1
    assert calls[0]["top_k"] == 3
    assert calls[0]["query"] != _coarse_query()
    assert "生产工艺与焊接质量" in calls[0]["query"]
