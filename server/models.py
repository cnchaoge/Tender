"""
ClawOS X - 数据模型
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Union, Dict, Any
from datetime import datetime


# ============ 通用 ============
class Resp(BaseModel):
    code: int = 0
    message: str = "ok"
    data: Optional[Union[dict, list, str]] = None


# ============ 认证 ============
class LoginReq(BaseModel):
    username: str
    password: str


class LoginResp(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


class UserInfo(BaseModel):
    id: int
    username: str
    role: str  # admin | user
    created_at: str


# ============ 文档 ============
class Document(BaseModel):
    id: int
    filename: str
    file_type: str  # pdf | docx | md | txt
    file_size: int  # bytes
    chunk_count: int
    status: str  # processing | ready | error
    created_at: str
    updated_at: str


class Chunk(BaseModel):
    id: int
    doc_id: int
    chunk_index: int
    text: str
    metadata: dict  # {page, source}


# ============ RAG ============
class QueryReq(BaseModel):
    question: str
    top_k: int = 5
    stream: bool = False


class QueryResp(BaseModel):
    answer: str
    sources: List[dict]  # [{doc_id, filename, chunk_index, text, score}]


# ============ 标书 ============
class BidParseReq(BaseModel):
    file_path: str  # 已在服务端的文件路径


class ScoringItem(BaseModel):
    name: str
    score: float
    max_score: float
    type: str = "expert"   # expert=专家打分, formula=公式计算, qualified=满足即得分
    formula: str = ""       # type=formula 时填写计算公式
    bidirectional: bool = False  # True=偏离扣分, False=正向得分
    disqualify_if_fail: bool = False  # 不满足即废标
    requirements: List[str] = []  # 补充说明，如 ["评委逐项打分", "保留一位小数"]


class ScoringSection(BaseModel):
    name: str             # 如"技术标"、"商务标"
    weight: float         # 占比，如 60（表示60%）
    items: List[ScoringItem] = []


class BidParseResp(BaseModel):
    project_name: str
    deadline: str
    requirements: List[str]
    qualification: List[str]
    scoring: dict = {}    # {method, total_score, sections, disqualify_conditions, price_method}
    raw_text: str
    recommended_materials: List[dict] = []
    parse_meta: dict = {}  # {confidence: float, warnings: List[str]}


class BidGenerateReq(BaseModel):
    parse_result: dict  # BidParseResp 结果
    materials: List[int]  # 素材文档 ID 列表


class BidMatchCheckReq(BaseModel):
    parse_result: dict  # BidParseResp 结果
    materials: List[int]  # 待检测的素材文档 ID 列表


class BidPlanReq(BaseModel):
    parse_result: dict  # BidParseResp 结果
    materials: List[int]  # 素材文档 ID 列表


class BidPlanResp(BaseModel):
    chapters: List[dict]  # [{name: str, description: str}]


# ============ 标书质检 ============
class BidReviewResult(BaseModel):
    passed: bool                    # 是否通过
    score: float                    # 质量评分 0-100
    issues: List[str]              # 发现的问题列表
    suggestions: List[str]          # 修改建议
    coverage_check: dict            # 资质要求覆盖情况
