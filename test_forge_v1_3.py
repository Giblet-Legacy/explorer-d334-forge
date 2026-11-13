"""
test_forge_v1_3.py — The Cockpit v1.3 (P13 v3 gate, cubes, attestation) test suite

Function:
    Executable expression of SPEC_V1_3.md. Written before
    forge_cli_v1_3.py and run red first.

Functions in this file (pytest-collected):
    1. test_remember_gates_with_v3
    2. test_inbox_gates_with_v3
    3. test_commit_cube
    4. test_attest
    5. test_v1_2_commands_still_work
    12. test_engine_command
    13. test_engine_end_to_end

Fixtures and helpers:
    6. workspace — FORGE_HOME with key.pem, getpass patched
    7. run       — call main, return (rc, out, err)
    8. _ledger   — ledger records
    9. FACES6    — one text per face
    10. engine   — LLLM_HOME with one build, LLLM_CLI pointing at ENGINE
    11. ENGINE   — a stand-in engine cli.py

Tier:     Tier 1 — Consumer (The Cockpit)
Spec:     SPEC_V1_3.md 1.3.0
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

import forge_cli_v1_3 as cli  # noqa: E402

KEY = Ed25519PrivateKey.generate()

# 9. FACES6
FACES6 = {"FACT": "A fact", "COUNTER": "A counter", "OPINION": "An opinion", "FICTION": "A fiction",
          "CONTEXT": "A context", "UNKNOWN": "An open question?"}


# 8. _ledger
def _ledger(home):
    path = home / "ledger.jsonl"
    return [json.loads(x)["record"] for x in path.read_bytes().splitlines()] if path.exists() else []


# 6. workspace
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


# 7. run
@pytest.fixture
def run(capsys):
    def _run(*argv):
        rc = cli.main(list(argv))
        out = capsys.readouterr()
        return rc, out.out, out.err
    return _run


# 1. test_remember_gates_with_v3
def test_remember_gates_with_v3(workspace, run):
    assert run("remember", "ledger is append-only", "--face", "FACT")[0] == 0
    rc, _, err = run("remember", "ledger is sharded", "--face", "UNKNOWN")
    assert rc == 0, err  # a different object: a different claim (v2 refused this)
    rc, _, err = run("remember", "ledger is not append-only", "--face", "UNKNOWN")
    assert rc == 1 and "keystone gate" in err
    assert len(_ledger(workspace)) == 2


# 2. test_inbox_gates_with_v3
def test_inbox_gates_with_v3(workspace, run):
    assert run("remember", "sky is blue", "--face", "FACT")[0] == 0
    cli._v12.write_draft({"subject": "sky", "object": "grey", "text": "sky is grey", "face": "UNKNOWN"})
    cli._v12.write_draft({"subject": "sky", "object": "not blue", "text": "sky is not blue", "face": "UNKNOWN"})
    rc, out, _ = run("inbox", "commit")
    assert rc == 0 and "committed 1, refused 1" in out
    refused = os.listdir(workspace / "inbox" / "refused")
    note = json.load(open(workspace / "inbox" / "refused" / [f for f in refused if f.endswith(".json")][0]))
    assert "keystone gate" in json.dumps(note).lower()


# 3. test_commit_cube
def test_commit_cube(workspace):
    key = KEY
    cid, entry = cli.commit_cube("envelope-layer", "status", FACES6, key)
    assert entry is not None
    cap = cli._layer("substrate").read_claim(str(workspace / "forge.db"), cid)["capsule"]
    assert all(cap[f] == t for f, t in FACES6.items())
    assert cap["face"] == "FACT" and cap["polarity"] == "affirm" and cap["object"] == "status"
    cid2, _ = cli.commit_cube("envelope-layer", "design", FACES6, key)  # same subject, new object
    assert cid2 != cid
    assert cli.commit_cube("envelope-layer", "status", FACES6, key) == (cid, None)
    n = len(_ledger(workspace))
    with pytest.raises(ValueError, match="Keystone Gate"):
        cli.commit_cube("envelope-layer", "not status", {"UNKNOWN": "is it?"}, key)
    for bad in ({}, {"SEVENTH": "x"}, {"FACT": "  "}, {"FACT": 3}):
        with pytest.raises(ValueError):
            cli.commit_cube("x", "y", bad, key)
    assert len(_ledger(workspace)) == n
    cid3, _ = cli.commit_cube("sea", "not deep", {"OPINION": "o", "CONTEXT": "c"}, key)
    cap3 = cli._layer("substrate").read_claim(str(workspace / "forge.db"), cid3)["capsule"]
    assert cap3["face"] == "CONTEXT" and cap3["polarity"] == "negate" and cap3["object"] == "deep"
    cid4, _ = cli.commit_cube("sea", "salty", {"OPINION": "o"}, key)
    cap4 = cli._layer("substrate").read_claim(str(workspace / "forge.db"), cid4)["capsule"]
    assert cap4["face"] == "OPINION" and "polarity" not in cap4


# 4. test_attest
def test_attest(workspace, run):
    cid, _ = cli.commit_cube("hal-layer", "P15 HAL", FACES6, KEY)
    seal_hash = cli.attest(cid, KEY, 1.0, "read and approved")
    records = _ledger(workspace)
    assert records[-2]["pending_hal"] is True and records[-2]["subject_id"] == cid
    assert records[-1]["decision"] == "approve" and records[-1]["subject_id"] == cid
    assert len(seal_hash) == 64
    att = cli._layer("substrate").latest_attestation(str(workspace / "forge.db"), cid)
    assert att["kind"] == "attestation" and att["note"] == "read and approved"
    assert run("verify-ledger")[0] == 0
    with pytest.raises(ValueError):
        cli.attest(cid, KEY, 0.5)
    with pytest.raises(KeyError):
        cli.attest("0" * 64, KEY, 1.0)


# 5. test_v1_2_commands_still_work
def test_v1_2_commands_still_work(workspace, run):
    assert run("remember", "sky is blue", "--face", "FACT", "--polarity", "negate")[0] == 0
    rc, out, _ = run("status")
    assert rc == 0 and json.loads(out)["claims"]["total"] == 1


# 11. ENGINE — a stand-in for the engine's lllm/cli.py (gen and info)
ENGINE = '''import json, os, sys
home = os.environ["LLLM_HOME"]
if sys.argv[1] == "info":
    print("build:   abc123def456")
    print("model:   x")
elif sys.argv[1] == "gen":
    if sys.argv[2] == "refuse":
        print("(nothing: the model refused to continue this seed)")
    else:
        print("The tide is late")
'''


# 10. engine
@pytest.fixture
def engine(workspace, tmp_path, monkeypatch):
    lllm_home = tmp_path / "lllm"
    (lllm_home / "models" / "abc123def456").mkdir(parents=True)
    (lllm_home / "models" / "abc123def456" / "build.json").write_text(
        json.dumps({"identity": {"code": {}}, "counts": {"docs": 1}}))
    cli_py = tmp_path / "cli.py"
    cli_py.write_text(ENGINE)
    monkeypatch.setenv("LLLM_HOME", str(lllm_home))
    monkeypatch.setenv("LLLM_CLI", str(cli_py))
    return cli_py


# 12. test_engine_command
def test_engine_command(workspace, tmp_path, monkeypatch):
    cli_py = tmp_path / "cli.py"
    cli_py.write_text("")
    monkeypatch.setenv("LLLM_CLI", str(cli_py))
    assert cli.engine_command() == [sys.executable, str(cli_py)]
    monkeypatch.setenv("LLLM_CLI", str(tmp_path / "missing.py"))
    with pytest.raises(RuntimeError, match="LLLM_CLI"):
        cli.engine_command()
    monkeypatch.delenv("LLLM_CLI")
    with patch("shutil.which", return_value=None):
        with pytest.raises(RuntimeError, match="LLLM unavailable"):
            cli.engine_command()
    with patch("shutil.which", return_value="/usr/bin/lllm"):
        assert cli.engine_command() == ["/usr/bin/lllm"]


# 13. test_engine_end_to_end
def test_engine_end_to_end(engine, workspace, run):
    prov = cli.lllm_provenance()
    assert prov["build_id"] == "abc123def456" and prov["warnings"] == []
    rc, out, err = run("dream")
    assert rc == 0, err
    assert "build_id=abc123def456" in out
    rows = cli._layer("substrate").list_claims(str(workspace / "lllm.db"))
    assert [r["capsule"]["subject"] for r in rows] == ["tide"] and rows[0]["capsule"]["face"] == "OPINION"
    with pytest.raises(RuntimeError, match="refused"):
        cli.lllm_gen("refuse")
    rc, _, err = run("reason", "refuse")
    assert rc == 1 and "refused" in err
    assert len(cli._layer("substrate").list_claims(str(workspace / "lllm.db"))) == 1
