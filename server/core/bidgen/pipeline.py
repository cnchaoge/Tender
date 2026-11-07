"""兼容导出。实现在 server.domain.generation.draft。"""
from server.domain.generation.draft import (
    SYSTEM_PROMPT,
    BidDraftPipeline,
    build_bid_info,
    build_generation_prompt,
    chapter_lookup,
    format_scoring,
    match_heading_chapter,
    review_retry_prompt,
    strategy_guidance,
)

__all__ = [
    "SYSTEM_PROMPT",
    "BidDraftPipeline",
    "build_bid_info",
    "build_generation_prompt",
    "chapter_lookup",
    "format_scoring",
    "match_heading_chapter",
    "review_retry_prompt",
    "strategy_guidance",
]
