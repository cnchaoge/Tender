"""Background scheduling for knowledge-base document processing.

Parse, OCR, and embedding are slow and call native libraries. They must not
run on the asyncio event loop, and they should not occupy FastAPI's shared
thread pool (that pool also runs synchronous routes). A small dedicated
``ThreadPoolExecutor`` accepts the job and returns immediately, so
``POST /api/kb/documents`` and folder import can respond with ``pending``
while the work continues.

This stays in-process, on the interpreter that is already serving the API:

* There is no machine-specific Python path. The previous worker launched
  ``/Library/Developer/CommandLineTools/.../Python``, which does not exist on
  Linux or Windows.
* A subprocess of ``sys.executable`` is the wrong fallback for the packaged
  app: under PyInstaller that executable is Tender itself, so spawning it
  starts another copy of the server instead of a worker.
* Threads share the SQLite file (connections already use
  ``check_same_thread=False``) and can roll back a failed document without
  coordinating a second process. Chroma writes are serialized with
  ``write_lock`` in the worker.

A process pool would isolate native crashes, but Chroma's persistent client
plus SQLite from spawned interpreters is easy to corrupt, and it is not
required to keep the request handler non-blocking.
"""
from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

logger = logging.getLogger(__name__)

_MAX_WORKERS = 2
_executor: Optional[ThreadPoolExecutor] = None
_executor_lock = threading.Lock()


def get_executor() -> ThreadPoolExecutor:
    global _executor
    with _executor_lock:
        if _executor is None:
            _executor = ThreadPoolExecutor(
                max_workers=_MAX_WORKERS,
                thread_name_prefix="kb-doc",
            )
        return _executor


def schedule_document(doc_id: int, file_path: str) -> None:
    """Queue one document. Returns as soon as the job is accepted."""
    get_executor().submit(run_document, doc_id, file_path)


def run_document(doc_id: int, file_path: str) -> None:
    from server.workers import document_worker

    try:
        document_worker.process_document(doc_id, file_path)
    except Exception:
        logger.exception("document worker crashed doc_id=%s", doc_id)
        try:
            document_worker.cleanup_partial_document(doc_id)
        except Exception:
            logger.exception("cleanup after crash failed doc_id=%s", doc_id)


def schedule_reindex(build_id: int) -> None:
    """Queue an index rebuild on the same in-process pool as document ingest."""
    get_executor().submit(run_reindex, build_id)


def run_reindex(build_id: int) -> None:
    from server.domain.documents.index_build import execute_rebuild

    try:
        execute_rebuild(build_id)
    except Exception:
        logger.exception("index rebuild crashed build_id=%s", build_id)


def shutdown_executor(wait: bool = False) -> None:
    global _executor
    with _executor_lock:
        executor = _executor
        _executor = None
    if executor is not None:
        executor.shutdown(wait=wait, cancel_futures=True)
