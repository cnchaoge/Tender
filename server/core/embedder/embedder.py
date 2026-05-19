"""
Tender - Embedding 模型
支持 通义 / BGE
"""
from server.config import get_settings, BASE_DIR

settings = get_settings()


def get_embedder():
    """根据配置返回 Embedding 实例"""
    provider = settings.EMBED_PROVIDER
    try:
        with open(BASE_DIR / "embedder_debug.txt", "a", encoding="utf-8") as f:
            f.write(f"EMBED_PROVIDER={provider!r}, BASE_DIR={BASE_DIR!r}\n")
    except Exception:
        pass

    if provider == "dashscope":
        return DashScopeEmbedder()
    elif provider == "bge":
        return BGEEmbedder()
    elif provider == "m3e":
        return M3EEmbedder()
    elif provider == "mock":
        return MockEmbedder()
    else:
        raise ValueError(f"未知的 Embedding provider: {provider}，支持 dashscope / bge / m3e / mock")


class DashScopeEmbedder:
    """通义 Embedding"""

    def __init__(self):
        import httpx
        self.model = settings.DASHSCOPE_EMBED_MODEL
        self.api_key = settings.DASHSCOPE_API_KEY
        self.url = "https://dashscope.aliyuncs.com/api/v1/services/embeddings/text-embedding/text-embedding"

    def embed(self, texts: list[str]) -> list[list[float]]:
        import httpx
        if not self.api_key:
            raise ValueError("DashScope API KEY 未配置，请在设置中配置 DASHSCOPE_API_KEY")
        results = []
        # DashScope 每批最多 10 条
        for i in range(0, len(texts), 10):
            batch = texts[i:i+10]
            resp = httpx.post(
                self.url,
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json={"model": self.model, "input": {"texts": batch}},
                timeout=30
            )
            data = resp.json()
            if resp.status_code != 200:
                raise ValueError(f"DashScope embed failed: {data}")
            results.extend([item["embedding"] for item in data["output"]["embeddings"]])
        return results

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text])[0]


class BGEEmbedder:
    """本地 BGE Embedding（不依赖 sentence_transformers）"""

    def __init__(self):
        from server.core.embedder.bge_embedder import encode_texts as _encode_bge
        self._encode = _encode_bge

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [emb.tolist() if hasattr(emb, 'tolist') else emb for emb in self._encode(texts)]

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text])[0]


class M3EEmbedder:
    """本地 M3E Embedding（不依赖 sentence_transformers）"""

    def __init__(self):
        from server.core.embedder.m3e_embedder import encode_texts as _encode_m3e
        self._encode = _encode_m3e

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [emb.tolist() if hasattr(emb, 'tolist') else emb for emb in self._encode(texts)]

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text])[0]


class MockEmbedder:
    """Mock Embedder（Mac 开发用，不调真实 API）"""

    def __init__(self, dim: int = 768):
        import numpy as np
        self.dim = dim
        self._np = np

    def embed(self, texts: list[str]) -> list[list[float]]:
        vecs = []
        for _ in texts:
            v = self._np.random.randn(self.dim)
            v = v / (self._np.linalg.norm(v) + 1e-9)
            vecs.append(v.tolist())
        return vecs

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text])[0]
