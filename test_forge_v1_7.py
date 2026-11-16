"""
test_forge_v1_7.py — The Cockpit v1.7 (entity and subject drafts) test suite

Function:
    Executable expression of SPEC_V1_7.md. Written before
    forge_cli_v1_7.py and run red first.

Functions in this file (pytest-collected):
    1. test_drafts_validate_write_describe
    2. test_bad_drafts_refused
    3. test_claim_draft_unchanged
    4. test_commit_entity_subject_claim
    5. test_subject_needs_a_registered_entity
    6. test_inbox_lists_every_kind

Fixtures and helpers:
    7. workspace — FORGE_HOME with key.pem, getpass patched
    8. run       — call main, return (rc, out, err)
    9. _ledger   — ledger records

Tier:     Tier 1 — Consumer (The Cockpit)
Spec:     SPEC_V1_7.md 1.7.0
Licence:  MSL-1.0
Author:   James Gilbert (Giblets Forge)
"""

import json
import os
import sys
from unittest.mock import patch

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import forge_cli_v1_2 as v12  # noqa: E402
import forge_cli_v1_7 as cli  # noqa: E402

KEY = Ed25519PrivateKey.generate()


# 9. _ledger
def _ledger(home):
    path = home / "ledger.jsonl"
    return [json.loads(x)["record"] for x in path.read_bytes().splitlines()] if path.exists() else []


# 7. workspace
@pytest.fixture
def workspace(tmp_path, monkeypatch):
    home = tmp_path / "forge"
    home.mkdir()
    monkeypatch.setenv("FORGE_HOME", str(home))
    pem = KEY.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                            serialization.BestAvailableEncryption(b"test"))
    (home / "key.pem").write_bytes(pem)
    with patch("getpass.getpass", return_value="test"):
        yield home


# 8. run
@pytest.fixture
def run(capsys):
    def _run(*argv):
        rc = cli.main(list(argv))
        out = capsys.readouterr()
        return rc, out.out, out.err
    return _run


def _draft(home, draft_id):
    return json.loads((home / "inbox" / f"{draft_id}.json").read_text(encoding="utf-8"))


# 1. test_drafts_validate_write_describe
def test_drafts_validate_write_describe(workspace):
    e = cli.write_draft_any({"kind": "entity", "name": "James Gilbert"})
    s = cli.write_draft_any({"kind": "subject", "name": "Nova-bot", "entity": "James Gilbert"})
    c = cli.write_draft_any({"subject": "Nova-bot", "object": "sensor", "face": "FACT", "text": "HC-SR04."})
    assert cli.describe(_draft(workspace, e)) == {"kind": "entity", "name": "James Gilbert"}
    assert cli.describe(_draft(workspace, s)) == {"kind": "subject", "name": "Nova-bot", "entity": "James Gilbert"}
    assert cli.describe(_draft(workspace, c)) == {"kind": "claim", "subject": "Nova-bot", "object": "sensor",
                                                  "face": "FACT", "text": "HC-SR04."}
    for d in (e, s, c):
        cli.validate_any(_draft(workspace, d))


# 2. test_bad_drafts_refused
@pytest.mark.parametrize("fields", [
    {"kind": "entity"},
    {"kind": "entity", "name": "  "},
    {"kind": "entity", "name": "x" * 201},
    {"kind": "entity", "name": "James", "entity": "extra"},
    {"kind": "subject", "name": "Nova-bot"},
    {"kind": "subject", "name": "Nova-bot", "entity": ""},
    {"kind": "place", "name": "home"},
    {"kind": "claim", "subject": "a", "object": "b", "face": "FACT", "text": "c"},
    {"subject": "a", "object": "b", "face": "NOPE", "text": "c"},
])
def test_bad_drafts_refused(workspace, fields):
    with pytest.raises(ValueError):
        cli.write_draft_any(fields)
    assert not (workspace / "inbox").exists() or not list((workspace / "inbox").glob("*.json"))


# 3. test_claim_draft_unchanged
def test_claim_draft_unchanged(workspace):
    c = cli.write_draft_any({"subject": "sky", "object": "colour", "face": "FACT", "text": "Blue."})
    d = _draft(workspace, c)
    v12.validate_draft(d)  # an older Cockpit reads it as before
    assert set(d) == {"draft", "subject", "object", "text", "face", "created_at"}


# 4. test_commit_entity_subject_claim
def test_commit_entity_subject_claim(workspace, run):
    # drafted in reverse order: the commit still makes them in the right order
    cli.write_draft_any({"subject": "Nova-bot", "object": "sensor", "face": "FACT", "text": "HC-SR04 on the front."})
    cli.write_draft_any({"kind": "subject", "name": "Nova-bot", "entity": "James Gilbert"})
    cli.write_draft_any({"kind": "entity", "name": "James Gilbert"})
    rc, out, err = run("inbox", "commit")
    assert rc == 0, err
    assert "committed 3, refused 0" in out
    p9, db = cli._substrate_v4(), str(workspace / "forge.db")
    ent = p9.find(db, "James Gilbert")
    sub = p9.find(db, "Nova-bot")
    assert ent["type"] == "entity" and sub["type"] == "subject"
    assert [m["id"] for m in p9.members(db, sub["id"])] == [ent["id"]]
    types = [r.get("type") for r in _ledger(workspace)]
    assert "entity" in types and "subject" in types and "membership" in types
    assert any(r.get("subject") == "Nova-bot" and r.get("object") == "sensor" for r in _ledger(workspace))
    assert len(list((workspace / "inbox" / "done").glob("*.json"))) == 3
    assert not list((workspace / "inbox").glob("*.json"))


# 5. test_subject_needs_a_registered_entity
def test_subject_needs_a_registered_entity(workspace, run):
    cli.write_draft_any({"kind": "subject", "name": "Orphan", "entity": "Nobody"})
    rc, out, _ = run("inbox", "commit")
    assert rc == 0 and "committed 0, refused 1" in out
    refused = [json.loads(p.read_text(encoding="utf-8")) for p in (workspace / "inbox" / "refused").glob("*.json")]
    assert len(refused) == 1 and "Nobody" in refused[0]["reason"]
    cli.write_draft_any({"kind": "entity", "name": "James Gilbert"})
    assert "committed 1" in run("inbox", "commit")[1]
    cli.write_draft_any({"kind": "entity", "name": "James Gilbert"})
    rc, out, _ = run("inbox", "commit")
    assert rc == 0 and "committed 1, refused 0" in out
    done = [json.loads(p.read_text(encoding="utf-8")) for p in (workspace / "inbox" / "done").glob("*.json")]
    assert any(d.get("note") == "already registered" for d in done)


# 6. test_inbox_lists_every_kind
def test_inbox_lists_every_kind(workspace, run):
    cli.write_draft_any({"kind": "entity", "name": "James Gilbert"})
    cli.write_draft_any({"kind": "subject", "name": "Nova-bot", "entity": "James Gilbert"})
    cli.write_draft_any({"subject": "sky", "object": "colour", "face": "FACT", "text": "Blue."})
    rc, out, _ = run("inbox")
    assert rc == 0
    assert "entity James Gilbert" in out
    assert "subject Nova-bot -> James Gilbert" in out
    assert "sky" in out and "colour" in out
