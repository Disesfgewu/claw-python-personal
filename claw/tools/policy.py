from __future__ import annotations


def is_main_session(session_id: str) -> bool:
    return session_id == "agent:main" or session_id.endswith(":main")

# ── NemoClaw-inspired Egress Policy ───────────────────────────────────────────
from enum import Enum
from dataclasses import dataclass, field
import time
import uuid
import yaml
import aiosqlite
from pathlib import Path


class EgressVerdict(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    PENDING = "pending"


@dataclass
class EgressRule:
    dest: str
    methods: list[str] = field(default_factory=lambda: ["GET", "POST"])
    verdict: EgressVerdict = EgressVerdict.ALLOW


@dataclass
class EgressPolicy:
    rules: list[EgressRule] = field(default_factory=list)
    default: EgressVerdict = EgressVerdict.DENY
    db_path: str = "~/.claw/claw.db"

    def check(self, dest: str, method: str = "POST") -> EgressVerdict:
        for rule in self.rules:
            if dest.endswith(rule.dest) and method in rule.methods:
                return rule.verdict
        return self.default

    async def request_approval(self, dest: str, method: str) -> str:
        req_id = str(uuid.uuid4())[:8]
        async with aiosqlite.connect(Path(self.db_path).expanduser()) as db:
            await db.execute(
                "INSERT INTO egress_pending(id,dest,method,requested_at) VALUES(?,?,?,?)",
                (req_id, dest, method, int(time.time())),
            )
            await db.commit()
        return req_id

    async def audit(self, dest: str, verdict: EgressVerdict, tool: str) -> None:
        async with aiosqlite.connect(Path(self.db_path).expanduser()) as db:
            await db.execute(
                "INSERT INTO egress_audit_log(ts,dest,verdict,tool) VALUES(?,?,?,?)",
                (int(time.time()), dest, verdict.value, tool),
            )
            await db.commit()

    def add_rule(self, dest: str, method: str = "POST") -> None:
        """Dynamically add whitelist rule at runtime (no restart needed)."""
        for rule in self.rules:
            if rule.dest == dest and method in rule.methods:
                return
        self.rules.append(EgressRule(dest=dest, methods=[method]))

    @classmethod
    def from_yaml(cls, path: Path, db_path: str = "~/.claw/claw.db") -> "EgressPolicy":
        if not path.exists():
            return cls(db_path=db_path)
        raw = yaml.safe_load(path.read_text())
        rules = [
            EgressRule(
                dest=r["dest"],
                methods=r.get("methods", ["GET", "POST"]),
                verdict=EgressVerdict(r.get("verdict", "allow")),
            )
            for r in raw.get("egress_rules", [])
        ]
        default = EgressVerdict(raw.get("default", "deny"))
        return cls(rules=rules, default=default, db_path=db_path)


# Module-level singleton (set by main.py)
_egress_policy: "EgressPolicy | None" = None


def get_egress_policy() -> "EgressPolicy":
    global _egress_policy
    if _egress_policy is None:
        _egress_policy = EgressPolicy()
    return _egress_policy


def set_egress_policy(policy: "EgressPolicy") -> None:
    global _egress_policy
    _egress_policy = policy
