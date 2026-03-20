import pytest
import hashlib
from pathlib import Path
from config.blueprint import Blueprint, _read_memavailable_mb, bootstrap


def test_blueprint_load_defaults():
    bp = bootstrap(path=Path("/nonexistent/blueprint.yaml"))
    assert bp.name == "claw-python"
    assert bp.sandbox_memory_mb == 400


def test_blueprint_sha256_mismatch(tmp_path):
    bp_file = tmp_path / "blueprint.yaml"
    bp_file.write_text("name: claw-python\nversion: '0.4.0'\nsha256: 'abc123'\n")
    bp = Blueprint(name="claw-python", version="0.4.0", sha256="abc123wronghash")
    with pytest.raises(ValueError, match="digest mismatch"):
        bp.verify(bp_file)


def test_blueprint_sha256_skip_when_empty(tmp_path):
    bp_file = tmp_path / "blueprint.yaml"
    bp_file.write_text("name: claw-python\nversion: '0.4.0'\nsha256: ''\n")
    bp = Blueprint(name="claw-python", version="0.4.0", sha256="")
    bp.verify(bp_file)  # should not raise


def test_blueprint_preflight_ok(monkeypatch):
    monkeypatch.setattr("config.blueprint._read_memavailable_mb", lambda: 9999)
    bp = Blueprint(sandbox_memory_mb=400)
    result = bp.preflight()
    assert result["ok"] is True


def test_blueprint_preflight_oom(monkeypatch):
    monkeypatch.setattr("config.blueprint._read_memavailable_mb", lambda: 100)
    bp = Blueprint(sandbox_memory_mb=400)
    with pytest.raises(RuntimeError, match="memory"):
        bp.preflight()
