from importlib import import_module

from server.core.generator import llm as llm_mod


def test_get_generator_mock():
    llm_mod.settings.LLM_PROVIDER = 'mock'
    g = llm_mod.get_generator()
    assert g.__class__.__name__ == 'MockGenerator'

    # audit prompt should return JSON-like passed result
    res = g.generate('请做一次审核')
    assert '"passed": true' in res or '通过' in res or res.strip().startswith('{')

    # non-audit prompt returns the mock tender string
    res2 = g.generate('生成投标文档')
    assert '# 投标函' in res2
