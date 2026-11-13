"""
test_forge_v1_1.py — The Cockpit v1.1 (current-layer wiring) test suite

Function:
    Executable expression of SPEC_V1_1.md. Written before
    forge_cli_v1_1.py and run red first. Every test runs in an
    isolated FORGE_HOME with a passphrase-protected PEM key.

Functions in this file (pytest-collected):
    1.  test_layer_map
    2.  test_remember_writes_p9_p4_p8
    3.  test_remember_repeat_is_idempotent
    4.  test_remember_refuses_unsplittable_text
    5.  test_gate_uses_real_faces
    6.  test_cubes_filter_and_verify
    7.  test_trust_is_not_always_one
    8.  test_verify_ledger_cases
    9.  test_propose_pending_approve
    10. test_quarantine_writes_nothing
    11. test_refuse_recorded_as_refusal
    12. test_health_all_pass
    13. test_dream
    14. test_web
    15. test_crlf_ledger_refused
    16. test_v1_untouched

Fixtures and helpers:
    17. workspace — FORGE_HOME with key.pem (passphrase "test")
    18. run       — call main and return (rc, out, err)
    19. _lines    — ledger lines as parsed dicts
    20. _pub      — the operator public key

Tier:     Tier 1 — Consumer (The Cockpit)
Spec:     SPEC_V1_1.md 1.1.0
Licence:  MSL-1.0
Author:   James Gilbert (Giblets Forge)
"""

import json
import os
import sqlite3
import sys
from unittest.mock import patch

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import forge_cli  # noqa: E402
import forge_cli_v1_1 as cli  # noqa: E402

KEY = Ed25519PrivateKey.generate()


# 17. workspace
@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("FORGE_HOME", str(tmp_path))
    pem = KEY.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                            serialization.BestAvailableEncryption(b"test"))
    (tmp_path / "key.pem").write_bytes(pem)
    with patch("getpass.getpass", return_value="test"):
        yield tmp_path


# 18. run
@pytest.fixture
def run(capsys):
    def _run(*argv):
        rc = cli.main(list(argv))
        out = capsys.readouterr()
        return rc, out.out, out.err
    return _run


# 19. _lines
def _lines(ws):
    data = (ws / "ledger.jsonl").read_bytes()
    assert b"\r" not in data
    return [json.loads(x) for x in data.splitlines()]


# 20. _pub
def _pub():
    return KEY.public_key()


# 1. test_layer_map
def test_layer_map():
    expected = {
        "envelope": "envelope_v2", "sign": "sign_v2", "freeze": "freeze_v2",
        "ledger": "ledger_v2", "genesis": "genesis_v3", "canon-verify": "canon_verify_v2",
        "record": "record_v2", "store": "store_v2_1", "substrate": "substrate_v3",
        "weight": "weight_v2", "trust": "trust_v2", "leighton-engine": "leighton_engine_v3",
        "rules": "rules_v3", "datacube": "datacube_v2", "hal": "hal_v2",
    }
    for name, mod in expected.items():
        assert cli._layer(name).__name__ == mod


# 2. test_remember_writes_p9_p4_p8
def test_remember_writes_p9_p4_p8(workspace, run):
    rc, out, _ = run("remember", "The sky is blue", "--face", "FACT")
    assert rc == 0
    claim_id = out.strip()
    row = cli._layer("substrate").read_claim(str(workspace / "forge.db"), claim_id, verify=True)
    assert row["verified"] and row["capsule"]["face"] == "FACT"
    assert row["capsule"]["subject"] == "sky" and row["capsule"]["FACT"] == "The sky is blue"
    lines = _lines(workspace)
    assert len(lines) == 1 and lines[0]["seq"] == 0 and lines[0]["prev"] == "0" * 64
    assert cli._layer("genesis").verify_genesis(str(workspace / "ledger.jsonl"), _pub())
    store = cli._layer("store")
    assert store.export_jsonl(str(workspace / "store.db")) == (workspace / "ledger.jsonl").read_bytes()
    run("remember", "The sea is deep", "--face", "CONTEXT")
    assert store.export_jsonl(str(workspace / "store.db")) == (workspace / "ledger.jsonl").read_bytes()
    assert store.verify_store(str(workspace / "store.db"), _pub())


