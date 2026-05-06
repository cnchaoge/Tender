"""
ClawOS X - 数据模型
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


# ============ 通用 ============
class Resp(BaseModel):
    code: int = 0
    message: str = "ok"
    data: Optional[dict | list | str] = None


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


class BidParseResp(BaseModel):
    project_name: str
    deadline: str
    requirements: List[str]
    qualification: List[str]
    scoring: List[dict]
    raw_text: str


class BidGenerateReq(BaseModel):
    parse_result: dict  # BidParseResp 结果
    materials: List[int]  # 素材文档 ID 列表


# ============ 飞书 ============
class FeishuMessage(BaseModel):
    msg_type: str
    content: dict
    sender: dict


class FeishuConfig(BaseModel):
    app_id: str
    app_name: str
    status: str  # not_configured | connected | error
