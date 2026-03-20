from __future__ import annotations
import hashlib
import yaml
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Blueprint:
    name: str = "claw-python"
    version: str = "0.4.0"
    sha256: str = ""
    sandbox_memory_mb: int = 400
    sandbox_tmp_mb: int = 128
    sandbox_cpus: float = 1.5
    egress_policy_path: str = "config/egress_policy.yaml"

    @classmethod
    def resolve(cls, path: Path = Path("config/blueprint.yaml")) -> "Blueprint":
        raw = yaml.safe_load(path.read_text())
        valid = {k: v for k, v in raw.items() if k in cls.__dataclass_fields__}
        return cls(**valid)

    def verify(self, path: Path = Path("config/blueprint.yaml")) -> None:
        if not self.sha256:
            return
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != self.sha256:
            raise ValueError(
                f"Blueprint digest mismatch — file may be tampered. "
                f"Expected {self.sha256[:12]}... got {actual[:12]}..."
            )

    def preflight(self) -> dict:
        available_mb = _read_memavailable_mb()
        required_mb = self.sandbox_memory_mb + 200
        if available_mb < required_mb:
            raise RuntimeError(
                f"Insufficient memory: {available_mb}MB available, "
                f"{required_mb}MB required. "
                "Try: sudo systemctl stop nvargus-daemon"
            )
        return {"available_mb": available_mb, "required_mb": required_mb, "ok": True}


def _read_memavailable_mb() -> int:
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) // 1024
    except FileNotFoundError:
        pass
    return 9999


def bootstrap(path: Path = Path("config/blueprint.yaml")) -> Blueprint:
    if not path.exists():
        return Blueprint()
    bp = Blueprint.resolve(path)
    bp.verify(path)
    bp.preflight()
    return bp