# 3. test_remember_repeat_is_idempotent
def test_remember_repeat_is_idempotent(workspace, run):
    rc1, out1, _ = run("remember", "The sky is blue", "--face", "FACT")
    rc2, out2, err2 = run("remember", "The sky is blue", "--face", "FACT")
    assert rc1 == rc2 == 0 and out1 == out2
    assert "already remembered" in err2
    assert len(_lines(workspace)) == 1


# 4. test_remember_refuses_unsplittable_text
def test_remember_refuses_unsplittable_text(workspace, run):
    rc, _, err = run("remember", "Sky", "--face", "FACT")
    assert rc == 2 and "subject" in err
    assert not (workspace / "ledger.jsonl").exists()
    assert run("remember", "x", "--face", "NOPE")[0] == 2


# 5. test_gate_uses_real_faces
def test_gate_uses_real_faces(workspace, run):
    run("remember", "The sky is blue", "--face", "FACT")
    run("remember", "The moon is cheese", "--face", "FICTION")
    before = (workspace / "ledger.jsonl").read_bytes()
    rc, _, err = run("remember", "The sky is green", "--face", "UNKNOWN")
    assert rc == 1 and "keystone gate" in err
    assert (workspace / "ledger.jsonl").read_bytes() == before
    # FICTION does not block: an UNKNOWN about the moon is allowed (v1 gated it as FACT)
    assert run("remember", "The moon is rock", "--face", "UNKNOWN")[0] == 0
    assert run("remember", "The sky is blue", "--face", "UNKNOWN")[0] == 0  # same object: no contradiction


# 6. test_cubes_filter_and_verify
def test_cubes_filter_and_verify(workspace, run):
    run("remember", "The sky is blue", "--face", "FACT")
    run("remember", "The sea is deep", "--face", "OPINION")
    rc, out, _ = run("cubes", "--face", "FACT")
    rows = json.loads(out)
    assert rc == 0 and [r["face"] for r in rows] == ["FACT"]
    assert rows[0]["verified"] is True and rows[0]["subject"] == "sky"
    rc, out, _ = run("cube", rows[0]["claim_id"])
    shown = json.loads(out)
    assert rc == 0 and shown["verified"] is True and shown["attestation"] is None


# 7. test_trust_is_not_always_one
def test_trust_is_not_always_one(workspace, run):
    _, out, _ = run("remember", "The sky is blue", "--face", "FACT")
    rc, out, _ = run("trust", out.strip())
    result = json.loads(out)
    assert rc == 0
    assert result["lambda"] == pytest.approx(1.5, abs=1e-3)
    assert result["time_unit"] == "days" and result["parameters"]["k"] == 0.1
    assert run("trust", "0" * 64)[0] == 1


# 8. test_verify_ledger_cases
def test_verify_ledger_cases(workspace, run):
    assert run("verify-ledger")[0] == 2
    (workspace / "ledger.jsonl").write_bytes(b"")
    assert run("verify-ledger")[0] == 2
    (workspace / "ledger.jsonl").unlink()
    run("remember", "The sky is blue", "--face", "FACT")
    rc, out, _ = run("verify-ledger")
    assert rc == 0 and "P8" in out
    good = (workspace / "ledger.jsonl").read_bytes()
    (workspace / "ledger.jsonl").write_bytes(good.replace(b"blue", b"bleu"))
    assert run("verify-ledger")[0] == 1
    (workspace / "ledger.jsonl").write_bytes(good)
    conn = sqlite3.connect(str(workspace / "store.db"))
    with conn:
        conn.execute("UPDATE ledger SET signer='x'")
    conn.close()
    assert run("verify-ledger")[0] == 1


# 9. test_propose_pending_approve
def test_propose_pending_approve(workspace, run):
    _, out, _ = run("remember", "The sky is blue", "--face", "FACT")
    claim_id = out.strip()
    assert run("propose", "0" * 64, "--action", "publish")[0] == 1
    rc, out, _ = run("propose", claim_id, "--action", "publish", "--note", "share it")
    assert rc == 0
    pending = json.loads(run("pending")[1])
    assert len(pending) == 1 and pending[0]["subject_id"] == claim_id
    rc, out, _ = run("approve", str(pending[0]["seq"]), "--key", str(workspace / "key.pem"),
                     "--lambda", "1.8", "--reason", "checked")
    assert rc == 0 and len(out.strip()) == 64
    assert json.loads(run("pending")[1]) == []
    att = cli._layer("substrate").latest_attestation(str(workspace / "forge.db"), claim_id)
    assert att["kind"] == "attestation" and att["seal"]["separation"] == "none"
    assert run("verify-ledger")[0] == 0
    assert run("approve", str(pending[0]["seq"]), "--key", str(workspace / "key.pem"),
               "--lambda", "1.8")[0] == 1  # no longer pending


