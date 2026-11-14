"""
test_forge_v1_6.py — The Cockpit v1.6 (imagining) test suite

Function:
    Executable expression of SPEC_V1_6.md. Written before
    forge_cli_v1_6.py and run red first. The Ollama call is replaced;
    nothing reaches a network.

Functions in this file (pytest-collected):
    1. test_pick_seeds
    2. test_imagine
    3. test_imagine_refusals
    4. test_loopback_only
    5. test_commands

Fixtures and helpers:
    6. workspace — FORGE_HOME with key.pem, getpass patched, fake Ollama
    7. run       — call main, return (rc, out, err)
    8. _ledger   — ledger records
    9. _seed     — commit a claim

Tier:     Tier 1 — Consumer (The Cockpit)
Spec:     SPEC_V1_6.md 1.6.0
Licence:  MSL-1.0
Author:   James Gilbert (Giblets Forge)
"""

import json
import os
import sys
from unittest.mock import patch
from urllib.parse import urlparse

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import forge_cli_v1_6 as cli  # noqa: E402

KEY = Ed25519PrivateKey.generate()
DREAM = "I dreamt the ultrasonic eye and the six servos learnt to walk around the chair leg."
PROMPTS = []


# 8. _ledger
def _ledger(home):
    path = home / "ledger.jsonl"
    return [json.loads(x)["record"] for x in path.read_bytes().splitlines()] if path.exists() else []


# 9. _seed
def _seed(subject, obj, faces):
    return cli.commit_cube(subject, obj, faces, KEY)[0]


def _fake_ollama(prompt):
    PROMPTS.append(prompt)
    return DREAM, "sha256:abc"


# 6. workspace
@pytest.fixture
def workspace(tmp_path, monkeypatch):
    home = tmp_path / "forge"
    home.mkdir()
    monkeypatch.setenv("FORGE_HOME", str(home))
    monkeypatch.delenv("FORGE_DREAM_MODEL", raising=False)
    pem = KEY.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                            serialization.BestAvailableEncryption(b"test"))
    (home / "key.pem").write_bytes(pem)
    PROMPTS.clear()
    with patch("getpass.getpass", return_value="test"), patch.object(cli, "_ollama", _fake_ollama):
        yield home


# 7. run
@pytest.fixture
def run(capsys):
    def _run(*argv):
        rc = cli.main(list(argv))
        out = capsys.readouterr()
        return rc, out.out, out.err
    return _run


# 1. test_pick_seeds
def test_pick_seeds(workspace):
    assert cli.pick_seeds() == []
    a = _seed("robot", "sensor", {"FACT": "The HC-SR04 echo pin outputs 5 V."})
    b = _seed("Robot", "power", {"CONTEXT": "Six SG90 servos share one 5 V supply."})
    _seed("robot", "mood", {"OPINION": "Robots are fun."})              # not asserted
    _seed("robot", "gap", {"UNKNOWN": "Which servo library?"})          # not asserted
    c = _seed("esp32", "logic", {"FACT": "ESP32 GPIO is 3.3 V only."})
    assert {r["claim_id"] for r in cli.pick_seeds(n=10)} == {a, b, c}
    assert {r["claim_id"] for r in cli.pick_seeds(" ROBOT ", n=10)} == {a, b}
    assert len(cli.pick_seeds(n=2)) == 2
    assert cli.pick_seeds("nothing here") == []


# 2. test_imagine
def test_imagine(workspace, run):
    a = _seed("robot", "sensor", {"FACT": "The HC-SR04 echo pin outputs 5 V."})
    b = _seed("robot", "power", {"FACT": "Six SG90 servos share one 5 V supply."})
    before = len(_ledger(workspace))
    claim_id, text, seeds = cli.imagine(KEY, "robot")
    assert text == DREAM and {s["claim_id"] for s in seeds} == {a, b}
    assert "HC-SR04" in PROMPTS[-1] and "SG90" in PROMPTS[-1]
    p9, db = cli._layer("substrate"), str(workspace / "forge.db")
    row = p9.read_claim(db, claim_id, verify=True)
    cap = row["capsule"]
    assert row["verified"] and row["is_active"]
    assert cap["UNKNOWN"] == DREAM and cap["face"] == "UNKNOWN"
    assert cap["subject"] == "robot" and cap["object"] == "dream"
    assert cap["source"] == "ollama" and cap["model"] == "gemma2:2b" and cap["model_digest"] == "sha256:abc"
    assert sorted(cap["seeds"]) == sorted([a, b]) and len(cap["dream_sha256"]) == 64
    for face in ("FACT", "COUNTER", "CONTEXT", "OPINION", "FICTION"):
        assert cap[face] is None
    assert len(_ledger(workspace)) == before + 1
    assert run("verify-ledger")[0] == 0
    with patch.dict(os.environ, {"FORGE_DREAM_MODEL": "llama3.2:3b"}):
        with patch.object(cli, "_ollama", lambda p: ("A second, different dream.", None)):
            cid2, _, _ = cli.imagine(KEY)
    assert p9.read_claim(db, cid2)["capsule"]["model"] == "llama3.2:3b"


# 3. test_imagine_refusals
def test_imagine_refusals(workspace):
    with pytest.raises(ValueError):
        cli.imagine(KEY)  # nothing to dream from
    _seed("robot", "sensor", {"FACT": "The HC-SR04 echo pin outputs 5 V."})
    p9, db = cli._layer("substrate"), str(workspace / "forge.db")
    count = lambda: (len(p9.list_claims(db, active_only=False)), len(_ledger(workspace)))  # noqa: E731
    start = count()
    with patch.object(cli, "gate", side_effect=ValueError("contradicts claim 1234")):
        with pytest.raises(ValueError):
            cli.imagine(KEY)
    with patch.object(cli, "_ollama", lambda p: ("   ", None)):
        with pytest.raises(RuntimeError):
            cli.imagine(KEY)
    assert count() == start


# 4. test_loopback_only
def test_loopback_only():
    assert urlparse(cli.OLLAMA_URL).hostname == "127.0.0.1"
    assert cli.DEFAULT_MODEL == "gemma2:2b"


# 5. test_commands
def test_commands(workspace, run):
    assert run("imagine")[0] == 2
    a = _seed("robot", "sensor", {"FACT": "The HC-SR04 echo pin outputs 5 V."})
    rc, out, err = run("imagine", "robot")
    assert rc == 0, err
    assert DREAM in out and "robot / sensor" in out
    rc, out, _ = run("dreams")
    assert rc == 0 and DREAM in out and a[:12] in out and "robot / sensor" in out
    with patch.object(cli, "_ollama", side_effect=cli.OllamaUnavailable("connection refused")):
        rc, _, err = run("imagine")
    assert rc == 1 and "Ollama unavailable" in err
    with patch.object(cli, "gate", side_effect=ValueError("contradicts claim 1234")):
        assert run("imagine")[0] == 1
