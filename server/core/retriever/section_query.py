"""按章节构造标书生成用的检索查询。

生成某一章节时，查询以该章标题和用途为主，并带上招标文件里与该章相关的
技术要求、资格条件和评分项。不再只用「项目名称 + 工期」。
"""
import re
from typing import Callable, Optional

# 整段就是占位文案时丢弃，避免把「未识别到…」送进向量检索。
_DROP_EXACT = {"未知", "无", "暂无", "不详", "null", "None", "N/A"}
_DROP_PREFIXES = ("未识别", "解析失败")

# 只根据章节标题判断侧重点；标题对不上时再看描述。
_FOCUS_KEYWORDS = {
    "technical": ("技术", "施工", "工艺", "质量", "参数", "检测", "规格", "焊接", "防腐"),
    "commercial": ("商务", "报价", "价格", "费用", "成本", "保证金", "付款", "发票", "税率"),
    "qualification": ("资格", "资质", "业绩", "证明", "审查", "证书", "许可证", "人员"),
    "schedule": ("工期", "进度", "交货", "交付", "排产"),
    "letter": ("投标函",),
}

_CHAPTER_PREFIX = re.compile(
    r"^(?:第[0-9一二三四五六七八九十百零]+[章节]\s*|[0-9]{1,2}[.、．]\s*|[一二三四五六七八九十]+、\s*)"
)

MAX_QUERY_CHARS = 420
_TECH_FIELDS = ("technical_requirements", "tech_requirements", "technical_specs")


def _clean(value: object) -> str:
    if not isinstance(value, str):
        return ""
    text = re.sub(r"\s+", " ", value).strip()
    if not text or text in _DROP_EXACT or text.startswith(_DROP_PREFIXES):
        return ""
    return text


def _clip(value: object, limit: int) -> str:
    text = _clean(value)
    if len(text) <= limit:
        return text
    return text[:limit].rstrip()


def _dedupe(parts: list[str]) -> list[str]:
    seen = set()
    out = []
    for part in parts:
        part = part.strip()
        if not part or part in seen:
            continue
        seen.add(part)
        out.append(part)
    return out


def _strip_chapter_prefix(name: str) -> str:
    return _CHAPTER_PREFIX.sub("", name).strip() or name


def _matches(text: str, focus: str) -> bool:
    return any(keyword in text for keyword in _FOCUS_KEYWORDS.get(focus, ()))


def _focuses_for(chapter: Optional[dict]) -> list[str]:
    if not chapter:
        return []
    name = _strip_chapter_prefix(_clean(chapter.get("name", "")))
    hits = [focus for focus in _FOCUS_KEYWORDS if name and _matches(name, focus)]
    if hits:
        return hits
    extra = " ".join(_clean(chapter.get(key, "")) for key in ("description", "key_points"))
    return [focus for focus in _FOCUS_KEYWORDS if extra and _matches(extra, focus)]


def _texts(parse_result: dict, *keys: str) -> list[str]:
    found = []
    for key in keys:
        value = parse_result.get(key)
        if isinstance(value, str):
            values = [value]
        elif isinstance(value, list):
            values = value
        else:
            continue
        for item in values:
            text = _clip(item, 100)
            if text:
                found.append(text)
    return _dedupe(found)


def _iter_scoring_items(scoring: object):
    if isinstance(scoring, dict):
        sections = scoring.get("sections") or []
        if not isinstance(sections, list):
            return
        for section in sections:
            if not isinstance(section, dict):
                continue
            sec_name = _clip(section.get("name", ""), 20)
            items = section.get("items") or []
            if not isinstance(items, list):
                continue
            for item in items:
                if isinstance(item, dict):
                    yield sec_name, item
                elif isinstance(item, str):
                    yield sec_name, {"name": item}
    elif isinstance(scoring, list):
        for item in scoring:
            if isinstance(item, dict):
                yield "", item
            elif isinstance(item, str):
                yield "", {"name": item}


def _item_label(sec_name: str, item: dict) -> str:
    """只用评分项名称判断它属于哪一类，避免条目说明里的个别词串章。"""
    name = _clip(item.get("name", ""), 40)
    return " ".join(bit for bit in (sec_name, name) if bit)


