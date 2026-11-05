import importlib
import math

from server.core.embedder import embedder as embedder_mod


def test_get_embedder_mock():
    # ensure provider is mock for test isolation
    embedder_mod.settings.EMBED_PROVIDER = 'mock'
    inst = embedder_mod.get_embedder()
    assert inst.__class__.__name__ == 'MockEmbedder'

    vec = inst.embed_one('hello')
    assert isinstance(vec, list)
    assert len(vec) == inst.dim
    norm = math.sqrt(sum(x * x for x in vec))
    assert abs(norm - 1) < 1e-6


def test_mock_embedder_batch():
    me = embedder_mod.MockEmbedder(dim=16)
    vecs = me.embed(['a', 'b', 'c'])
    assert len(vecs) == 3
    for v in vecs:
        assert len(v) == 16
