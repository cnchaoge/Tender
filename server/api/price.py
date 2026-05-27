"""
Tender - 报价分析计算器 API
"""
import re
import json
from typing import Optional, List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from server.db.sqlite import get_db
from server.core.generator.llm import get_generator

router = APIRouter(prefix="/api/price", tags=["报价分析"])

# ── 模型 ───────────────────────────────────────────────────────────────────


class FormulaInfo(BaseModel):
    method: str = "lowest"          # lowest | average | formula
    weight: float = 30              # 价格分权重
    description: str = ""           # 公式描述
    params: dict = {}              # 具体参数


class PriceCalcReq(BaseModel):
    formula_json: str               # JSON 格式的 FormulaInfo
    cost_price: float               # 成本价
    competitor_count: int = 5       # 假设竞争对手数量


class PriceStrategy(BaseModel):
    name: str
    price: float
    score: float
    profit: float
    profit_margin: float
    rank: int = 0
    is_suggested: bool = False


class PriceCalcResp(BaseModel):
    suggested_price: float
    suggested_score: float
    suggested_profit: float
    strategies: list
    formula_info: dict
    explanation: str


class PriceSaveReq(BaseModel):
    project_name: str
    formula_json: str
    cost_price: float
    suggested_price: float
    calculated_results: str = "{}"
    strategy_scores: str = "[]"


class ParseFormulaReq(BaseModel):
    scoring: dict = {}
    raw_text: str = ""


# ── 公式解析 ───────────────────────────────────────────────────────────────


def _parse_formula_from_scoring(scoring: dict) -> dict:
    """从 parse_result 的 scoring 中提取价格评分公式"""
    method = scoring.get("price_method", "lowest")
    sections = scoring.get("sections", [])

    weight = 30
    formula_text = ""
    for section in sections:
        for item in section.get("items", []):
            if item.get("type") == "formula" and item.get("formula"):
                formula_text = item["formula"]
                weight = item.get("max_score", item.get("score", 30))
                break

    if not formula_text:
        desc_map = {
            "lowest": "价格分 = (最低有效报价 / 投标报价) × 权重",
            "average": "价格分 = (基准价 / 投标报价) × 权重（基准价 = 所有有效报价的算术平均值）",
            "formula": "价格分按公式计算（详见招标文件）",
        }
        description = desc_map.get(method, desc_map["lowest"])
    else:
        description = formula_text

    if method == "lowest":
        params = {"base_price_type": "lowest", "formula_text": formula_text or "(最低报价/投标报价)*权重"}
    elif method == "average":
        params = {"base_price_type": "average", "deduction_k": 0.5, "formula_text": formula_text or "(基准价/投标报价)*权重"}
    else:
        params = {"base_price_type": "lowest", "deduction_k": 0.5, "formula_text": formula_text}

    return {
        "method": method,
        "weight": float(weight),
        "description": description,
        "params": params,
    }


def _calc_score(price: float, base_price: float, method: str, weight: float) -> float:
    """根据评标办法计算单次报价得分"""
    if price <= 0 or base_price <= 0:
        return 0
    if method == "lowest":
        # 价格分 = (最低价 / 投标报价) × 权重
        return round((base_price / price) * weight, 2)
    elif method == "average":
        # 价格分 = (基准价 / 投标报价) × 权重（基准价是平均价）
        return round((base_price / price) * weight, 2)
    else:
        # 综合公式法：默认用最低价法降级
        return round((base_price / price) * weight, 2)


def _generate_strategies(cost_price: float, formula: dict, competitor_count: int = 5) -> list:
    """生成多种报价策略及其得分"""
    method = formula.get("method", "lowest")
    weight = float(formula.get("weight", 30))
    params = formula.get("params", {})

    base_price_type = params.get("base_price_type", "lowest")

    strategies = []
    # 生成 6 种不同报价策略（利润率从低到高）
    ratios = [0.95, 1.00, 1.03, 1.05, 1.08, 1.12]
    labels = ["低价抢标", "成本价", "微利报价", "保守报价", "正常报价", "激进报价"]

    for ratio, label in zip(ratios, labels):
        price = round(cost_price * ratio, 2)

        # 模拟竞争对手
        if competitor_count > 0:
            import random
            random.seed(int(price))
            competitor_prices = [cost_price * (0.92 + random.random() * 0.25) for _ in range(competitor_count)]
            all_prices = competitor_prices + [price]

            if base_price_type == "lowest":
                base_price = min(all_prices)
            else:
                base_price = sum(all_prices) / len(all_prices)
        else:
            base_price = price if base_price_type == "lowest" else cost_price

        score = _calc_score(price, base_price, method, weight)
        profit = round(price - cost_price, 2)
        profit_margin = round((profit / cost_price) * 100, 1) if cost_price > 0 else 0

        strategies.append({
            "name": label,
            "price": price,
            "score": score,
            "profit": profit,
            "profit_margin": profit_margin,
            "is_suggested": False,
        })

    # 排序：分高优先，同分利润高优先
    strategies.sort(key=lambda s: (-s["score"], -s["profit"]))
    for i, s in enumerate(strategies):
        s["rank"] = i + 1

    # 标注建议方案（得分最高且利润为正）
    for s in strategies:
        if s["score"] > 0 and s["profit"] > 0:
            s["is_suggested"] = True
            break

    return strategies


# ── API 端点 ───────────────────────────────────────────────────────────────


