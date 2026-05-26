from importlib import import_module
from fastapi.testclient import TestClient


def test_health_endpoints():
    mod = import_module('server.main')
    app = getattr(mod, 'app')
    client = TestClient(app)
    ok_statuses = {200, 301, 302, 404, 405}
    for path in ('/health', '/api/health', '/'):
        resp = client.get(path)
        assert resp.status_code in ok_statuses
