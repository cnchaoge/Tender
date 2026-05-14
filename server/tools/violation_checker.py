"""
ClawOS X - 废标项检查器
招标文件解析阶段 + 标书生成阶段 + 质检阶段的三重合规校验
"""
import re
from typing import Optional
from server.db.sqlite import get_db


class ViolationChecker:
    """
    废标项检查器：基于正则规则 + 违规案例库进行投标合规性检测。
    支持三个阶段：parse(解析后)/generate(生成前)/review(质检)
    """

    def __init__(self):
        self._rules = None
        self._cases = None

    def _load_rules(self):
        """懒加载废标红线规则"""
        if self._rules is not None:
            return
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            SELECT rule_name, trigger_pattern, rule_type, check_stage,
                   severity, description, fix_suggestion
            FROM disqualify_rules WHERE enabled = 1
        """)
        rows = cur.fetchall()
        conn.close()
        self._rules = [dict(r) for r in rows]
        return self._rules

    def _load_cases(self):
        """懒加载违规案例"""
        if self._cases is not None:
            return
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            SELECT category, sub_category, keyword, case_title, penalty, severity
            FROM violation_cases
        """)
        rows = cur.fetchall()
        conn.close()
        self._cases = [dict(r) for r in rows]
        return self._cases

    # ── 公开接口 ────────────────────────────────────────────────────

    def check_document(self, text: str, stage: str = "parse") -> dict:
        """
        检查一段文本，返回违规项列表

        Args:
            text: 待检查的文本内容
            stage: 检查阶段 parse|generate|review

        Returns:
            {
                "passed": bool,            # 是否通过（无必废标项）
                "violations": [
                    {
                        "rule_name": str,
                        "severity": int,    # 1-5
                        "is_disqualify": bool,  # 是否为必废标项
                        "matched_text": str,    # 匹配的文本片段
                        "description": str,
                        "fix_suggestion": str,
                    }
                ],
                "warnings": [
                    {
                        "case_title": str,
                        "category": str,
                        "severity": int,
                        "penalty": str,
                        "matched_keyword": str,
                    }
                ],
                "summary": {
                    "total_violations": int,
                    "disqualify_count": int,  # 必废标数量
                    "high_risk_count": int,    # 高风险（severity >= 4）
                }
            }
        """
        self._load_rules()
        self._load_cases()

        violations = []
        warnings = []

        text_lower = text.lower()

        # ── 规则匹配 ────────────────────────────────────────────────
        for rule in self._rules:
            if rule["check_stage"] != stage and rule["check_stage"] != "all":
                continue
            try:
                pattern = rule["trigger_pattern"]
                matches = re.finditer(pattern, text, re.IGNORECASE)
                for m in matches:
                    matched_text = m.group(0)
                    is_disqualify = rule["severity"] >= 5
                    violations.append({
                        "rule_name": rule["rule_name"],
                        "severity": rule["severity"],
                        "is_disqualify": is_disqualify,
                        "matched_text": matched_text[:100],
                        "description": rule["description"],
                        "fix_suggestion": rule["fix_suggestion"],
                    })
            except re.error:
                continue

        # ── 违规案例关键字匹配 ───────────────────────────────────────
        for case in self._cases:
            keyword = case["keyword"]
            # 支持多pattern（用 | 分隔）
            for pat in keyword.split("|"):
                pat = pat.strip()
                if len(pat) < 3:
                    continue
                if pat.lower() in text_lower:
                    warnings.append({
                        "case_title": case["case_title"],
                        "category": case["category"],
                        "sub_category": case["sub_category"],
                        "severity": case["severity"],
                        "penalty": case["penalty"],
                        "matched_keyword": pat,
                    })

        # ── 高频废标特征专项检测 ─────────────────────────────────────
        extra_violations = self._check_common_pitfalls(text)
        violations.extend(extra_violations)

        # ── 汇总 ─────────────────────────────────────────────────────
        disqualify_count = sum(1 for v in violations if v["is_disqualify"])
        high_risk_count = sum(1 for v in violations if v["severity"] >= 4)

        passed = disqualify_count == 0

        return {
            "passed": passed,
            "violations": violations,
            "warnings": warnings,
            "summary": {
                "total_violations": len(violations),
                "disqualify_count": disqualify_count,
                "high_risk_count": high_risk_count,
            }
        }

    def check_parse_result(self, parse_result: dict, raw_text: str = "") -> dict:
        """
        检查招标文件解析结果

        Args:
            parse_result: BidParseResp 解析结果
            raw_text: 原始招标文件文本（可选，用于全文检测）
        """
        text_parts = []

        # 从 parse_result 提取关键字段拼接检测
        project_name = parse_result.get("project_name", "")
        deadline = parse_result.get("deadline", "")
        requirements = parse_result.get("requirements", [])
        qualification = parse_result.get("qualification", [])
        scoring = parse_result.get("scoring", {})
        raw_text = raw_text or parse_result.get("raw_text", "")

        if raw_text:
            text_parts.append(raw_text)
        else:
            text_parts.append(f"项目名称: {project_name}\n工期: {deadline}")
            text_parts.append("资格要求: " + " ".join(requirements))
            text_parts.append("资质要求: " + " ".join(qualification))

        combined = "\n".join(text_parts)
        return self.check_document(combined, stage="parse")

    def check_bid_content(self, bid_content: str, parse_result: dict) -> dict:
        """
        检查生成的标书正文（生成阶段 + 质检阶段合并）

        Args:
            bid_content: 标书正文（Markdown）
            parse_result: 招标文件解析结果
        """
        # 拼接：标书正文 + 招标文件关键要求（用于一致性检测）
        project_name = parse_result.get("project_name", "")
        deadline = parse_result.get("deadline", "")
        requirements = parse_result.get("requirements", [])
        qualification = parse_result.get("qualification", [])
        scoring_str = str(parse_result.get("scoring", {}))

        combined = (
            f"项目名称: {project_name}\n"
            f"工期承诺: {deadline}\n"
            f"资格要求: {' '.join(requirements)}\n"
            f"资质要求: {' '.join(qualification)}\n"
            f"评分标准: {scoring_str}\n"
            f"标书正文:\n{bid_content}"
        )

        result_generate = self.check_document(bid_content, stage="generate")
        result_review = self.check_document(combined, stage="review")

        # 合并结果（去重）
        violations_map = {}
        for v in result_generate["violations"] + result_review["violations"]:
            key = v["rule_name"]
            if key not in violations_map or v["is_disqualify"]:
                violations_map[key] = v

        warnings_map = {}
        for w in result_generate["warnings"] + result_review["warnings"]:
            key = w["case_title"]
            if key not in warnings_map or w["severity"] >= 5:
                warnings_map[key] = w

        violations = list(violations_map.values())
        warnings = list(warnings_map.values())
        disqualify_count = sum(1 for v in violations if v["is_disqualify"])

        return {
            "passed": disqualify_count == 0,
            "violations": violations,
            "warnings": warnings,
            "summary": {
                "total_violations": len(violations),
                "disqualify_count": disqualify_count,
                "high_risk_count": sum(1 for v in violations if v["severity"] >= 4),
            }
        }

    def _check_common_pitfalls(self, text: str) -> list[dict]:
        """
        高频废标特征专项检测（无需数据库，基于正则）
        这些是招投标中高频踩坑的特征，不在规则库里则快速扫描
        """
        violations = []
        text_lower = text.lower()

        checks = [
            # (检测名称, 正则, 描述, 严重程度, 修复建议)
            ("投标报价低于成本价", r"(低于成本|恶性低价|低于成本价)", "报价明显低于成本价，违反招投标法第33条", 5,
             "重新核算成本，确保报价不低于企业个别成本"),
            ("工期承诺超出招标要求", r"工期[^\n]{0,30}(超长|超出|超过|大于)\s*\d+", "工期承诺超出招标要求", 4,
             "核对招标文件工期要求，调整工期承诺"),
            ("投标文件正本不足", r"正本.{0,5}(不足|缺少|未提供)", "投标文件正本数量不足", 4,
             "按招标文件要求提供足够份数的正本"),
            ("电子投标MAC地址异常", r"MAC\s*(地址|add)", "电子投标文件MAC地址异常，可能触发串标审查", 5,
             "确保每家公司独立制作电子投标文件，必要时更换网络环境"),
            ("分包商无资质", r"分包.{0,20}(无资质|资质不符|不符合)", "分包给无相应资质的分包商，违反建筑法", 4,
             "审查分包商资质，确保符合招标文件要求"),
            ("合同实质性偏离", r"(黑白合同|实质性偏离|背离招标承诺)", "合同条款与招标文件实质性要求偏离", 4,
             "确保合同条款与招标文件保持一致"),
        ]

        for name, pattern, desc, severity, suggestion in checks:
            try:
                if re.search(pattern, text, re.IGNORECASE):
                    violations.append({
                        "rule_name": name,
                        "severity": severity,
                        "is_disqualify": severity >= 5,
                        "matched_text": "",
                        "description": desc,
                        "fix_suggestion": suggestion,
                    })
            except re.error:
                continue

        return violations

    def get_disqualify_rules(self) -> list[dict]:
        """返回所有启用的废标红线规则（供管理后台展示）"""
        self._load_rules()
        return self._rules

    def get_violation_cases(self, category: str = None) -> list[dict]:
        """返回违规案例，可按 category 过滤"""
        self._load_cases()
        if category:
            return [c for c in self._cases if c["category"] == category]
        return self._cases


# 单例
_checker = None


def get_violation_checker() -> ViolationChecker:
    global _checker
    if _checker is None:
        _checker = ViolationChecker()
    return _checker