@router.post("/parse-formula")
def parse_formula(req: ParseFormulaReq):
    """从招标解析结果中提取价格评分公式"""
    formula = _parse_formula_from_scoring(req.scoring)

    # 如果有原文且缺少具体公式，尝试 LLM 提取
    if req.raw_text and not formula.get("description"):
        try:
            generator = get_generator()
            prompt = f"""从以下招标文件内容中提取价格评分公式。

招标文件内容：
{req.raw_text[:3000]}

请提取价格评分相关的信息，以JSON格式返回：
{{
    "method": "lowest|average|formula",
    "weight": 价格分权重（数字）,
    "description": "公式的文字描述",
    "formula_text": "公式表达式"
}}

只返回JSON，不要其他内容。"""
            raw_llm = generator.generate(prompt, system="你是一个招投标专家，擅长提取价格评分公式。")
            cleaned = raw_llm.strip()
            if cleaned.startswith("```"):
                lines = cleaned.splitlines()
                if lines and lines[0].strip().startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                cleaned = "\n".join(lines)
            result = json.loads(cleaned)
            formula["method"] = result.get("method", formula["method"])
            formula["weight"] = float(result.get("weight", formula["weight"]))
            formula["description"] = result.get("description", result.get("formula_text", ""))
            if result.get("formula_text"):
                formula["params"]["formula_text"] = result["formula_text"]
        except Exception:
            pass

    return {"formula": formula}


@router.post("/calculate", response_model=PriceCalcResp)
def calculate_price(req: PriceCalcReq):
    """根据公式和成本价计算最优报价"""
    try:
        formula = json.loads(req.formula_json) if isinstance(req.formula_json, str) else req.formula_json
    except (json.JSONDecodeError, TypeError):
        formula = {"method": "lowest", "weight": 30, "params": {"base_price_type": "lowest"}}

    strategies = _generate_strategies(req.cost_price, formula, req.competitor_count)
    suggested = next((s for s in strategies if s["is_suggested"]), strategies[0])

    # 生成解释文本
    method_names = {"lowest": "最低价法", "average": "均价法", "formula": "公式法"}
    explanation = (
        f"基于{method_names.get(formula.get('method'), '综合')}评标办法（价格分权重{formula.get('weight', 30)}分），"
        f"建议报价 ¥{suggested['price']:,.2f}，预计得分 {suggested['score']} 分，"
        f"利润 ¥{suggested['profit']:,.2f}（利润率 {suggested['profit_margin']}%）。"
    )

    return PriceCalcResp(
        suggested_price=suggested["price"],
        suggested_score=suggested["score"],
        suggested_profit=suggested["profit"],
        strategies=strategies,
        formula_info=formula,
        explanation=explanation,
    )


@router.post("/save")
def save_analysis(req: PriceSaveReq):
    """保存报价分析记录"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO price_analyses
           (project_name, formula_json, cost_price, suggested_price, calculated_results, strategy_scores)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (req.project_name, req.formula_json, req.cost_price,
         req.suggested_price, req.calculated_results, req.strategy_scores)
    )
    conn.commit()
    aid = cur.lastrowid
    conn.close()
    return {"id": aid, "message": "保存成功"}


@router.get("/history")
def list_history(limit: int = 20):
    """获取历史报价分析记录"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """SELECT id, project_name, cost_price, suggested_price, created_at
           FROM price_analyses ORDER BY created_at DESC LIMIT ?""",
        (limit,)
    )
    rows = cur.fetchall()
    conn.close()
    return {"records": [dict(r) for r in rows]}


@router.get("/history/{aid}")
def get_history_detail(aid: int):
    """获取单条报价分析记录详情"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM price_analyses WHERE id = ?", (aid,))
    row = cur.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="记录不存在")
    result = dict(row)
    for field in ("formula_json", "calculated_results", "strategy_scores"):
        try:
            result[field] = json.loads(result[field])
        except (json.JSONDecodeError, TypeError):
            pass
    return result


@router.delete("/history/{aid}")
def delete_history(aid: int):
    """删除报价分析记录"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM price_analyses WHERE id = ?", (aid,))
    conn.commit()
    deleted = cur.rowcount > 0
    conn.close()
    if not deleted:
        raise HTTPException(status_code=404, detail="记录不存在")
    return {"message": "已删除"}


@router.get("/formula-templates")
def get_formula_templates():
    """返回常见报价公式模板"""
    return {"templates": [
        {
            "name": "最低价法（综合评分）",
            "method": "lowest",
            "weight": 30,
            "description": "价格分 = (最低有效报价 / 投标报价) × 30",
            "params": {"base_price_type": "lowest", "formula_text": "(最低报价/投标报价)*30"},
        },
        {
            "name": "最低价法（商务标）",
            "method": "lowest",
            "weight": 40,
            "description": "价格分 = (最低有效报价 / 投标报价) × 40",
            "params": {"base_price_type": "lowest", "formula_text": "(最低报价/投标报价)*40"},
        },
        {
            "name": "均价法",
            "method": "average",
            "weight": 30,
            "description": "价格分 = (基准价 / 投标报价) × 30（基准价为有效报价的算术平均值）",
            "params": {"base_price_type": "average", "formula_text": "(平均价/投标报价)*30"},
        },
        {
            "name": "均价法（去除最高最低）",
            "method": "average",
            "weight": 30,
            "description": "价格分 = (基准价 / 投标报价) × 30，基准价为去掉最高和最低后的算术平均值",
            "params": {"base_price_type": "average", "trim_extreme": True, "formula_text": "(基准价/投标报价)*30"},
        },
        {
            "name": "综合公式法",
            "method": "formula",
            "weight": 30,
            "description": "价格分 = 30 - |投标价 - 基准价| / 基准价 × 100 × K",
            "params": {"base_price_type": "average", "deduction_k": 0.5, "formula_text": "30 - |投标价-基准价|/基准价*100*0.5"},
        },
    ]}
