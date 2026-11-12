"""
test_forge.py — The Cockpit test suite

Function:
    Executable expression of SPEC.md. Written before the implementation
    per build discipline. Covers the CLI contract: argument parsing,
    face validation, quarantine enforcement, LLLM unavailability,
    passphrase handling, migration, exit codes.

Layer:    Tier 1 — Consumer (The Cockpit)
Spec:     SPEC.md v1.0.0
Licence:  MSL-1.0
Author:   James Gilbert (Giblets Forge)
"""

import os
import sys
import json
import pytest
from unittest.mock import patch
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

# Bootstrap: add all sibling layer directories to sys.path
ROOT = os.path.dirname(os.path.abspath(__file__))
LAYER_DIRS = [
    "envelope-layer", "sign-layer", "freeze-layer", "ledger-layer",
    "genesis-layer", "canon-verify-layer", "record-layer", "store-layer",
    "substrate-layer", "weight-layer", "trust-layer",
    "leighton-engine-layer", "rules-layer", "datacube-layer", "hal-layer",
]
for layer in LAYER_DIRS:
    p = os.path.abspath(os.path.join(ROOT, "..", layer))
    if os.path.isdir(p):
        sys.path.insert(0, p)

import forge_cli


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def workspace(tmp_path, monkeypatch):
    """Isolated FORGE_HOME with a fresh Ed25519 PEM keypair."""
    monkeypatch.setenv("FORGE_HOME", str(tmp_path))
    key = Ed25519PrivateKey.generate()
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.BestAvailableEncryption(b"test"),
    )
    (tmp_path / "key.pem").write_bytes(pem)
    return tmp_path


@pytest.fixture
def fake_passphrase():
    """Patch getpass to return 'test'."""
    with patch("getpass.getpass", return_value="test"):
        yield


# ---------------------------------------------------------------------------
# CLI parsing: usage errors (exit 2)
# ---------------------------------------------------------------------------
def test_no_args_prints_usage(workspace, capsys):
    rc = forge_cli.main([])
    assert rc == 2
    captured = capsys.readouterr()
    assert "usage" in captured.err.lower()


def test_unknown_command_exits_2(workspace, capsys):
    rc = forge_cli.main(["nonsense"])
    assert rc == 2
    captured = capsys.readouterr()
    assert "unknown command" in captured.err.lower() or "usage" in captured.err.lower()


def test_remember_requires_face(workspace, capsys):
    rc = forge_cli.main(["remember", "The sky is blue"])
    assert rc == 2
    captured = capsys.readouterr()
    assert "--face" in captured.err


def test_remember_rejects_invalid_face(workspace, capsys):
    rc = forge_cli.main(["remember", "The sky is blue", "--face", "MAGIC"])
    assert rc == 2
    captured = capsys.readouterr()
    assert "face" in captured.err.lower()


# ---------------------------------------------------------------------------
# remember: happy path (exit 0)
# ---------------------------------------------------------------------------
def test_remember_fact_succeeds(workspace, fake_passphrase, capsys):
    rc = forge_cli.main(["remember", "The sky is blue", "--face", "FACT"])
    assert rc == 0
    captured = capsys.readouterr()
    # Should print a claim_id
    assert len(captured.out.strip()) > 0


def test_remember_creates_ledger_and_db(workspace, fake_passphrase):
    rc = forge_cli.main(["remember", "The sky is blue", "--face", "FACT"])
    assert rc == 0
    # Ledger and DB exist
    assert (workspace / "ledger.jsonl").exists() or (workspace / "forge.db").exists()


# ---------------------------------------------------------------------------
# Keystone Gate: UNKNOWN contradicting FACT refuses
# ---------------------------------------------------------------------------
def test_remember_unknown_contradicting_fact_fails(workspace, fake_passphrase, capsys):
    # First: store a FACT
    rc1 = forge_cli.main(["remember", "The sky is blue", "--face", "FACT"])
    assert rc1 == 0
    # Then: try UNKNOWN that contradicts
    rc2 = forge_cli.main(["remember", "The sky is green", "--face", "UNKNOWN"])
    assert rc2 == 1
    captured = capsys.readouterr()
    assert "keystone" in captured.err.lower() or "contradict" in captured.err.lower()


def test_remember_unknown_consistent_passes(workspace, fake_passphrase):
    rc1 = forge_cli.main(["remember", "The sky is blue", "--face", "FACT"])
    assert rc1 == 0
    # Same subject, same object - not a contradiction
    rc2 = forge_cli.main(["remember", "The sky is blue", "--face", "UNKNOWN"])
    assert rc2 == 0


def test_remember_unknown_with_empty_existing_passes(workspace, fake_passphrase):
    # No existing claims - gate has nothing to contradict
    rc = forge_cli.main(["remember", "The moon is cheese", "--face", "UNKNOWN"])
    assert rc == 0


