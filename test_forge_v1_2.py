"""
test_forge_v1_2.py — The Cockpit v1.2 (LLLM provenance, inbox, status) test suite

Function:
    Executable expression of SPEC_V1_2.md. Written before
    forge_cli_v1_2.py and run red first. LLLM is replaced by a fake
    LLLM_HOME (a real build.json on disk) and patched subprocess calls.

Functions in this file (pytest-collected):
    1. test_provenance_reads_build
    2. test_provenance_refusals
    3. test_dream_anchors_build_once
    4. test_inbox_commit_and_refuse
    5. test_inbox_drop_and_invalid
    6. test_status
    11. test_remember_polarity
    12. test_inbox_polarity

Fixtures and helpers:
    7.  workspace — FORGE_HOME with key.pem, LLLM_HOME with one build
    8.  run       — call main, return (rc, out, err)
    9.  _info     — fake `lllm info` text
    10. _ledger   — ledger records

Tier:     Tier 1 — Consumer (The Cockpit)
Spec:     SPEC_V1_2.md 1.2.0
Licence:  MSL-1.0
Author:   James Gilbert (Giblets Forge)
"""

import hashlib
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

import forge_cli_v1_2 as cli  # noqa: E402

KEY = Ed25519PrivateKey.generate()
BID = "4817218b9f3a"
BUILD = {"build_id": BID, "identity": {"corpus_csv_sha256": "c" * 64, "trained_sha256": "t" * 64,
                                       "code": {"train.py": "a" * 64}, "capsule_id": "lllm@0.1.0"},
         "counts": {"docs": 634}}


# 9. _info
def _info(warnings=()):
    lines = [f"build:   {BID}", "model:   x", "docs:    634", "capsule: lllm@0.1.0"]
    return "\n".join(lines + [f"WARNING: {w}" for w in warnings]) + "\n"


# 10. _ledger
def _ledger(ws):
    path = ws / "ledger.jsonl"
    return [json.loads(x)["record"] for x in path.read_bytes().splitlines()] if path.exists() else []


# 7. workspace
@pytest.fixture
def workspace(tmp_path, monkeypatch):
    home, lllm_home = tmp_path / "forge", tmp_path / "lllm"
    home.mkdir()
    (lllm_home / "models" / BID).mkdir(parents=True)
    (lllm_home / "models" / BID / "build.json").write_text(json.dumps(BUILD, indent=1, sort_keys=True))
    monkeypatch.setenv("FORGE_HOME", str(home))
    monkeypatch.setenv("LLLM_HOME", str(lllm_home))
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


# 1. test_provenance_reads_build
def test_provenance_reads_build(workspace):
    with patch.object(cli, "_run_lllm", return_value=_info()):
        p = cli.lllm_provenance()
    raw = (workspace.parent / "lllm" / "models" / BID / "build.json").read_bytes()
    assert p["build_id"] == BID and p["warnings"] == []
    assert p["build_json_sha256"] == hashlib.sha256(raw).hexdigest()
    assert p["identity"] == BUILD["identity"]


# 2. test_provenance_refusals
def test_provenance_refusals(workspace, run):
    with patch.object(cli, "_run_lllm", return_value="no current build: lllm build, then lllm use <id>\n"):
        with pytest.raises(RuntimeError):
            cli.lllm_provenance()
    with patch.object(cli, "_run_lllm", return_value=_info().replace(BID, "ffffffffffff")):
        with pytest.raises(RuntimeError):
            cli.lllm_provenance()
    with patch.object(cli, "_run_lllm", return_value=_info(["train.py changed since this build; lllm build for a new id"])), \
         patch.object(cli, "_lllm_gen", return_value="The tide is late\n"):
        rc, _, err = run("dream")
    assert rc == 1 and "no longer matches" in err
    assert not (workspace / "ledger.jsonl").exists() and not (workspace / "forge.db").exists()


# 3. test_dream_anchors_build_once
def test_dream_anchors_build_once(workspace, run):
    with patch.object(cli, "_run_lllm", return_value=_info()), \
         patch.object(cli, "_lllm_gen", side_effect=["The tide is late\n", "The moon is restless\n"]):
        assert run("dream")[0] == 0
        rc, out, _ = run("dream")
    assert rc == 0
    recs = _ledger(workspace)
    assert [r.get("type") for r in recs] == ["lllm.build", None, None]
    anchor = recs[0]
    assert anchor["build_id"] == BID and anchor["identity"] == BUILD["identity"]
    claim = recs[2]
    assert claim["lllm"] == {"build_id": BID, "build_json_sha256": anchor["build_json_sha256"]}
    assert claim["face"] == "OPINION" and claim["build_id"] == BID and "polarity" not in claim
    assert claim["source"] == "lllm"
    assert not (workspace / "forge.db").exists()  # LLLM output never enters the truth store
    sub = cli._layer("substrate")
    rows = sub.list_claims(str(workspace / "lllm.db"), verify=True)
    assert [r["capsule"]["subject"] for r in rows] == ["tide", "moon"] and all(r["verified"] for r in rows)
    assert run("verify-ledger")[0] == 0


