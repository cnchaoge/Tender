"""
Tender - LLM 生成器
支持 DeepSeek / 通义 / OpenAI / Mock
"""
from typing import Optional
from server.config import get_settings

settings = get_settings()


class BaseGenerator:
    def __init__(self, model: str):
        self.model = model

    def generate(self, prompt: str, system: str = "", **kwargs) -> str:
        raise NotImplementedError

    def generate_stream(self, prompt: str, system: str = "", **kwargs):
        """流式生成YEild str片段。默认不支持，子类覆盖。"""
        raise NotImplementedError


class MockGenerator(BaseGenerator):
    """Mock LLM，用于本地无 API Key 时测试流程"""

    def __init__(self):
        super().__init__("mock")

    def generate(self, prompt: str, system: str = "", **kwargs) -> str:
        if "审核" in prompt:
            # 质检 prompt 返回通过
            return '{"passed": true, "score": 85, "issues": [], "suggestions": [], "coverage_check": {"requirements_covered": ["视频监控系统", "门禁系统"], "requirements_missing": []}}'
        # 生成 prompt 返回 mock 标书
        return """# 投标函

感谢贵方提供本次投标机会，我方愿以人民币50万元整的价格承接本项目。

## 一、项目概况

本项目为某工厂智能化改造项目，主要内容包括视频监控系统、门禁系统、网络改造等。

## 二、技术方案

### 2.1 视频监控系统
采用高清网络摄像机，支持夜视、移动侦测、云存储。

### 2.2 门禁系统
采用人脸识别+刷卡双因子认证，支持远程开门。

### 2.3 网络改造
升级千兆核心交换机，实现全厂网络覆盖。

## 三、资格说明

我方具备相关资质证书，技术团队有5年以上实施经验。

## 四、商务报价

| 项目 | 金额 |
|------|------|
| 设备费 | 30万元 |
| 施工费 | 15万元 |
| 税费 | 5万元 |
| **合计** | **50万元** |"""


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
            stream=False,
            **kwargs
        )
        return resp.choices[0].message.content

    def generate_stream(self, prompt: str, system: str = "", **kwargs):
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        stream = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            stream=True,
            **kwargs
        )
        for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta


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
        return resp.choices[0].message.content


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
        return resp.choices[0].message.content


class OllamaGenerator(BaseGenerator):
    """Ollama 本地 LLM（OpenAI 兼容 API，无需 API Key）"""
    def __init__(self):
        super().__init__(settings.OLLAMA_MODEL)
        from openai import OpenAI
        self.client = OpenAI(
            api_key="ollama",  # Ollama 不校验 API Key，但 OpenAI SDK 要求非空
            base_url=f"{settings.OLLAMA_BASE_URL}/v1",
        )

    def generate(self, prompt: str, system: str = "", **kwargs) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            stream=False,
            **kwargs
        )
        return resp.choices[0].message.content

    def generate_stream(self, prompt: str, system: str = "", **kwargs):
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        stream = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            stream=True,
            **kwargs
        )
        for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta


def get_generator():
    """根据配置返回 LLM 实例"""
    provider = settings.LLM_PROVIDER

    if provider == "mock":
        return MockGenerator()
    elif provider == "deepseek":
        return DeepSeekGenerator()
    elif provider == "dashscope":
        return DashScopeGenerator()
    elif provider == "openai":
        return OpenAIGenerator()
    elif provider == "minimax":
        return MiniMaxGenerator()
    elif provider == "ollama":
        return OllamaGenerator()
    raise ValueError(f"未知的 LLM provider: {provider}")
