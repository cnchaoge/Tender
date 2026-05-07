"""
sitecustomize.py - PyInstaller frozen 环境下修复 chromadb 导入问题
在 site 模块加载时自动执行，早于所有其他模块导入
"""
import sys

# chromadb.api.types 导入 DefaultEmbeddingFunction 时会触发 sentence_transformers
# 在 frozen 环境下 sentence_transformers 的 transformers.utils.import_utils 会失败
# 解决方案：提前在 sys.modules 中注入一个假的 chromadb.api.types，
# 让真正的 types.py 导入时触发 AttributeError，被 except 捕获
# 然后提供一个不依赖 sentence_transformers 的最小 stub

_orig_chromadb_types = None


def _patch_chromadb_types():
    global _orig_chromadb_types
    try:
        import chromadb.api.types as types_module
        _orig_chromadb_types = types_module
    except Exception:
        return

    # 创建一个 stub，不继承任何实际的 embedding 实现
    class _FakeEmbeddingFunction:
        def __init__(self, *args, **kwargs):
            pass

        def __call__(self, *args, **kwargs):
            raise NotImplementedError("DefaultEmbeddingFunction stub in frozen env")

    # 把 stub 注入到模块属性
    types_module.DefaultEmbeddingFunction = _FakeEmbeddingFunction


# 在所有模块导入之前执行
_patch_chromadb_types()
