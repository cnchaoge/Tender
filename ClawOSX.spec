# -*- mode: python ; coding: utf-8 -*-
import sys, os
from PyInstaller.utils.hooks import collect_all, collect_submodules

block_cipher = None

# 收集所有数据文件
datas = [
    ('web/dist', 'web/dist'),
    ('web/dist/assets', 'web/dist/assets'),
]

# 收集所有 hidden imports
hiddenimports = [
    # FastAPI & uvicorn
    'uvicorn', 'uvicorn.loop', 'uvicorn.loops.auto', 'uvicorn.loops.uvloop',
    'uvicorn.protocols', 'uvicorn.protocols.http', 'uvicorn.protocols.http.auto',
    'uvicorn.protocols.websockets', 'uvicorn.protocols.websockets.auto',
    'uvicorn.lifespan', 'uvicorn.lifespan.auto',
    'fastapi', 'starlette',
    # DB
    'aiosqlite', 'sqlite3',
    # ChromaDB
    'chromadb', 'chromadb.config', 'chromadb.api', 'chromadb.client',
    'chromadb.db', 'chromadb.db.duckdb', 'chromadb.segment',
    'chromadb.segment.impl.vector', 'chromadb.segment.impl.metadata',
    'chromadb.utils.embedding_functions', 'chromadb.utils.embedding_functions._generated',
    'chromadb.api.types', 'chromadb.api.fastapi',
    'hnswlib',
    # ONNX / sentence-transformers (chromadb default embedding)
    'onnxruntime', 'onnxruntime.capi.onnxruntime_inference_collection',
    'sentence_transformers', 'sentence_transformers.models',
    'numpy', 'numpy.core', 'numpy.random',
    # Parsers
    'pdfplumber', 'pdfminer', 'pdfminer.high_level', 'pdfminer.pdfparser',
    'pdfminer.pdfpage', 'pdfminer.pdfdocument', 'pdfminer.pdfinterp',
    'pdfminer.six', 'pdfminer.layout',
    'openpyxl', 'openpyxl.xlsx.reader', 'openpyxl.workbook',
    'docx', 'docx.oxml', 'docx.table', 'docx.text.paragraph',
    'pptx', 'pptx.presentation', 'pptx.util', 'pptx.shapes',
    'markdown_it', 'markdown_it.main', 'markdown_it.rules',
    # RAG / embedding
    'openai', 'dashscope',
    'httpx', 'anyio',
    # Auth
    'passlib', 'passlib.context', 'passlib.hash', 'passlib.hash.bcrypt',
    'bcrypt',
    'jose', 'jose.exceptions',
    'cryptography', 'cryptography.x509', 'cryptography.hazmat',
    # Utils
    'pydantic', 'pydantic.fields', 'pydantic.main', 'pydantic_settings',
    'python_dotenv', 'python_jose',
    'click',
    'yaml', 'yaml.loader',
    # Routers
    'server.api.auth', 'server.api.kb', 'server.api.rag', 'server.api.bid',
    'server.api.feishu', 'server.api.admin', 'server.api.relay',
    'server.db.sqlite', 'server.config',
    'server.core.relay.manager',
    'server.core.parser.document',
]

# 收集 ONNX 模型文件（sentence-transformers / chromadb default embedding）
from PyInstaller.utils.hooks import collect_data_files
datas += collect_data_files('sentence_transformers')
datas += collect_data_files('onnxruntime')


a = Analysis(
    ['server/main.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='ClawOSX',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
