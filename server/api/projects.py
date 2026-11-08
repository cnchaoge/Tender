"""项目、招标文件和素材引用。

列表不按创建人过滤。解析快照和素材选择写在服务器上，刷新生成页不用再调模型。
"""
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

from server.api.kb import (
    _UPLOAD_SUFFIXES,
    _file_type_for_suffix,
    _write_limited,
)
from server.deps import get_current_user
from server.domain.documents.files import incoming_path
from server.domain.projects.service import (
    archive_project,
    attach_document,
    create_project,
    get_project,
    list_projects,
    set_materials,
    store_tender_file,
    update_current_snapshot,
    update_project,
)

router = APIRouter(
    prefix="/api/projects",
    tags=["投标项目"],
    dependencies=[Depends(get_current_user)],
)


class ProjectCreateReq(BaseModel):
    name: str = ""
    purchaser: str = ""
    deadline: str = ""


class ProjectUpdateReq(BaseModel):
    name: Optional[str] = None
    purchaser: Optional[str] = None
    deadline: Optional[str] = None
    status: Optional[str] = None


class AttachDocReq(BaseModel):
    document_id: int
    role: str


class MaterialsReq(BaseModel):
    document_ids: list[int] = []


class SnapshotReq(BaseModel):
    result: dict
    name_edited: bool = False
    deadline_edited: bool = False


@router.get("")
def list_project_rows():
    return list_projects()


@router.post("")
def create_project_row(req: ProjectCreateReq, user: dict = Depends(get_current_user)):
    return create_project(
        name=req.name,
        purchaser=req.purchaser,
        deadline=req.deadline,
        created_by=user["id"],
    )


@router.get("/{project_id}")
def get_project_row(project_id: int):
    return get_project(project_id)


@router.put("/{project_id}")
def update_project_row(project_id: int, req: ProjectUpdateReq):
    fields = req.model_dump(exclude_unset=True)
    return update_project(
        project_id,
        name=req.name,
        purchaser=req.purchaser,
        deadline=req.deadline,
        status=req.status,
        name_set="name" in fields,
        purchaser_set="purchaser" in fields,
        deadline_set="deadline" in fields,
        status_set="status" in fields,
    )


@router.post("/{project_id}/archive")
def archive_project_row(project_id: int):
    return archive_project(project_id)


@router.post("/{project_id}/documents")
def attach_project_document(project_id: int, req: AttachDocReq):
    return attach_document(project_id, req.document_id, req.role)


@router.put("/{project_id}/materials")
def replace_project_materials(project_id: int, req: MaterialsReq):
    return set_materials(project_id, req.document_ids)


@router.put("/{project_id}/snapshot")
def save_project_snapshot(project_id: int, req: SnapshotReq):
    return update_current_snapshot(
        project_id,
        req.result,
        name_edited=req.name_edited,
        deadline_edited=req.deadline_edited,
    )


@router.post("/{project_id}/tender")
async def upload_project_tender(project_id: int, file: UploadFile = File(...)):
    """招标文件单独存放，scope=project，不进入公司资料库和全局问答。"""
    filename = file.filename or "tender"
    suffix = Path(filename).suffix.lower()
    if suffix not in _UPLOAD_SUFFIXES:
        raise HTTPException(status_code=400, detail=f"不支持的文件类型: {suffix}")
    tmp_path = incoming_path(suffix)
    try:
        await _write_limited(file, tmp_path)
    except HTTPException:
        tmp_path.unlink(missing_ok=True)
        raise
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise
    try:
        return store_tender_file(
            project_id,
            filename,
            tmp_path,
            _file_type_for_suffix(suffix),
        )
    except HTTPException:
        tmp_path.unlink(missing_ok=True)
        raise
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise
