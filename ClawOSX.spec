# -*- mode: python ; coding: utf-8 -*-
import sys, os
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

block_cipher = None

# ChromaDB 所有子模块（含 _generated, embedding_functions 等）
chromadb_submodules = collect_submodules('chromadb')

# 收集所有数据文件
datas = [
    ('web/dist', 'web/dist'),
    ('web/dist/assets', 'web/dist/assets'),
]

# sentence-transformers 模型文件
datas += collect_data_files('sentence_transformers')
datas += collect_data_files('onnxruntime')
datas += collect_data_files('tokenizers')
datas += collect_data_files('PIL')
datas += collect_data_files('pystray')

# hidden imports
_base_hiddenimports = [
    # FastAPI & uvicorn
    'uvicorn', 'uvicorn.loop', 'uvicorn.loops.auto', 'uvicorn.loops.uvloop',
    'uvicorn.protocols', 'uvicorn.protocols.http', 'uvicorn.protocols.http.auto',
    'uvicorn.protocols.websockets', 'uvicorn.protocols.websockets.auto',
    'uvicorn.lifespan', 'uvicorn.lifespan.auto',
    'fastapi', 'starlette',
    # DB
    'aiosqlite', 'sqlite3',
    # Parsers
    'pdfplumber', 'pdfminer', 'pdfminer.high_level', 'pdfminer.pdfparser',
    'pdfminer.pdfpage', 'pdfminer.pdfdocument', 'pdfminer.pdfinterp',
    'pdfminer.six', 'pdfminer.layout',
    'openpyxl', 'openpyxl.xlsx.reader', 'openpyxl.workbook',
    'docx', 'docx.oxml', 'docx.table', 'docx.text.paragraph',
    'pptx', 'pptx.presentation', 'pptx.util', 'pptx.shapes',
    'markdown_it', 'markdown_it.main', 'markdown_it.rules',
    # ONNX / sentence-transformers (chromadb default embedding)
    'onnxruntime', 'onnxruntime.capi.onnxruntime_inference_collection',
    'sentence_transformers', 'sentence_transformers.models',
    'tokenizers', 'tokenizers.implementations', 'tokenizers.models',
    'filelock', 'huggingface_hub',
    'numpy', 'numpy.core', 'numpy.random',
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
    'server.core.tray',
    # Tray
    'pystray', 'pystray._win32', 'pystray._util',
    'PIL', 'PIL.Image', 'PIL.ImageDraw', 'PIL._imaging',
]

# 合并 chromadb 所有子模块（去重）
hiddenimports = _base_hiddenimports.copy()
for m in chromadb_submodules:
    if m not in hiddenimports:
        hiddenimports.append(m)

# 强制收集 parser 包（PyInstaller 可能漏掉）
for _pkg in ['pdfplumber', 'openpyxl', 'docx', 'pptx', 'markdown_it', 'markdown_it.main']:
    try:
        datas += collect_data_files(_pkg)
    except Exception:
        pass

a = Analysis(
    ['server/main.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
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
