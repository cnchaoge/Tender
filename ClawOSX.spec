# -*- mode: python ; coding: utf-8 -*-
import sys, os
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

block_cipher = None

chromadb_submodules = collect_submodules('chromadb')

datas = [
    ('web/dist', 'web/dist'),
    ('web/dist/assets', 'web/dist/assets'),
]

datas += collect_data_files('sentence_transformers')
datas += collect_data_files('transformers')
datas += collect_data_files('scipy')
datas += collect_data_files('onnxruntime')
datas += collect_data_files('tokenizers')
datas += collect_data_files('PIL')
datas += collect_data_files('pystray')
datas += collect_data_files('huggingface_hub')
datas += collect_data_files('filelock')

_base_hiddenimports = [
    'uvicorn', 'uvicorn.loop', 'uvicorn.loops.auto', 'uvicorn.loops.uvloop',
    'uvicorn.protocols', 'uvicorn.protocols.http', 'uvicorn.protocols.http.auto',
    'uvicorn.protocols.websockets', 'uvicorn.protocols.websockets.auto',
    'uvicorn.lifespan', 'uvicorn.lifespan.auto',
    'fastapi', 'starlette',
    'aiosqlite', 'sqlite3',
    'pdfplumber', 'pdfminer', 'pdfminer.high_level', 'pdfminer.pdfparser',
    'pdfminer.pdfpage', 'pdfminer.pdfdocument', 'pdfminer.pdfinterp',
    'pdfminer.six', 'pdfminer.layout',
    'openpyxl', 'openpyxl.xlsx.reader', 'openpyxl.workbook',
    'docx', 'docx.oxml', 'docx.table', 'docx.text.paragraph',
    'pptx', 'pptx.presentation', 'pptx.util', 'pptx.shapes',
    'markdown_it', 'markdown_it.main', 'markdown_it.rules',
    'onnxruntime', 'onnxruntime.capi.onnxruntime_inference_collection',
    'sentence_transformers', 'sentence_transformers.models',
    'tokenizers', 'tokenizers.implementations', 'tokenizers.models',
    'filelock', 'huggingface_hub',
    'numpy', 'numpy.core', 'numpy.random',
    'numpy._core', 'numpy._core._multiarray_umath',
    'numpy._core._exceptions', 'numpy._core.multiarray',
    'openai', 'dashscope',
    'httpx', 'anyio',
    'passlib', 'passlib.context', 'passlib.hash', 'passlib.hash.bcrypt',
    'bcrypt',
    'jose', 'jose.exceptions',
    'cryptography', 'cryptography.x509', 'cryptography.hazmat',
    'pydantic', 'pydantic.fields', 'pydantic.main', 'pydantic_settings',
    'python_dotenv', 'python_jose',
    'click',
    'yaml', 'yaml.loader',
    'server.api.auth', 'server.api.kb', 'server.api.rag', 'server.api.bid',
    'server.api.feishu', 'server.api.admin', 'server.api.relay',
    'server.db.sqlite', 'server.config',
    'server.core.relay.manager',
    'server.core.parser.document',
    'server.core.tray',
    'pystray', 'pystray._win32', 'pystray._util',
    'PIL', 'PIL.Image', 'PIL.ImageDraw', 'PIL._imaging',
]

hiddenimports = _base_hiddenimports.copy()
for m in chromadb_submodules:
    if m not in hiddenimports:
        hiddenimports.append(m)

try:
    transformers_submodules = collect_submodules('transformers')
    for m in transformers_submodules:
        if m not in hiddenimports:
            hiddenimports.append(m)
except Exception:
    pass

try:
    from PyInstaller.utils.hooks import collect_all
    np_data, np_hidden = collect_all('numpy')
    datas += np_data
    hiddenimports += np_hidden
except Exception as e:
    print(f"numpy collect_all failed: {e}")

try:
    from PyInstaller.utils.hooks import collect_all
    scipy_data, scipy_hidden = collect_all('scipy')
    datas += scipy_data
    hiddenimports += scipy_hidden
except Exception as e:
    print(f"scipy collect_all failed: {e}")

try:
    from PyInstaller.utils.hooks import collect_all
    st_data, st_hidden = collect_all('sentence_transformers')
    datas += st_data
    hiddenimports += st_hidden
except Exception as e:
    print(f"sentence_transformers collect_all failed: {e}")

try:
    from PyInstaller.utils.hooks import collect_all
    tf_data, tf_hidden = collect_all('transformers')
    datas += tf_data
    hiddenimports += tf_hidden
except Exception as e:
    print(f"transformers collect_all failed: {e}")

try:
    from PyInstaller.utils.hooks import collect_all
    torch_data, torch_hidden = collect_all('torch')
    datas += torch_data
    hiddenimports += torch_hidden
except Exception as e:
    print(f"torch collect_all failed: {e}")

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
