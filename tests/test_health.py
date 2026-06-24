import os
import subprocess
import sys
import textwrap
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app


def test_health_returns_ok():
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_index_renders_when_imported_outside_project_root(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    script = textwrap.dedent(
        """
        from fastapi.testclient import TestClient

        from app.main import app

        response = TestClient(app).get("/")

        assert response.status_code == 200
        assert "Tax Filing Assistant" in response.text
        """
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root)

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
