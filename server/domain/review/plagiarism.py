"""标书查重调用。相似度规则仍在 plagiarism_checker。"""
from typing import List, Optional

from fastapi import HTTPException

from server.tools.plagiarism_checker import get_plagiarism_checker


def check_plagiarism(bid_content: str, exclude_doc_ids: Optional[List[int]] = None):
    """检测正文与知识库已有标书的相似程度。内容过短时返回 400。"""
    if not bid_content or len(bid_content.strip()) < 100:
        raise HTTPException(status_code=400, detail="标书内容太短，无法进行查重检测")
    checker = get_plagiarism_checker()
    return checker.check(
        bid_content=bid_content,
        exclude_doc_ids=exclude_doc_ids or [],
    )
