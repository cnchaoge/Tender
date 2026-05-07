"""
ClawOS X - Embedding 模型
支持 通义 / BGE
"""
from server.config import get_settings

settings = get_settings()


def get_embedder():
    """根据配置返回 Embedding 实例"""
    provider = settings.EMBED_PROVIDER

    if provider == "dashscope":
        return DashScopeEmbedder()
    elif provider == "bge":
        return BGEEmbedder()
    else:
        raise ValueError(f"未知的 Embedding provider: {provider}，支持 dashscope / bge")


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
    """本地 BGE Embedding"""

    def __init__(self):
        from sentence_transformers import SentenceTransformer
        self.model = SentenceTransformer(settings.BGE_MODEL_PATH or "BAAI/bge-large-zh-v1.5")

    def embed(self, texts: list[str]) -> list[list[float]]:
        return self.model.encode(texts, normalize_embeddings=True).tolist()

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text])[0]
