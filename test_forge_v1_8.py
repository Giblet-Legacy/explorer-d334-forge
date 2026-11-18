"""
test_forge_v1_8.py — The Cockpit v1.8 (drafts in the order written) test suite

Function:
    Executable expression of SPEC_V1_8.md. Written before
    forge_cli_v1_8.py and run red first.

Functions in this file (pytest-collected):
    1. test_frozen_clock_keeps_write_order
    2. test_same_millisecond_old_drafts_by_created_at
    3. test_unreadable_draft_listed_and_refused
    4. test_claim_draft_keys_and_delegation

Fixtures and helpers:
    5. workspace — FORGE_HOME with key.pem, getpass patched
    6. run       — call main, return (rc, out, err)
    7. _ledger   — ledger records

Tier:     Tier 1 — Consumer (The Cockpit)
Spec:     SPEC_V1_8.md 1.8.0
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

import forge_cli_v1_2 as v12  # noqa: E402
import forge_cli_v1_7 as v17  # noqa: E402
import forge_cli_v1_8 as cli  # noqa: E402

KEY = Ed25519PrivateKey.generate()
NOW = 1795036260.646


# 7. _ledger
def _ledger(home):
    path = home / "ledger.jsonl"
    return [json.loads(x)["record"] for x in path.read_bytes().splitlines()] if path.exists() else []


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


def _created(home, draft_id):
    return json.loads((home / "inbox" / f"{draft_id}.json").read_text(encoding="utf-8"))["created_at"]


# 1. test_frozen_clock_keeps_write_order
def test_frozen_clock_keeps_write_order(workspace, run):
    texts = [f"Claim number {i}." for i in range(8)]
    with patch("time.time", return_value=NOW):
        ids = [cli.write_draft_any({"subject": "order", "object": f"o{i}", "face": "FACT", "text": t})
               for i, t in enumerate(texts)]
    assert [i for i, _ in cli.pending_drafts()] == ids
    stamps = [_created(workspace, i) for i in ids]
    assert all(a < b for a, b in zip(stamps, stamps[1:]))
    rc, out, _ = run("inbox")
    assert rc == 0 and [line.split()[0] for line in out.splitlines()] == ids
    rc, out, err = run("inbox", "commit")
    assert rc == 0 and "committed 8, refused 0" in out, err
    claims = [r for r in _ledger(workspace) if r.get("subject") == "order"]
    assert [r["object"] for r in claims] == [f"o{i}" for i in range(8)]


# 2. test_same_millisecond_old_drafts_by_created_at
def test_same_millisecond_old_drafts_by_created_at(workspace):
    inbox = workspace / "inbox"
    inbox.mkdir()
    written = []
    for n, t in enumerate((NOW + 0.0001, NOW + 0.0002, NOW + 0.0003)):
        d = {"draft": v12.DRAFT_VERSION, "created_at": t, "subject": "s", "object": f"o{n}",
             "face": "FACT", "text": f"Text {n}."}
        data = json.dumps(d, sort_keys=True, ensure_ascii=False).encode("utf-8")
        draft_id = f"{int(t * 1000)}-{hashlib.sha256(data).hexdigest()[:8]}"
        (inbox / f"{draft_id}.json").write_bytes(data)
        written.append(draft_id)
    assert len({i.split("-")[0] for i in written}) == 1  # one millisecond
    assert written != sorted(written)  # the hashes sort the other way, so this test can fail
    assert [i for i, _ in cli.pending_drafts()] == written
    assert [i for i, _ in v12._pending_drafts()] == sorted(written)  # v1.2: by hash, the bug


# 3. test_unreadable_draft_listed_and_refused
def test_unreadable_draft_listed_and_refused(workspace, run):
    good = cli.write_draft_any({"kind": "entity", "name": "James Gilbert"})
    (workspace / "inbox" / "1-deadbeef.json").write_text("{ broken", encoding="utf-8")
    assert [i for i, _ in cli.pending_drafts()] == ["1-deadbeef", good]
    rc, out, _ = run("inbox")
    assert rc == 0 and "1-deadbeef  invalid" in out
    rc, out, err = run("inbox", "commit")
    assert rc == 0 and "committed 1, refused 1" in out, err
    assert (workspace / "inbox" / "refused" / "1-deadbeef.json").exists()


# 4. test_claim_draft_keys_and_delegation
def test_claim_draft_keys_and_delegation(workspace, run):
    c = cli.write_draft_any({"subject": "sky", "object": "colour", "face": "FACT", "text": "Blue."})
    v = v12.write_draft({"subject": "sea", "object": "depth", "face": "FACT", "text": "Deep."})
    keys = lambda i: set(json.loads((workspace / "inbox" / f"{i}.json").read_text(encoding="utf-8")))  # noqa
    assert keys(c) == keys(v)
    assert cli.write_draft is not v12.write_draft and cli.validate_any is v17.validate_any
    rc, _, _ = run("inbox", "drop", c)
    assert rc == 0 and [i for i, _ in cli.pending_drafts()] == [v]
    rc, out, _ = run("status")
    assert rc == v17.main(["status"])
