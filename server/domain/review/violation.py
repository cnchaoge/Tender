"""废标检查的调用。规则库本身仍在 server.tools / violation_db。"""
from fastapi import HTTPException

from server.tools.violation_checker import get_violation_checker


def check_violations(parse_result, bid_content, raw_text, check_stage):
    """按阶段调用废标检查。缺少正文和解析结果时由路由得到 400。"""
    checker = get_violation_checker()
    stage = check_stage if check_stage != "auto" else None
    if bid_content and parse_result:
        result = checker.check_bid_content(bid_content, parse_result)
    elif bid_content:
        result = checker.check_document(bid_content, stage=stage or "review")
    elif parse_result:
        result = checker.check_parse_result(parse_result, raw_text or "")
    else:
        raise HTTPException(status_code=400, detail="缺少检测内容：bid_content 或 parse_result 二选一")
    return result


def list_disqualify_rules():
    checker = get_violation_checker()
    return checker.get_disqualify_rules()


def list_violation_cases(category=None):
    checker = get_violation_checker()
    return checker.get_violation_cases(category)
