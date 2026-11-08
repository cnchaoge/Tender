"""招标文件解析与字段补全。

带 `file_path` 的旧接口保留到阶段 5。内部先找到受管原件再解析。
带 `document_id` 和 `project_id` 时，解析结果写入 ParseSnapshot。
"""
import os
import re
from pathlib import Path

from fastapi import HTTPException

from server.core.generator.llm import get_generator
from server.core.retriever.retriever import retrieve
from server.db.sqlite import get_db
from server.domain.documents.files import relative_to_data, resolve_stored_path
from server.models import BidParseReq, BidParseResp

def _json_clean(raw: str) -> str:
    """去掉 markdown json 包装（```json ... ```）"""
    raw = raw.strip()
    if raw.startswith("```"):
        lines = raw.splitlines()
        # 去掉第一行 ```json 或 ``` 等标记
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        # 去掉最后一行 ```
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        raw = "\n".join(lines)
    return raw.strip()


def _validate_and_fill(result: dict, raw_text: str) -> dict:
    """校验关键字段，缺失时从 raw_text 正则降级提取，注入 warnings"""
    warnings = []

    # project_name：缺失时从 raw_text 前200字尝试提取
    if not result.get("project_name") or result["project_name"] == "解析失败":
        m = re.search(r"项目名称[：:]\s*(.+?)(?:\n|$)", raw_text)
        if m:
            result["project_name"] = m.group(1).strip()
            warnings.append("project_name 从原文正则提取")
        else:
            result["project_name"] = "未识别到项目名称"

    # deadline：缺失时尝试正则
    if not result.get("deadline"):
        patterns = [
            r"工期[：:]\s*(.+?)(?:\n|$)",
            r"交付时间[：:]\s*(.+?)(?:\n|$)",
            r"计划.*?(\d+年\d+月|\d+月\d+日|\d+日)",
        ]
        for pat in patterns:
            m = re.search(pat, raw_text)
            if m:
                result["deadline"] = m.group(1).strip()
                warnings.append("deadline 从原文正则提取")
                break
        if not result.get("deadline"):
            result["deadline"] = ""

    # requirements：确保是列表
    if not isinstance(result.get("requirements"), list):
        result["requirements"] = []
    if not result["requirements"]:
        result["requirements"] = ["未识别到资格要求"]

    # qualification：确保是列表
    if not isinstance(result.get("qualification"), list):
        result["qualification"] = []
    if not result["qualification"]:
        result["qualification"] = ["未识别到资质要求"]

    # scoring：新 dict 结构
    if not isinstance(result.get("scoring"), dict):
        result["scoring"] = {}
    # 如果 LLM 仍返回旧列表结构（向后兼容），包装成新结构
    if "sections" not in result["scoring"] and isinstance(result.get("_raw_scoring_list"), list):
        result["scoring"] = {
            "method": "综合评分法",
            "total_score": 100,
            "sections": [{"name": "评分项", "weight": 100, "items": result.get("_raw_scoring_list", [])}],
            "disqualify_conditions": [],
            "price_method": "average",
        }

    # 计算置信度
    scoring_ok = isinstance(result.get("scoring"), dict) and bool(result["scoring"].get("sections"))
    field_ok = (
        result.get("project_name")
        and result["project_name"] not in ("未识别到项目名称", "解析失败")
        and isinstance(result["requirements"], list)
        and bool(result["requirements"])  # requirements 非空才算成功
        and isinstance(result["qualification"], list)
        and scoring_ok
    )
    if field_ok and not warnings:
        confidence = 0.95
    elif warnings and len(warnings) <= 2:
        confidence = 0.6
    elif warnings:
        confidence = 0.3
    else:
        confidence = 0.5

    result["parse_meta"] = {
        "confidence": confidence,
        "warnings": warnings,
        "health_check": {},  # 由 parse_bid_file 注入
    }
    return result


