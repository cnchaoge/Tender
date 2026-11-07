"""全局标书模板。选用模板只影响本次目录，模板本身不进项目。"""
import json
from typing import Optional

from fastapi import HTTPException

from server.db.sqlite import get_db
from server.models import BidTemplateCreateReq, BidTemplateUpdateReq

def list_templates(category: Optional[str] = None):
    """获取标书模板列表，可按分类筛选"""
    conn = get_db()
    cur = conn.cursor()
    if category:
        cur.execute(
            """SELECT id, name, category, industry, description, chapters, default_strategy,
                      is_builtin, created_at, updated_at
               FROM bid_templates WHERE category = ?
               ORDER BY is_builtin DESC, id ASC""",
            (category,)
        )
    else:
        cur.execute(
            """SELECT id, name, category, industry, description, chapters, default_strategy,
                      is_builtin, created_at, updated_at
               FROM bid_templates
               ORDER BY is_builtin DESC, id ASC"""
        )
    rows = cur.fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        try:
            d["chapters"] = json.loads(d["chapters"])
        except (json.JSONDecodeError, TypeError):
            d["chapters"] = []
        result.append(d)
    return {"templates": result}


def get_template(template_id: int):
    """获取单个模板详情"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """SELECT id, name, category, industry, description, chapters, default_strategy,
                  is_builtin, created_at, updated_at
           FROM bid_templates WHERE id = ?""",
        (template_id,)
    )
    row = cur.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="模板不存在")
    d = dict(row)
    try:
        d["chapters"] = json.loads(d["chapters"])
    except (json.JSONDecodeError, TypeError):
        d["chapters"] = []
    return d


def create_template(req: BidTemplateCreateReq):
    """创建自定义模板"""
    conn = get_db()
    cur = conn.cursor()
    chapters_json = json.dumps([ch.model_dump() if hasattr(ch, 'model_dump') else ch for ch in req.chapters], ensure_ascii=False)
    cur.execute(
        """INSERT INTO bid_templates (name, category, industry, description, chapters, default_strategy, is_builtin)
           VALUES (?, ?, ?, ?, ?, ?, 0)""",
        (req.name, req.category, req.industry, req.description, chapters_json, req.default_strategy)
    )
    conn.commit()
    template_id = cur.lastrowid
    conn.close()
    return {"id": template_id, "message": "模板创建成功"}


def update_template(template_id: int, req: BidTemplateUpdateReq):
    """更新自定义模板"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id FROM bid_templates WHERE id = ? AND is_builtin = 0", (template_id,))
    if not cur.fetchone():
        raise HTTPException(status_code=403, detail="内置模板不可修改")

    fields = []
    values = []
    if req.name is not None:
        fields.append("name = ?")
        values.append(req.name)
    if req.category is not None:
        fields.append("category = ?")
        values.append(req.category)
    if req.industry is not None:
        fields.append("industry = ?")
        values.append(req.industry)
    if req.description is not None:
        fields.append("description = ?")
        values.append(req.description)
    if req.chapters is not None:
        chapters_json = json.dumps([ch.model_dump() if hasattr(ch, 'model_dump') else ch for ch in req.chapters], ensure_ascii=False)
        fields.append("chapters = ?")
        values.append(chapters_json)
    if req.default_strategy is not None:
        fields.append("default_strategy = ?")
        values.append(req.default_strategy)

    if not fields:
        return {"message": "无变更"}

    fields.append("updated_at = CURRENT_TIMESTAMP")
    values.append(template_id)
    cur.execute(
        f"UPDATE bid_templates SET {', '.join(fields)} WHERE id = ?",
        values
    )
    conn.commit()
    conn.close()
    return {"message": "模板更新成功"}