def _item_brief(sec_name: str, item: dict) -> str:
    name = _clip(item.get("name", ""), 40)
    reqs = item.get("requirements") or []
    req = ""
    if isinstance(reqs, list) and reqs:
        req = _clip(reqs[0], 60)
    elif isinstance(reqs, str):
        req = _clip(reqs, 60)
    return _clip(" ".join(bit for bit in (sec_name, name, req) if bit), 110)


def _overlap(text: str, chapter: dict) -> int:
    """章节标题与候选文本的词面重合，用于没有明确侧重点时挑评分项。"""
    name = _strip_chapter_prefix(_clean(chapter.get("name", "")))
    if not name or not text:
        return 0
    score = 3 if name in text else 0
    keywords = {kw for words in _FOCUS_KEYWORDS.values() for kw in words}
    score += sum(2 for kw in keywords if kw in name and kw in text)
    for token in re.findall(r"[\u4e00-\u9fff]{4,}", name):
        if token[:4] in text:
            score += 1
    return score


def _requirement_signals(parse_result: dict, focuses: list[str], chapter: Optional[dict]) -> list[str]:
    tech = _texts(parse_result, *_TECH_FIELDS)
    reqs = _texts(parse_result, "requirements")
    quals = _texts(parse_result, "qualification")
    if chapter is None:
        return _dedupe(tech[:2] + reqs[:3] + quals[:2])[:6]

    picked: list[str] = []
    if "technical" in focuses:
        picked.extend(tech)
        picked.extend(req for req in reqs if _matches(req, "technical"))
    if "qualification" in focuses:
        picked.extend(quals)
        picked.extend(req for req in reqs if _matches(req, "qualification"))
    if "commercial" in focuses:
        picked.extend(req for req in reqs + quals if _matches(req, "commercial"))
    if "schedule" in focuses:
        picked.extend(req for req in reqs if _matches(req, "schedule"))
    if not picked and chapter is not None:
        picked.extend(_by_name_overlap(tech + reqs + quals, chapter, limit=2))
    return _dedupe(picked)[:4]


def _by_name_overlap(candidates: list[str], chapter: dict, limit: int) -> list[str]:
    name = _strip_chapter_prefix(_clean(chapter.get("name", "")))
    desc = _clean(chapter.get("description", ""))
    keys = [name] if len(name) >= 2 else []
    keys.extend(re.findall(r"[\u4e00-\u9fff]{2,}", name))
    keys.extend(re.findall(r"[\u4e00-\u9fff]{3,}", desc)[:6])
    picked = []
    for cand in candidates:
        if any(key and key in cand for key in keys):
            picked.append(cand)
        if len(picked) >= limit:
            break
    return picked


def _scoring_signals(
    parse_result: dict,
    focuses: list[str],
    chapter: Optional[dict],
    limit: int,
) -> list[str]:
    ranked = []
    plain = []
    for sec_name, item in _iter_scoring_items(parse_result.get("scoring")):
        brief = _item_brief(sec_name, item)
        label = _item_label(sec_name, item)
        if not brief:
            continue
        if chapter is None:
            plain.append(brief)
            continue
        # 归类看章节名和评分项名；说明文字只放进已选中的查询，不参与归类。
        score = _overlap(label, chapter)
        if focuses and any(_matches(label, focus) for focus in focuses):
            score += 2
        if score > 0:
            ranked.append((score, brief))
    if chapter is None:
        return _dedupe(plain)[:limit]
    ranked.sort(key=lambda pair: pair[0], reverse=True)
    return _dedupe([brief for _, brief in ranked])[:limit]


