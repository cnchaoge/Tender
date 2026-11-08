"""投标项目。一次投标的解析、版本、报价和清单从这里按 project_id 一起取出。"""

from server.domain.projects.backfill import backfill_projects
from server.domain.projects.service import (
    archive_project,
    attach_document,
    create_project,
    get_project,
    link_price_project,
    list_projects,
    record_parse_snapshot,
    require_project,
    set_materials,
    store_tender_file,
    tender_document_ids,
    update_current_snapshot,
    update_project,
)

__all__ = [
    "archive_project",
    "attach_document",
    "backfill_projects",
    "create_project",
    "get_project",
    "link_price_project",
    "list_projects",
    "record_parse_snapshot",
    "require_project",
    "set_materials",
    "store_tender_file",
    "tender_document_ids",
    "update_current_snapshot",
    "update_project",
]
