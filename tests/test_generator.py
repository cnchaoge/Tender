from types import SimpleNamespace

from server.core.generator import llm as llm_mod


def test_get_generator_mock(monkeypatch):
    monkeypatch.setattr(llm_mod, "get_settings", lambda: SimpleNamespace(LLM_PROVIDER="mock"))
    g = llm_mod.get_generator()
    assert g.__class__.__name__ == 'MockGenerator'

    # audit prompt should return JSON-like passed result
    res = g.generate('请做一次审核')
    assert '"passed": true' in res or '通过' in res or res.strip().startswith('{')

    # non-audit prompt returns the mock tender string
    res2 = g.generate('生成投标文档')
    assert '# 投标函' in res2
    assert ''.join(g.generate_stream('生成投标文档')) == res2
    assert ''.join(g.generate_stream('请做一次审核')) == res
