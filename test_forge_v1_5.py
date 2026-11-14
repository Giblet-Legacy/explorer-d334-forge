"""
test_forge_v1_5.py — The Cockpit v1.5 (answering a question) test suite

Function:
    Executable expression of SPEC_V1_5.md. Written before
    forge_cli_v1_5.py and run red first.

Functions in this file (pytest-collected):
    1. test_find_claim
    2. test_answer
    3. test_answer_refusals
    4. test_command

Fixtures and helpers:
    5. workspace — FORGE_HOME with key.pem, getpass patched
    6. run       — call main, return (rc, out, err)
    7. _ledger   — ledger records
    8. _question — commit a six-face cube whose UNKNOWN is a question

Tier:     Tier 1 — Consumer (The Cockpit)
Spec:     SPEC_V1_5.md 1.5.0
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

import forge_cli_v1_5 as cli  # noqa: E402

KEY = Ed25519PrivateKey.generate()
QUESTION = "When, if ever, can a frozen v1 be retired from the import path entirely?"
FACES = {"FACT": "New code imports envelope_v2.",
         "COUNTER": "Two behaviours exist side by side.",
         "CONTEXT": "The Immutable Rule.",
         "OPINION": "Layering is worth it.",
         "FICTION": "In fifty years v1 still re-runs.",
         "UNKNOWN": QUESTION}


# 7. _ledger
def _ledger(home):
    path = home / "ledger.jsonl"
    return [json.loads(x)["record"] for x in path.read_bytes().splitlines()] if path.exists() else []


# 8. _question
def _question(subject="envelope-layer", obj="design", faces=FACES):
    claim_id, _ = cli.commit_cube(subject, obj, dict(faces), KEY, predicate="has")
    return claim_id


# 5. workspace
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


# 6. run
@pytest.fixture
def run(capsys):
    def _run(*argv):
        rc = cli.main(list(argv))
        out = capsys.readouterr()
        return rc, out.out, out.err
    return _run


# 1. test_find_claim
def test_find_claim(workspace):
    with pytest.raises(KeyError):
        cli.find_claim("0123456789ab")  # no forge.db yet
    a = _question()
    b = _question(obj="status")
    assert cli.find_claim(a) == a
    assert cli.find_claim(a[:12]) == a
    assert cli.find_claim(a[:8].upper()) == a
    assert cli.find_claim(b[:12]) == b
    with pytest.raises(ValueError):
        cli.find_claim(a[:7])
    with pytest.raises(ValueError):
        cli.find_claim("not-hex-at-all")
    with pytest.raises(KeyError):
        cli.find_claim("f" * 64 if not a.startswith("f") else "0" * 64)
    with patch.object(cli, "_all_claim_ids", return_value=["abcdef0011", "abcdef0022"]):
        with pytest.raises(ValueError):
            cli.find_claim("abcdef00")


# 2. test_answer
def test_answer(workspace, run):
    old_id = _question()
    p9, db = cli._layer("substrate"), str(workspace / "forge.db")
    old = p9.read_claim(db, old_id)["capsule"]
    before = len(_ledger(workspace))

    new_id, entry = cli.answer(old_id, "  Never: envelope_v2 is built on envelope.py.  ", KEY)

    new_row = p9.read_claim(db, new_id, verify=True)
    assert new_row["verified"] and new_row["is_active"]
    new = new_row["capsule"]
    assert new["UNKNOWN"] is None
    assert new["answers"] == {"claim_id": old_id, "question": QUESTION,
                              "answer": "Never: envelope_v2 is built on envelope.py."}
    for k in old:
        if k not in ("UNKNOWN", "signature"):
            assert new[k] == old[k], k
    old_row = p9.read_claim(db, old_id)
    assert not old_row["is_active"] and old_row["superseded_by"] == new_id
    asking = [r for r in p9.list_claims(db) if (r["capsule"] or {}).get("UNKNOWN") == QUESTION]
    assert asking == []
    records = _ledger(workspace)
    assert len(records) == before + 1
    assert records[-1] == p9.get_claim(db, new_id)
    assert entry is not None
    assert run("verify-ledger")[0] == 0


# 3. test_answer_refusals
def test_answer_refusals(workspace):
    old_id = _question()
    no_q = _question(obj="plain", faces={"FACT": "Nothing is asked here."})
    p9, db = cli._layer("substrate"), str(workspace / "forge.db")
    count = lambda: (len(p9.list_claims(db, active_only=False)), len(_ledger(workspace)))  # noqa: E731
    start = count()
    for bad in ("", "   ", None):
        with pytest.raises(ValueError):
            cli.answer(old_id, bad, KEY)
    with pytest.raises(KeyError):
        cli.answer("0" * 64, "an answer", KEY)
    with pytest.raises(ValueError):
        cli.answer(no_q, "an answer", KEY)
    assert count() == start
    cli.answer(old_id, "first answer", KEY)
    after = count()
    with pytest.raises(ValueError):
        cli.answer(old_id, "second answer", KEY)
    assert count() == after


# 4. test_command
def test_command(workspace, run):
    old_id = _question()
    rc, out, err = run("answer", old_id[:12], "Never:", "v2", "is", "built", "on", "v1.")
    assert rc == 0, err
    assert QUESTION in out and "Never: v2 is built on v1." in out
    assert f"answered {old_id[:12]} -> " in out
    assert run("answer", old_id[:12], "again")[0] == 2
    assert run("answer", "0" * 12, "who")[0] == 2
    assert run("answer", "abc", "short ref")[0] == 2
    assert run("answer", _question(obj="x")[:12])[0] == 2  # no answer text
    assert run("verify-ledger")[0] == 0
