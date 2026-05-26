from importlib import import_module


def test_app_importable():
    mod = import_module('server.main')
    assert hasattr(mod, 'app')


def test_app_has_routes():
    mod = import_module('server.main')
    app = getattr(mod, 'app')
    assert hasattr(app, 'routes')