def _health_check(text: str, file_path: str) -> dict:
    """招标文件体检：轻量版"""
    checks = []

    # 1. 文件可读性：文字量检测
    char_count = len(text.strip())
    if char_count < 200:
        checks.append({"item": "文件可读性", "result": "fail", "detail": "文字量极少（< 200字），可能为扫描件或图片型PDF，建议使用文字版文件"})
    elif char_count < 500:
        checks.append({"item": "文件可读性", "result": "warning", "detail": f"文字量偏少（{char_count}字），可能是扫描件，建议核实"})
    else:
        checks.append({"item": "文件可读性", "result": "pass", "detail": f"文字量正常（{char_count}字）"})

    # 2. 关键章节检测（正则）
    chapter_keywords = ["招标公告", "投标人须知", "技术标准", "评分办法", "合同条款"]
    missing = [kw for kw in chapter_keywords if kw not in text]
    if missing:
        checks.append({"item": "关键章节", "result": "warning", "detail": f"缺少章节：{'、'.join(missing)}"})
    else:
        checks.append({"item": "关键章节", "result": "pass", "detail": "主要章节齐全"})

    # 3. 关键字段存在性检测
    deadline_found = bool(re.search(r"工期|交付时间|计划.*?\d+月", text))
    project_found = bool(re.search(r"项目名称|项目名称[：:]", text))
    scoring_found = bool(re.search(r"评分|评标|得分", text))

    if not project_found:
        checks.append({"item": "关键字段", "result": "warning", "detail": "未找到项目名称相关内容"})
    if not deadline_found:
        checks.append({"item": "关键字段", "result": "warning", "detail": "未找到工期/交付时间"})
    if not scoring_found:
        checks.append({"item": "关键字段", "result": "warning", "detail": "未找到评分标准相关内容"})
    if project_found and deadline_found and scoring_found:
        checks.append({"item": "关键字段", "result": "pass", "detail": "关键字段均已识别"})

    # 整体状态
    fail_count = sum(1 for c in checks if c["result"] == "fail")
    warn_count = sum(1 for c in checks if c["result"] == "warning")
    if fail_count > 0:
        status = "fail"
    elif warn_count >= 2:
        status = "warning"
    elif warn_count == 1:
        status = "warning"
    else:
        status = "pass"

    return {"status": status, "checks": checks}


def _find_document_by_path(file_path: str):
    """file_path 能对上受管副本时返回那一行，解析读的是这份副本。"""
    raw = Path(file_path)
    keys = {file_path}
    if raw.is_absolute():
        try:
            keys.add(relative_to_data(raw))
        except Exception:
            pass
    else:
        keys.add(str(resolve_stored_path(file_path)))
    conn = get_db()
    try:
        cur = conn.cursor()
        for key in keys:
            cur.execute(
                "SELECT * FROM documents WHERE file_path = ? ORDER BY id LIMIT 1",
                (key,),
            )
            row = cur.fetchone()
            if row is not None:
                return row
        if not raw.exists():
            return None
        try:
            resolved = raw.resolve()
        except OSError:
            return None
        cur.execute("SELECT id, file_path FROM documents")
        for item in cur.fetchall():
            stored = resolve_stored_path(item["file_path"])
            try:
                if stored.is_file() and stored.resolve() == resolved:
                    cur.execute("SELECT * FROM documents WHERE id = ?", (item["id"],))
                    return cur.fetchone()
            except OSError:
                continue
        return None
    finally:
        conn.close()


def resolve_parse_source(file_path: str | None, document_id: int | None) -> tuple[str, int | None]:
    """返回 (要解析的路径, 文档 id)。文档 id 优先；旧路径先对受管文件。"""
    if document_id is not None:
        conn = get_db()
        try:
            cur = conn.cursor()
            cur.execute("SELECT * FROM documents WHERE id = ?", (document_id,))
            row = cur.fetchone()
        finally:
            conn.close()
        if row is None:
            raise HTTPException(status_code=404, detail="文件不存在")
        path = resolve_stored_path(row["file_path"])
        if not path.is_file():
            raise HTTPException(status_code=404, detail="文件不存在")
        return str(path), int(document_id)

    if not file_path:
        raise HTTPException(status_code=400, detail="需要 file_path 或 document_id")

    row = _find_document_by_path(file_path)
    if row is not None:
        managed = resolve_stored_path(row["file_path"])
        if managed.is_file():
            return str(managed), int(row["id"])
        if os.path.exists(file_path):
            return file_path, int(row["id"])
    if os.path.exists(file_path):
        return file_path, None
    raise HTTPException(status_code=404, detail="文件不存在")


def parse_bid_file(req: BidParseReq):
    """解析招标文件。项目上的解析会多写一条快照，不覆盖用户改过的项目字段。"""
    path, document_id = resolve_parse_source(req.file_path, req.document_id)
    if req.project_id is not None:
        from server.domain.projects.service import require_project

        require_project(req.project_id)
    resp = _parse_managed_file(path)
    if req.project_id is not None:
        from server.domain.projects.service import record_parse_snapshot

        stored = record_parse_snapshot(req.project_id, document_id, resp.model_dump())
        resp = resp.model_copy(update={
            "project_name": stored["project_name"] if "project_name" in stored else resp.project_name,
            "deadline": stored["deadline"] if "deadline" in stored else resp.deadline,
        })
    return resp