# 10. test_quarantine_writes_nothing
def test_quarantine_writes_nothing(workspace, run):
    _, out, _ = run("remember", "The sky is blue", "--face", "FACT")
    run("propose", out.strip(), "--action", "publish")
    before = (workspace / "ledger.jsonl").read_bytes()
    rc, _, err = run("approve", "1", "--key", str(workspace / "key.pem"), "--lambda", "0.5")
    assert rc == 2 and "quarantine" in err
    assert (workspace / "ledger.jsonl").read_bytes() == before


# 11. test_refuse_recorded_as_refusal
def test_refuse_recorded_as_refusal(workspace, run):
    _, out, _ = run("remember", "The sky is blue", "--face", "FACT")
    claim_id = out.strip()
    run("propose", claim_id, "--action", "publish")
    h = json.loads(run("pending")[1])[0]["hash"]
    assert run("refuse", h, "--key", str(workspace / "key.pem"), "--lambda", "1.2")[0] == 2
    rc, _, _ = run("refuse", h, "--key", str(workspace / "key.pem"), "--lambda", "1.2",
                   "--reason", "not ready")
    assert rc == 0
    att = cli._layer("substrate").latest_attestation(str(workspace / "forge.db"), claim_id)
    assert att["kind"] == "refusal" and att["note"] == "not ready"


# 12. test_health_all_pass
def test_health_all_pass(workspace, run):
    rows = cli.probe_layers()
    assert len(rows) == 15
    assert all(r["status"] == "PASS" for r in rows), [r for r in rows if r["status"] != "PASS"]
    assert run("health")[0] == 0
    assert not (workspace / "ledger.jsonl").exists()


# 13. test_dream
def test_dream(workspace, run):
    run("remember", "The sky is blue", "--face", "FACT")
    with patch.object(cli, "_lllm_call", return_value=("Dreams", "b1")):
        rc, _, err = run("dream")
    assert rc == 1 and "dream parse failed" in err
    with patch.object(cli, "_lllm_call", return_value=("The sky is green\nmore", "b2")):
        assert run("dream")[0] == 1  # contradicts the FACT
    with patch.object(cli, "_lllm_call", return_value=("The tide is late\nmore", "b3")):
        rc, out, _ = run("dream")
    assert rc == 0 and "build_id=b3" in out
    claim_id = out.split("claim_id=")[1].split()[0]
    cap = cli._layer("substrate").read_claim(str(workspace / "forge.db"), claim_id)["capsule"]
    assert cap["face"] == "UNKNOWN" and cap["build_id"] == "b3" and len(cap["lllm_output_sha256"]) == 64


# 14. test_web
def test_web(workspace, run):
    rc, out, _ = run("web")
    assert rc == 0 and "8085" in out and "8080" in out


# 15. test_crlf_ledger_refused
def test_crlf_ledger_refused(workspace, run):
    run("remember", "The sky is blue", "--face", "FACT")
    good = (workspace / "ledger.jsonl").read_bytes()
    (workspace / "ledger.jsonl").write_bytes(good.replace(b"\n", b"\r\n"))
    db_before = (workspace / "forge.db").read_bytes()
    rc, _, err = run("remember", "The sea is deep", "--face", "FACT")
    assert rc == 1 and "CRLF" in err
    assert (workspace / "forge.db").read_bytes() == db_before


# 16. test_v1_untouched
def test_v1_untouched(workspace, run):
    run("remember", "The sky is blue", "--face", "FACT")
    target = workspace / "artefact.txt"
    target.write_text("hello\n")
    assert run("sign", str(target))[0] == 0  # v1 handler, run with current layers
    assert forge_cli._layer is not cli._layer
    assert forge_cli._layer("sign").__name__ == "sign"
    assert forge_cli._layer("ledger").__name__ == "ledger"
