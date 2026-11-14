"""
test_forge_v1_4.py — The Cockpit v1.4 (entities, subjects, predicates) test suite

Function:
    Executable expression of SPEC_V1_4.md. Written before
    forge_cli_v1_4.py and run red first.

Functions in this file (pytest-collected):
    1. test_register
    2. test_commit_cube_predicate
    3. test_commands

Fixtures and helpers:
    4. workspace — FORGE_HOME with key.pem, getpass patched
    5. run       — call main, return (rc, out, err)
    6. _ledger   — ledger records

Tier:     Tier 1 — Consumer (The Cockpit)
Spec:     SPEC_V1_4.md 1.4.0
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

import forge_cli_v1_4 as cli  # noqa: E402

KEY = Ed25519PrivateKey.generate()


# 6. _ledger
def _ledger(home):
    path = home / "ledger.jsonl"
    return [json.loads(x)["record"] for x in path.read_bytes().splitlines()] if path.exists() else []


# 4. workspace
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


# 5. run
@pytest.fixture
def run(capsys):
    def _run(*argv):
        rc = cli.main(list(argv))
        out = capsys.readouterr()
        return rc, out.out, out.err
    return _run


# 1. test_register
def test_register(workspace, run):
    eid, new = cli.register("entity", "James Gilbert", KEY, kind="person")
    assert new
    sid, new = cli.register("subject", "hal-layer", KEY, kind="repo")
    assert new
    assert cli.register("subject", "HAL-layer ", KEY) == (sid, False)
    records = _ledger(workspace)
    assert [r["type"] for r in records] == ["entity", "subject"]
    assert records[0]["name"] == "James Gilbert" and records[0]["kind"] == "person"
    p9 = cli._substrate_v4()
    db = str(workspace / "forge.db")
    assert p9.find(db, "james gilbert")["id"] == eid and p9.find(db, "hal-layer")["id"] == sid
    with pytest.raises(ValueError):
        cli.register("entity", "hal-layer", KEY)
    with pytest.raises(ValueError):
        cli.register("thing", "x", KEY)
    assert len(_ledger(workspace)) == 2
    assert run("verify-ledger")[0] == 0


# 2. test_commit_cube_predicate
def test_commit_cube_predicate(workspace):
    cid, _ = cli.commit_cube("the-legacy", "explorer-d334-forge",
                             {"FACT": "The Legacy reads the Cockpit's status and drafts.", "CONTEXT": "legacy_v7 header"},
                             KEY, predicate="depends on")
    cap = cli._layer("substrate").read_claim(str(workspace / "forge.db"), cid)["capsule"]
    assert cap["predicate"] == "depends on" and cap["polarity"] == "affirm"
    plain, _ = cli.commit_cube("sky", "blue", {"FACT": "The sky is blue."}, KEY)
    assert "predicate" not in cli._layer("substrate").read_claim(str(workspace / "forge.db"), plain)["capsule"]
    for bad in ("", "  ", 3):
        with pytest.raises(ValueError):
            cli.commit_cube("a", "b", {"FACT": "x"}, KEY, predicate=bad)


# 3. test_commands
def test_commands(workspace, run):
    rc, out, _ = run("entity", "add", "James", "Gilbert", "--kind", "person")
    assert rc == 0 and "registered" in out and "already" not in out
    rc, out, _ = run("entity", "add", "James", "Gilbert")
    assert rc == 0 and "already registered" in out
    assert run("subject", "add", "hal-layer", "--kind", "repo")[0] == 0
    assert run("subject", "add", "James", "Gilbert")[0] == 2  # taken by an entity
    assert run("subject", "add", "x", "--kind", "k" * 61)[0] == 2
    assert run("remember", "ledger-layer is append-only", "--face", "FACT")[0] == 0
    rc, out, _ = run("subjects")
    d = json.loads(out)
    assert rc == 0 and [e["name"] for e in d["entities"]] == ["James Gilbert"]
    assert [s["name"] for s in d["subjects"]] == ["hal-layer"] and d["unregistered"] == ["ledger-layer"]
