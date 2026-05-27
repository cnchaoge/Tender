"""
Tender - 投标材料检查清单 API
"""
import re
import json
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from server.db.sqlite import get_db

router = APIRouter(prefix="/api/checklist", tags=["检查清单"])


class ChecklistItemUpdate(BaseModel):
    status: Optional[str] = None
    remark: Optional[str] = None


class ChecklistItemCreate(BaseModel):
    bid_version_id: int
    category: str = "其他"
    item: str
    status: str = "待准备"
    remark: str = ""


class ChecklistGenerateReq(BaseModel):
    bid_version_id: int
    bid_content: str = ""
    parse_result: Optional[dict] = None


# ── 清单自动生成规则 ───────────────────────────────────────────────────────

_CATEGORY_ORDER = ["盖章页", "签字页", "资质证书", "财务证明", "业绩证明", "其他"]


def _checklist_rules() -> list:
    """返回默认检查项列表（按分类）"""
    return [
        # 盖章页
        ("盖章页", "投标函（加盖公章）"),
        ("盖章页", "报价一览表（加盖公章）"),
        ("盖章页", "法定代表人身份证明（加盖公章）"),
        ("盖章页", "营业执照副本复印件（加盖公章）"),
        ("盖章页", "投标保证金缴纳凭证（加盖财务章）"),
        # 签字页
        ("签字页", "投标函（法定代表人或授权代表签字）"),
        ("签字页", "授权委托书（法定代表人签字）"),
        ("签字页", "投标承诺书（签字）"),
        # 资质证书
        ("资质证书", "营业执照（在有效期内）"),
        ("资质证书", "特种设备制造许可证（压力管道元件）"),
        ("资质证书", "API 会标使用许可证"),
        ("资质证书", "ISO 9001 质量管理体系认证"),
        ("资质证书", "ISO 14001 环境管理体系认证"),
        ("资质证书", "ISO 45001 职业健康安全管理体系认证"),
        # 财务证明
        ("财务证明", "近三年审计报告/财务报表"),
        ("财务证明", "银行资信证明"),
        ("财务证明", "纳税信用等级证明"),
        ("财务证明", "近半年社保缴纳记录"),
        # 业绩证明
        ("业绩证明", "近三年同类项目业绩合同（关键页）"),
        ("业绩证明", "验收报告/用户评价证明"),
        ("业绩证明", "中标通知书复印件"),
        # 其他
        ("其他", "信用中国报告（近一个月内）"),
        ("其他", "无行贿犯罪记录证明"),
        ("其他", "产品质量检测报告"),
    ]


def _extract_items_from_bid(content: str, parse_result: Optional[dict] = None) -> list:
    """从标书内容和解析结果中提取匹配的检查项"""
    items = []
    seen = set()

    # 默认检查项
    for cat, item_text in _checklist_rules():
        key = f"{cat}|{item_text}"
        items.append({
            "category": cat,
            "item": item_text,
            "source": "auto",
            "status": "待准备",
            "remark": "",
            "sort_order": _category_sort(cat),
        })
        seen.add(key)

    # 从 parse_result 的资格要求和资质要求中添加自定义项
    if parse_result:
        requirements = parse_result.get("requirements", [])
        qualification = parse_result.get("qualification", [])

        for req in requirements:
            if req and "未识别" not in req:
                key = f"资质证书|{req}"
                if key not in seen:
                    items.append({
                        "category": "资质证书",
                        "item": req,
                        "source": "auto",
                        "status": "待准备",
                        "remark": "招标文件资格要求",
                        "sort_order": _category_sort("资质证书"),
                    })
                    seen.add(key)

        for qual in qualification:
            if qual and "未识别" not in qual:
                key = f"资质证书|{qual}"
                if key not in seen:
                    items.append({
                        "category": "资质证书",
                        "item": qual,
                        "source": "auto",
                        "status": "待准备",
                        "remark": "招标文件资质要求",
                        "sort_order": _category_sort("资质证书"),
                    })
                    seen.add(key)

    # 从标书正文中检测需要盖章/签字的章节
    if content:
        content_lower = content.lower()
        # 检测是否有授权委托书
        if "授权委托书" in content and "授权委托书（法定代表人签字）|授权委托书|签字页" not in str(seen):
            items.append({
                "category": "签字页",
                "item": "授权委托书（法定代表人签字）",
                "source": "auto",
                "status": "待准备",
                "remark": "标书包含授权委托书章节",
                "sort_order": _category_sort("签字页"),
            })

        # 检测是否有投标保证金
        if "保证金" in content:
            items.append({
                "category": "盖章页",
                "item": "投标保证金缴纳凭证（加盖财务章）",
                "source": "auto",
                "status": "待准备",
                "remark": "标书包含投标保证金章节",
                "sort_order": _category_sort("盖章页"),
            })

    return items