def _parse_managed_file(file_path: str):
    """解析已经落到磁盘上的招标文件。"""
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="文件不存在")

    from server.core.parser.document import parse_file
    text, _ = parse_file(file_path)

    # 招标文件体检（轻量版）
    health = _health_check(text, file_path)

    generator = get_generator()
    prompt = f"""请从以下招标文件中提取关键信息，以JSON格式返回：

招标文件内容：
{text[:8000]}

请提取并返回以下JSON格式（只返回JSON，不要其他内容）：
{{
    "project_name": "项目名称",
    "deadline": "工期/交付时间",
    "requirements": ["资格要求1", "资格要求2"],
    "qualification": ["资质要求1", "资质要求2"],
    "scoring": {{
        "method": "综合评分法|最低价法|经评审的最低价法|性价比法",
        "total_score": 100,
        "sections": [
            {{
                "name": "技术标",
                "weight": 60,
                "items": [
                    {{
                        "name": "评分项名称",
                        "score": 20,
                        "max_score": 20,
                        "type": "expert|formula|qualified",
                        "formula": "(最低报价/投标报价)*20  # type=formula 时填写",
                        "bidirectional": false,
                        "disqualify_if_fail": false,
                        "requirements": ["评委逐项打分"]
                    }}
                ]
            }}
        ],
        "disqualify_conditions": ["资格条件不满足则废标", "工期承诺偏离则废标"],
        "price_method": "lowest|average|formula"
    }}
}}"""

    try:
        raw_llm = generator.generate(prompt, system="你是一个招投标专家，擅长提取招标文件关键信息。")
        import json
        cleaned = _json_clean(raw_llm)
        result = json.loads(cleaned)

        # 字段校验 + 降级提取
        result = _validate_and_fill(result, text[:2000])
        # 注入体检结果
        result["parse_meta"]["health_check"] = health

        # RAG 素材预关联（容错：解析失败时跳过，不阻断主流程）
        project_name = result.get("project_name", "")
        recommended_materials = []
        if not project_name or project_name in ("解析失败", "未识别到项目名称"):
            pass
        else:
            try:
                requirements = result.get("requirements", [])
                req0 = requirements[0] if requirements else ""
                if project_name and req0:
                    query = f"{project_name} {req0}"
                    chunks = retrieve(query, top_k=5)
                    doc_groups = {}
                    for chunk in chunks:
                        doc_id = chunk.get("doc_id")
                        if not doc_id:
                            continue
                        if doc_id not in doc_groups:
                            doc_groups[doc_id] = {
                                "id": doc_id,
                                "filename": chunk.get("filename", ""),
                                "scores": [],
                                "chunks": [],
                            }
                        doc_groups[doc_id]["scores"].append(chunk.get("score", 0.0))
                        if len(doc_groups[doc_id]["chunks"]) < 2:
                            doc_groups[doc_id]["chunks"].append(chunk.get("text", "")[:200])

                    for doc_id, group in doc_groups.items():
                        avg_score = sum(group["scores"]) / len(group["scores"]) if group["scores"] else 0
                        # 用匹配到的关键词片段生成推荐理由
                        query_keywords = [w for w in query.split() if len(w) > 1]
                        matched_keywords = []
                        for c in group["chunks"]:
                            for kw in query_keywords:
                                if kw in c:
                                    matched_keywords.append(kw)
                                    break
                        reason = f"匹配项目：{', '.join(matched_keywords[:3])}" if matched_keywords else "内容相似"
                        recommended_materials.append({
                            "id": doc_id,
                            "filename": group["filename"],
                            "relevance_score": round(avg_score, 2),
                            "relevance_reason": reason,
                            "matched_count": len(group["scores"]),
                            "matched_excerpts": group["chunks"],
                        })
                    # 按相关度降序
                    recommended_materials.sort(key=lambda m: m["relevance_score"], reverse=True)
            except Exception:
                pass

        return BidParseResp(
            raw_text=text[:2000],
            recommended_materials=recommended_materials,
            **{k: v for k, v in result.items()}
        )
    except json.JSONDecodeError:
        # JSON 解析失败，尝试正则降级
        result = {
            "project_name": "未识别到项目名称",
            "deadline": "",
            "requirements": ["解析失败，请检查文件格式"],
            "qualification": [],
            "scoring": [],
        }
        result = _validate_and_fill(result, text[:2000])
        result["parse_meta"]["health_check"] = health
        return BidParseResp(raw_text=text[:2000], parse_meta=result["parse_meta"], **{k: v for k, v in result.items() if k != "parse_meta"})
    except Exception as e:
        return BidParseResp(
            project_name="解析失败",
            deadline="",
            requirements=[f"解析错误: {str(e)}"],
            qualification=[],
            scoring={},
            raw_text=text[:2000],
            parse_meta={"confidence": 0, "warnings": [str(e)], "health_check": health},
        )
