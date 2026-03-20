import pytest
from claw.tools.policy import EgressPolicy, EgressVerdict, EgressRule


def _make_policy(default="deny") -> EgressPolicy:
    rules = [
        EgressRule(dest="api.example.com", methods=["POST"], verdict=EgressVerdict.ALLOW),
        EgressRule(dest="blocked.com", methods=["GET", "POST"], verdict=EgressVerdict.DENY),
    ]
    return EgressPolicy(rules=rules, default=EgressVerdict(default))


def test_egress_allow():
    p = _make_policy()
    assert p.check("api.example.com", "POST") == EgressVerdict.ALLOW


def test_egress_deny_explicit():
    p = _make_policy()
    assert p.check("blocked.com", "POST") == EgressVerdict.DENY


def test_egress_deny_default():
    p = _make_policy(default="deny")
    assert p.check("unknown.com", "POST") == EgressVerdict.DENY


def test_egress_add_rule_dynamic():
    p = _make_policy()
    p.add_rule("newsite.com", "GET")
    assert p.check("newsite.com", "GET") == EgressVerdict.ALLOW


def test_egress_add_rule_no_duplicate():
    p = _make_policy()
    p.add_rule("api.example.com", "POST")
    count = sum(1 for r in p.rules if r.dest == "api.example.com")
    assert count == 1


@pytest.mark.asyncio
async def test_egress_audit_writes_to_db(tmp_path):
    import aiosqlite
    db_path = str(tmp_path / "claw.db")
    async with aiosqlite.connect(db_path) as db:
        await db.execute("""
            CREATE TABLE egress_audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts INTEGER NOT NULL, dest TEXT NOT NULL,
                verdict TEXT NOT NULL, tool TEXT NOT NULL
            )
        """)
        await db.commit()

    p = EgressPolicy(db_path=db_path)
    await p.audit("example.com", EgressVerdict.ALLOW, "search")

    async with aiosqlite.connect(db_path) as db:
        async with db.execute("SELECT dest, verdict, tool FROM egress_audit_log") as cur:
            rows = await cur.fetchall()

    assert len(rows) == 1
    assert rows[0][0] == "example.com"
    assert rows[0][1] == "allow"


def test_egress_from_yaml(tmp_path):
    from pathlib import Path
    policy_file = tmp_path / "egress.yaml"
    policy_file.write_text(
        "default: deny\negress_rules:\n  - dest: 'llm-router.local'\n    methods: [POST]\n    verdict: allow\n"
    )
    p = EgressPolicy.from_yaml(policy_file)
    assert p.default == EgressVerdict.DENY
    assert p.check("llm-router.local", "POST") == EgressVerdict.ALLOW