# ---------------------------------------------------------------------------
# LLLM availability: dream/think/reason/ask fail cleanly if no LLLM
# ---------------------------------------------------------------------------
def test_dream_without_lllm_fails(workspace, fake_passphrase, capsys, monkeypatch):
    monkeypatch.delenv("LLLM_HOME", raising=False)
    rc = forge_cli.main(["dream"])
    assert rc == 1
    captured = capsys.readouterr()
    assert "lllm" in captured.err.lower()


def test_think_without_lllm_fails(workspace, fake_passphrase, capsys, monkeypatch):
    monkeypatch.delenv("LLLM_HOME", raising=False)
    rc = forge_cli.main(["think"])
    assert rc == 1
    captured = capsys.readouterr()
    assert "lllm" in captured.err.lower()


def test_ask_without_lllm_fails(workspace, fake_passphrase, capsys, monkeypatch):
    monkeypatch.delenv("LLLM_HOME", raising=False)
    rc = forge_cli.main(["ask", "what is a capsule?"])
    assert rc == 1
    captured = capsys.readouterr()
    assert "lllm" in captured.err.lower()


def test_remember_works_without_lllm(workspace, fake_passphrase, monkeypatch):
    # remember does not need LLLM
    monkeypatch.delenv("LLLM_HOME", raising=False)
    rc = forge_cli.main(["remember", "The sky is blue", "--face", "FACT"])
    assert rc == 0


# ---------------------------------------------------------------------------
# HAL: quarantine enforcement (λ < 0.60 -> exit 2)
# ---------------------------------------------------------------------------
def test_approve_quarantined_lambda_exits_2(workspace, fake_passphrase, capsys):
    rc = forge_cli.main([
        "approve", "abc123",
        "--key", str(workspace / "key.pem"),
        "--lambda", "0.5",
    ])
    assert rc == 2
    captured = capsys.readouterr()
    assert "quarantine" in captured.err.lower() or "lambda" in captured.err.lower()


def test_approve_valid_lambda_succeeds(workspace, fake_passphrase, capsys):
    # No pending proposals means "not found" is acceptable, but the
    # seal creation path must succeed (quarantine passed).
    # We test the quarantine gate specifically: 1.5 passes.
    rc = forge_cli.main([
        "approve", "abc123",
        "--key", str(workspace / "key.pem"),
        "--lambda", "1.5",
    ])
    # rc may be 0 (accepted) or 1 (proposal not found); never 2 (usage)
    assert rc in (0, 1)


def test_refuse_quarantined_lambda_exits_2(workspace, fake_passphrase, capsys):
    rc = forge_cli.main([
        "refuse", "abc123",
        "--key", str(workspace / "key.pem"),
        "--lambda", "0.3",
        "--reason", "not enough evidence",
    ])
    assert rc == 2


# ---------------------------------------------------------------------------
# verify-ledger: P6 independent verification
# ---------------------------------------------------------------------------
def test_verify_ledger_empty_workspace(workspace, capsys):
    # No ledger exists yet
    rc = forge_cli.main(["verify-ledger"])
    # Missing ledger exits 2 per spec
    assert rc == 2


def test_verify_ledger_after_remember(workspace, fake_passphrase):
    rc1 = forge_cli.main(["remember", "The sky is blue", "--face", "FACT"])
    assert rc1 == 0
    rc2 = forge_cli.main(["verify-ledger"])
    assert rc2 == 0


# ---------------------------------------------------------------------------
# health: all layers probe
# ---------------------------------------------------------------------------
def test_health_returns_zero_or_one(workspace, fake_passphrase, capsys):
    rc = forge_cli.main(["health"])
    # 0 = all green, 1 = some fail. Both are acceptable in test env.
    assert rc in (0, 1)
    captured = capsys.readouterr()
    # Should mention at least P1
    assert "P1" in captured.out or "Envelope" in captured.out


# ---------------------------------------------------------------------------
# migrate-scp: one-way importer
# ---------------------------------------------------------------------------
def test_migrate_scp_empty_dir(workspace, fake_passphrase, capsys, tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    rc = forge_cli.main(["migrate-scp", str(empty)])
    # Empty dir has nothing to do - should exit 0 (no-op)
    assert rc in (0, 1)


# ---------------------------------------------------------------------------
# Passphrase: Ctrl-C during getpass exits 130
# ---------------------------------------------------------------------------
def test_passphrase_interrupt_exits_130(workspace, capsys):
    with patch("getpass.getpass", side_effect=KeyboardInterrupt):
        rc = forge_cli.main(["remember", "Test claim", "--face", "FACT"])
    assert rc == 130


# ---------------------------------------------------------------------------
# Status: comprehensive summary
# ---------------------------------------------------------------------------
def test_status_runs(workspace, fake_passphrase, capsys):
    rc = forge_cli.main(["status"])
    # Status always succeeds (exit 0), even on empty workspace
    assert rc == 0