def build_section_retrieval_query(parse_result: Optional[dict], chapter: Optional[dict] = None) -> str:
    """构造一章（或无章节时的整份标书）的检索查询。

    章节标题和用途放在前面。工期只在进度类、投标函，以及没有章节的总查询里出现。
    """
    parse_result = parse_result or {}
    if chapter is not None and not isinstance(chapter, dict):
        chapter = None
    focuses = _focuses_for(chapter)

    parts: list[str] = []
    if chapter:
        for key, limit in (("name", 60), ("description", 100), ("key_points", 80)):
            piece = _clip(chapter.get(key, ""), limit)
            if piece:
                parts.append(piece)

    parts.extend(_requirement_signals(parse_result, focuses, chapter))
    parts.extend(_scoring_signals(parse_result, focuses, chapter, limit=4 if chapter else 6))

    project = _clip(parse_result.get("project_name", ""), 40)
    deadline = _clip(parse_result.get("deadline", ""), 40)
    if project:
        parts.append(project)
    # 工期会把检索拉向进度类素材，只在和工期相关的章节（或没有章节的总查询）里保留。
    if deadline and (chapter is None or any(focus in focuses for focus in ("schedule", "letter"))):
        parts.append(deadline)

    query = " ".join(_dedupe(parts))
    if len(query) > MAX_QUERY_CHARS:
        query = query[:MAX_QUERY_CHARS].rstrip()
    return query


def section_retrieval_queries(parse_result: Optional[dict], chapters: Optional[list]) -> list[dict]:
    """每个章节一条查询；没有可用章节时返回一条文档级查询。"""
    usable = []
    for chapter in chapters or []:
        if not isinstance(chapter, dict):
            continue
        if _clean(chapter.get("name", "")) or _clean(chapter.get("description", "")):
            usable.append(chapter)
    if not usable:
        return [{"name": "", "query": build_section_retrieval_query(parse_result, None)}]
    queries = []
    for chapter in usable:
        name = _clean(chapter.get("name", "")) or "章节"
        queries.append({"name": name, "query": build_section_retrieval_query(parse_result, chapter)})
    return queries


def assemble_section_context(
    sections: list[dict],
    max_chars: int = 6000,
    chunk_chars: int = 320,
) -> str:
    """按章节等额分配上下文字数，避免前面的章节占满素材片段。"""
    buckets: list[tuple[str, list[str]]] = []
    for section in sections:
        items: list[str] = []
        for chunk in section.get("chunks") or []:
            text = (chunk.get("text") or "").strip()
            if not text:
                continue
            filename = chunk.get("filename") or "素材"
            items.append(f"[{filename}]\n{text[:chunk_chars]}")
        if items:
            buckets.append((section.get("name") or "", items))
    if not buckets:
        return ""

    # 分隔符也占额度，避免最后一章被整段截掉。
    separator = "\n\n"
    share = max(1, (max_chars - len(separator) * (len(buckets) - 1)) // len(buckets))
    blocks: list[str] = []
    for name, items in buckets:
        header = f"【{name}】\n" if name else ""
        room = share - len(header)
        body: list[str] = []
        used = 0
        if room > 0:
            for item in items:
                piece = item[:chunk_chars]
                if not body and len(piece) > room:
                    piece = piece[:room]
                extra = len(piece) + (2 if body else 0)
                if body and used + extra > room:
                    break
                body.append(piece)
                used += extra
        block = (header + "\n\n".join(body))[:share]
        blocks.append(block)
    return separator.join(blocks)


def collect_section_materials(
    documents: list[dict],
    parse_result: Optional[dict],
    chapters: Optional[list] = None,
    retrieve_fn: Optional[Callable] = None,
    per_doc_k: Optional[int] = None,
    max_chars: int = 6000,
) -> str:
    """对每个选中素材、每个章节分别检索，并按章节拼成生成用上下文。"""
    if retrieve_fn is None:
        from server.core.retriever.retriever import retrieve as search
    else:
        search = retrieve_fn

    docs = [doc for doc in documents or [] if isinstance(doc, dict) and doc.get("id") is not None]
    if not docs:
        return ""

    queries = section_retrieval_queries(parse_result, chapters)
    file_k = per_doc_k if per_doc_k is not None else (2 if len(queries) > 1 else 3)
    sections = []
    for item in queries:
        chunks = []
        seen = set()
        for doc in docs:
            hits = search(item["query"], top_k=file_k, doc_ids=[doc["id"]]) or []
            for hit in hits:
                hit_id = hit.get("id")
                if hit_id in seen:
                    continue
                if hit_id is not None:
                    seen.add(hit_id)
                text = (hit.get("text") or "").strip()
                if not text:
                    continue
                chunks.append({
                    "filename": hit.get("filename") or doc.get("filename") or "素材",
                    "text": text,
                })
        sections.append({"name": item["name"], "chunks": chunks})
    return assemble_section_context(sections, max_chars=max_chars)