# 4. test_inbox_commit_and_refuse
def test_inbox_commit_and_refuse(workspace, run):
    assert run("remember", "The sky is blue", "--face", "FACT")[0] == 0
    good = cli.write_draft({"subject": "sea", "object": "deep", "text": "The sea is deep", "face": "CONTEXT"})
    bad = cli.write_draft({"subject": "sky", "object": "green", "text": "Is the sky green?", "face": "UNKNOWN"})
    rc, out, _ = run("inbox")
    listed = json.loads(out)
    assert rc == 0 and [d["id"] for d in listed] == [good, bad]
    rc, out, _ = run("inbox", "commit")
    assert rc == 0
    done = json.loads((workspace / "inbox" / "done" / f"{good}.json").read_text())
    refused = json.loads((workspace / "inbox" / "refused" / f"{bad}.json").read_text())
    assert len(done["claim_id"]) == 64 and "keystone" in refused["reason"]
    assert len(_ledger(workspace)) == 2
    assert json.loads(run("inbox")[1]) == []


# 5. test_inbox_drop_and_invalid
def test_inbox_drop_and_invalid(workspace, run):
    d = cli.write_draft({"subject": "a", "object": "b", "text": "a is b", "face": "FACT"})
    for bad in ({"subject": "", "object": "b", "text": "t", "face": "FACT"},
                {"subject": "a", "object": "b", "text": "t", "face": "MAYBE"},
                {"subject": "a", "object": "b", "text": "x" * 2001, "face": "FACT"},
                {"subject": "a", "object": "b", "text": "t", "face": "FACT", "extra": 1}):
        with pytest.raises(ValueError):
            cli.write_draft(bad)
    (workspace / "inbox" / "999-junk.json").write_text("{not json")
    assert run("inbox", "drop", d)[0] == 0
    assert json.loads((workspace / "inbox" / "refused" / f"{d}.json").read_text())["reason"] == "dropped by operator"
    assert run("inbox", "commit")[0] == 0
    assert "reason" in json.loads((workspace / "inbox" / "refused" / "999-junk.json").read_text())
    assert not (workspace / "ledger.jsonl").exists()


# 6. test_status
def test_status(workspace, run):
    s = cli.status()
    assert s["claims"]["total"] == 0 and s["ledger"]["entries"] == 0
    run("remember", "The sky is blue", "--face", "FACT")
    run("remember", "The tide is late", "--face", "UNKNOWN")
    cli.write_draft({"subject": "sea", "object": "deep", "text": "The sea is deep", "face": "FACT"})
    with patch("getpass.getpass", side_effect=AssertionError("status must not ask")):
        s = cli.status()
    assert s["claims"]["total"] == 2 and s["claims"]["by_face"]["UNKNOWN"] == 1
    assert s["ledger"]["entries"] == 2 and s["ledger"]["self_consistent"] is True
    assert s["ledger"]["p8_mirror"] is True and s["inbox"]["pending"] == 1
    assert s["lllm_opinions"] == 0
    lp = workspace / "ledger.jsonl"
    lp.write_bytes(lp.read_bytes().replace(b"blue", b"bleu"))
    assert cli.status()["ledger"]["self_consistent"] is False
    rc, out, _ = run("status")
    assert rc == 0 and json.loads(out)["claims"]["total"] == 2


# 11. test_remember_polarity
def test_remember_polarity(workspace, run):
    db = str(workspace / "forge.db")
    sub = cli._layer("substrate")

    def cap(text, *flags):
        rc, out, err = run("remember", text, *flags)
        assert rc == 0, err
        return sub.read_claim(db, out.strip())["capsule"]

    c = cap("The sky is blue", "--face", "FACT")
    assert (c["object"], c["polarity"]) == ("blue", "affirm")
    c = cap("The cat is not a dog", "--face", "FACT")
    assert (c["subject"], c["object"], c["polarity"]) == ("cat", "a dog", "negate")
    c = cap("The sea is deep", "--face", "CONTEXT", "--polarity", "negate")
    assert c["polarity"] == "negate"
    c = cap("The moon is cheese", "--face", "FICTION")
    assert "polarity" not in c
    c = cap("The tide is late", "--face", "UNKNOWN")
    assert "polarity" not in c
    assert run("remember", "The sun is hot", "--face", "OPINION", "--polarity", "affirm")[0] == 2
    assert run("remember", "The sun is hot", "--face", "FACT", "--polarity", "maybe")[0] == 2


# 12. test_inbox_polarity
def test_inbox_polarity(workspace, run):
    cli.write_draft({"subject": "fire", "object": "not cold", "text": "Fire is not cold", "face": "FACT"})
    cli.write_draft({"subject": "rain", "object": "wet", "text": "Rain is wet?", "face": "OPINION"})
    assert run("inbox", "commit")[0] == 0
    caps = [r["capsule"] for r in cli._layer("substrate").list_claims(str(workspace / "forge.db"))]
    assert {c["subject"]: (c["object"], c.get("polarity")) for c in caps} == {
        "fire": ("cold", "negate"), "rain": ("wet", None)}