def delete_template(template_id: int):
    """删除自定义模板"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id FROM bid_templates WHERE id = ? AND is_builtin = 0", (template_id,))
    if not cur.fetchone():
        raise HTTPException(status_code=403, detail="内置模板不可删除")
    cur.execute("DELETE FROM bid_templates WHERE id = ?", (template_id,))
    conn.commit()
    conn.close()
    return {"message": "模板已删除"}


def _init_builtin_templates():
    """初始化内置模板（仅在首次启动时写入）"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM bid_templates WHERE is_builtin = 1")
    count = cur.fetchone()[0]
    if count > 0:
        conn.close()
        return

    templates = [
        {
            "name": "设备采购技术标",
            "category": "设备采购技术标",
            "industry": "石油石化/钢管管件",
            "description": "适用于钢管管件等物资采购项目的技术投标文件，覆盖资质、技术方案、质量标准和售后服务等核心章节",
            "default_strategy": "技术优先型",
            "chapters": [
                {"name": "投标函", "description": "投标总报价、交货期承诺、质量承诺、投标有效期等", "key_points": "报价有效期通常为90天，交货期承诺需满足招标要求"},
                {"name": "法定代表人身份证明及授权委托书", "description": "法定代表人身份证明、授权委托书及被授权人身份证明", "key_points": "需加盖公章，授权委托书需明确授权范围"},
                {"name": "投标人资格审查资料", "description": "营业执照、特种设备制造许可证（压力管道元件）、API认证、ISO体系证书等", "key_points": "证书需在有效期内，覆盖招标范围"},
                {"name": "企业概况与业绩", "description": "公司简介、生产能力、近三年石油石化行业供货业绩（含合同复印件）", "key_points": "业绩合同需提供关键页，金额和型号清晰可见"},
                {"name": "技术方案", "description": "生产工艺流程、关键工序质量控制、技术路线说明", "key_points": "突出钢管管件生产工艺优势，从原材料到成品全过程描述"},
                {"name": "产品技术参数响应", "description": "按招标文件技术要求逐条响应，涵盖材质、壁厚、公差、防腐层等", "key_points": "逐条对应招标技术规格书，标注符合/优于/偏离"},
                {"name": "质量标准与检测", "description": "执行标准、出厂检验项目、第三方检测报告、质量保证期", "key_points": "列出执行的国标/行标/企标清单"},
                {"name": "生产进度与交货计划", "description": "生产排产计划表、产能保障措施", "key_points": "需有具体时间节点和产能数据支撑"},
                {"name": "包装运输方案", "description": "包装标准、管端保护方式、运输方案、货物追踪", "key_points": "钢管管件包装需符合石油行业运输要求"},
                {"name": "售后服务承诺", "description": "质保期服务、现场技术支持、响应时间", "key_points": "中石油项目通常要求24小时响应"},
                {"name": "近年财务状况", "description": "近三年资产负债表、利润表、银行资信证明", "key_points": "财务状况需良好，资产负债率通常要求低于70%"},
                {"name": "其他证明材料", "description": "信用中国报告、纳税证明、社保记录、无行贿记录证明", "key_points": "信用报告需为近一个月内查询结果"}
            ]
        },
        {
            "name": "设备采购商务标",
            "category": "设备采购商务标",
            "industry": "石油石化/钢管管件",
            "description": "适用于钢管管件等物资采购项目的商务投标文件，重点覆盖报价明细和商务条款响应",
            "default_strategy": "成本控制型",
            "chapters": [
                {"name": "投标函", "description": "投标总价、分项报价汇总、增值税率、投标有效期", "key_points": "大小写金额必须一致，税率按最新政策填写"},
                {"name": "法定代表人授权委托书", "description": "授权委托书、被授权人身份证明", "key_points": "需附被授权人身份证复印件并加盖公章"},
                {"name": "分项报价表", "description": "按规格逐项报价，含规格、材质、数量、单价、总价、防腐加工费", "key_points": "逐项填写，合计总价与投标函一致"},
                {"name": "价格构成分析", "description": "原材料成本、加工费、管理费、利润、运费的明细构成", "key_points": "分析合理，避免畸高畸低引起评委质疑"},
                {"name": "商务条款响应", "description": "对付款方式、履约保证金、质保金、发票类型等逐条响应", "key_points": "偏离项需在偏离表中说明"},
                {"name": "投标保证金", "description": "保证金缴纳凭证（银行保函或电汇回单）", "key_points": "金额和有效期需满足招标文件要求"},
                {"name": "制造商授权书", "description": "代理商投标时需提供制造商针对本项目的唯一授权", "key_points": "仅代理商投标时需要"},
                {"name": "近年审计报告", "description": "经审计的财务报告关键页", "key_points": "需加盖审计机构印章"},
                {"name": "偏离表", "description": "技术/商务偏离说明", "key_points": "无偏离请填写'无偏离'"}
            ]
        }
    ]

    for t in templates:
        chapters_json = json.dumps(t["chapters"], ensure_ascii=False)
        cur.execute(
            """INSERT INTO bid_templates (name, category, industry, description, chapters, default_strategy, is_builtin)
               VALUES (?, ?, ?, ?, ?, ?, 1)""",
            (t["name"], t["category"], t["industry"], t["description"], chapters_json, t["default_strategy"])
        )
    conn.commit()
    conn.close()
    print(f"[Templates] 已初始化 {len(templates)} 套内置模板")
