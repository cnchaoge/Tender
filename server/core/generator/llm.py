"""
ClawOS X - LLM 生成器
支持 DeepSeek / 通义 / OpenAI
"""
from typing import Optional
from server.config import get_settings

settings = get_settings()


def get_generator():
    """根据配置返回 LLM 实例"""
    provider = settings.LLM_PROVIDER

    if provider == "deepseek":
        return DeepSeekGenerator()
    elif provider == "dashscope":
        return DashScopeGenerator()
    elif provider == "openai":
        return OpenAIGenerator()
    elif provider == "minimax":
        return MiniMaxGenerator()
    else:
        raise ValueError(f"未知的 LLM provider: {provider}")


class BaseGenerator:
    def __init__(self, model: str):
        self.model = model

    def generate(self, prompt: str, system: str = "", **kwargs) -> str:
        raise NotImplementedError


class DeepSeekGenerator(BaseGenerator):
    """DeepSeek API（OpenAI 兼容格式）"""
    def __init__(self):
        super().__init__(settings.DEEPSEEK_MODEL)
        from openai import OpenAI
        self.client = OpenAI(
            api_key=settings.DEEPSEEK_API_KEY,
            base_url="https://api.deepseek.com",
        )

    def generate(self, prompt: str, system: str = "", **kwargs) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            **kwargs
        )
        return resp["choices"][0]["message"]["content"]


class DashScopeGenerator(BaseGenerator):
    def __init__(self):
        super().__init__(settings.DASHSCOPE_MODEL)
        import dashscope
        dashscope.api_key = settings.DASHSCOPE_API_KEY

    def generate(self, prompt: str, system: str = "", **kwargs) -> str:
        from dashscope import Generation
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        resp = Generation.call(
            model=self.model,
            messages=messages,
            **kwargs
        )
        if resp["status_code"] != 200:
            raise Exception(f"DashScope generate failed: {resp}")
        return resp["output"]["choices"][0]["message"]["content"]


class OpenAIGenerator(BaseGenerator):
    def __init__(self):
        super().__init__(settings.OPENAI_MODEL)
        from openai import OpenAI
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)

    def generate(self, prompt: str, system: str = "", **kwargs) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            **kwargs
        )
        return resp["choices"][0]["message"]["content"]


class MiniMaxGenerator(BaseGenerator):
    """MiniMax API（OpenAI 兼容格式）"""
    def __init__(self):
        super().__init__(settings.MINIMAX_MODEL)
        from openai import OpenAI
        self.client = OpenAI(
            api_key=settings.MINIMAX_API_KEY,
            base_url="https://api.minimax.chat/v1",
        )

    def generate(self, prompt: str, system: str = "", **kwargs) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            **kwargs
        )
        return resp["choices"][0]["message"]["content"]
