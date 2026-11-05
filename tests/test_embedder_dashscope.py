import sys
from types import SimpleNamespace
import importlib

from server.core.embedder import embedder as embedder_mod


def test_dashscope_batch_and_api_key(monkeypatch):
    # Ensure settings
    embedder_mod.settings.DASHSCOPE_API_KEY = 'test-key'
    embedder_mod.settings.DASHSCOPE_EMBED_MODEL = 'm'

    call_count = {'n': 0}

    class Resp:
        def __init__(self, batch_len):
            self.status_code = 200
            self._batch_len = batch_len
        def json(self):
            return {"output": {"embeddings": [{"embedding": [0.1]*8} for _ in range(self._batch_len)]}}

    def fake_post(url, headers=None, json=None, timeout=None):
        call_count['n'] += 1
        batch = json['input']['texts'] if isinstance(json, dict) and 'input' in json else [json.get('input')] if isinstance(json, dict) else [json]
        return Resp(len(batch))

    fake_httpx = SimpleNamespace(post=fake_post)
    monkeypatch.setitem(sys.modules, 'httpx', fake_httpx)

    de = embedder_mod.DashScopeEmbedder()
    # 12 texts -> should split into 2 batches (10 + 2)
    texts = [f't{i}' for i in range(12)]
    vecs = de.embed(texts)
    assert len(vecs) == 12
    assert call_count['n'] == 2

    # Missing API key should raise
    embedder_mod.settings.DASHSCOPE_API_KEY = ''
    de2 = embedder_mod.DashScopeEmbedder()
    try:
        de2.embed(['x'])
        assert False, 'Expected ValueError when API key missing'
    except ValueError:
        pass
