"""Guards for the P0 start path, relative /api, and the CI workflow."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _uvicorn_lines(text: str) -> list[str]:
    return [line for line in text.splitlines() if "uvicorn" in line and "echo" not in line.lower()]


def test_official_start_is_single_process_loopback():
    for relative in ("start.sh", "run.bat"):
        text = (ROOT / relative).read_text(encoding="utf-8")
        commands = _uvicorn_lines(text)
        assert commands, relative
        for line in commands:
            assert "--reload" not in line
            assert "--workers" not in line
        assert "127.0.0.1" in text


def test_browser_api_calls_are_same_origin():
    for relative in (
        "web/src/api/index.js",
        "web/src/features/jobs/client.js",
        "web/src/pages/RAGChat.vue",
    ):
        text = (ROOT / relative).read_text(encoding="utf-8")
        assert "localhost:8000" not in text
        assert "VITE_API_URL" not in text
    api = (ROOT / "web/src/api/index.js").read_text(encoding="utf-8")
    assert "export function apiBase()" in api
    assert 'return ""' in api
    vite = (ROOT / "web/vite.config.js").read_text(encoding="utf-8")
    assert "VITE_API_URL" not in vite
    assert "localhost:8000" in vite  # dev-server proxy target, not the browser base


def test_ci_workflow_parses_and_runs_pytest():
    text = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    import_lines = [
        line for line in text.splitlines() if "import xml.etree.ElementTree" in line
    ]
    assert import_lines
    assert import_lines[0].startswith(" ")
    assert "continue-on-error: true" in text
    assert "npm run build" in text
    assert "pytest -q --cov=server --cov-report=xml" in text
    # The pytest step must fail the job. It is not marked continue-on-error.
    lines = text.splitlines()
    pytest_indexes = [
        index for index, line in enumerate(lines) if "pytest -q --cov=server --cov-report=xml" in line
    ]
    assert pytest_indexes
    step = "\n".join(lines[pytest_indexes[0] - 2 : pytest_indexes[0] + 1])
    assert "continue-on-error" not in step
