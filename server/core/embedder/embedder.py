"""
ClawOS X - Embedding 模型
支持 DeepSeek / 通义 / BGE
"""
from server.config import get_settings

settings = get_settings()


def get_embedder():
    """根据配置返回 Embedding 实例"""
    provider = settings.EMBED_PROVIDER

    if provider == "deepseek":
        return DeepSeekEmbedder()
    elif provider == "dashscope":
        return DashScopeEmbedder()
    elif provider == "bge":
        return BGEEmbedder()
    else:
        raise ValueError(f"未知的 Embedding provider: {provider}")


class DeepSeekEmbedder:
    """DeepSeek Embedding"""

    def __init__(self):
        from deepseek import DeepSeek
        self.client = DeepSeek(api_key=settings.DEEPSEEK_API_KEY)
        self.model = settings.DEEPSEEK_EMBED_MODEL

    def embed(self, texts: list[str]) -> list[list[float]]:
        from deepseek import DeepSeek
        resp = self.client.embeddings(
            model=self.model,
            input=texts
        )
        return [item["embedding"] for item in resp["data"]]

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text])[0]


class DashScopeEmbedder:
    """通义 Embedding"""

    def __init__(self):
        import dashscope
        dashscope.api_key = settings.DASHSCOPE_API_KEY
        self.model = settings.DASHSCOPE_EMBED_MODEL

    def embed(self, texts: list[str]) -> list[list[float]]:
        import dashscope
        from dashscope import TextEmbedding
        embeddings = []
        for text in texts:
            resp = TextEmbedding.call(
                model=self.model,
                input=text
            )
            if resp["status_code"] != 200:
                raise Exception(f"DashScope embed failed: {resp}")
            embeddings.append(resp["output"]["embeddings"][0]["embedding"])
        return embeddings

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