def _category_sort(cat: str) -> int:
    try:
        return _CATEGORY_ORDER.index(cat)
    except ValueError:
        return 99


# ── API 端点 ───────────────────────────────────────────────────────────────


@router.post("/generate")
def generate_checklist(req: ChecklistGenerateReq):
    """根据标书内容自动生成检查清单"""
    items = _extract_items_from_bid(req.bid_content, req.parse_result)
    vid = req.bid_version_id

    # 删除该版本的旧 auto 项
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM checklist_items WHERE bid_version_id = ? AND source = 'auto'",
        (vid,)
    )

    # 插入新项
    for item in items:
        cur.execute(
            """INSERT INTO checklist_items
               (bid_version_id, category, item, status, remark, source, sort_order)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (vid, item["category"], item["item"],
             item["status"], item["remark"], item["source"], item["sort_order"])
        )
    conn.commit()
    conn.close()
    return {"count": len(items), "message": f"已生成 {len(items)} 项检查清单"}


@router.get("/categories")
def get_categories():
    """获取分类列表"""
    return {"categories": _CATEGORY_ORDER}


@router.get("/{bid_version_id}")
def get_checklist(bid_version_id: int):
    """获取指定标书版本的检查清单"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """SELECT id, bid_version_id, category, item, status, remark, source, sort_order, created_at
           FROM checklist_items WHERE bid_version_id = ?
           ORDER BY sort_order ASC, id ASC""",
        (bid_version_id,)
    )
    rows = cur.fetchall()
    conn.close()
    return {"items": [dict(r) for r in rows]}


@router.put("/item/{item_id}")
def update_item(item_id: int, req: ChecklistItemUpdate):
    """更新检查项状态或备注"""
    conn = get_db()
    cur = conn.cursor()
    fields = []
    values = []
    if req.status is not None:
        fields.append("status = ?")
        values.append(req.status)
    if req.remark is not None:
        fields.append("remark = ?")
        values.append(req.remark)
    if not fields:
        conn.close()
        return {"message": "无变更"}
    values.append(item_id)
    cur.execute(
        f"UPDATE checklist_items SET {', '.join(fields)} WHERE id = ?",
        values
    )
    conn.commit()
    conn.close()
    return {"message": "更新成功"}


@router.post("/item")
def add_item(req: ChecklistItemCreate):
    """手动添加检查项"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO checklist_items
           (bid_version_id, category, item, status, remark, source, sort_order)
           VALUES (?, ?, ?, ?, ?, 'manual', ?)""",
        (req.bid_version_id, req.category, req.item, req.status, req.remark,
         _category_sort(req.category))
    )
    conn.commit()
    item_id = cur.lastrowid
    conn.close()
    return {"id": item_id, "message": "添加成功"}


@router.delete("/item/{item_id}")
def delete_item(item_id: int):
    """删除检查项"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM checklist_items WHERE id = ?", (item_id,))
    conn.commit()
    deleted = cur.rowcount > 0
    conn.close()
    if not deleted:
        raise HTTPException(status_code=404, detail="检查项不存在")
    return {"message": "已删除"}


@router.get("/export/{bid_version_id}")
def export_checklist(bid_version_id: int):
    """获取导出数据（前端打印成 PDF）"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """SELECT category, item, status, remark FROM checklist_items
           WHERE bid_version_id = ? ORDER BY sort_order ASC, id ASC""",
        (bid_version_id,)
    )
    rows = cur.fetchall()
    conn.close()

    if not rows:
        raise HTTPException(status_code=404, detail="清单为空")

    # 按分类分组
    grouped = {}
    for r in rows:
        cat = r["category"]
        if cat not in grouped:
            grouped[cat] = []
        grouped[cat].append({
            "item": r["item"],
            "status": r["status"],
            "remark": r["remark"],
        })

    # 统计数据
    total = len(rows)
    prepared = sum(1 for r in rows if r["status"] == "已准备")
    not_applicable = sum(1 for r in rows if r["status"] == "不适用")
    pending = total - prepared - not_applicable

    return {
        "categories": grouped,
        "summary": {
            "total": total,
            "prepared": prepared,
            "not_applicable": not_applicable,
            "pending": pending,
            "ready": prepared + not_applicable,
        }
    }
