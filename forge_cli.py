"""
forge_cli.py — The Cockpit CLI (forge)

Function:
    The operator surface for The Legacy. Parses argv, dispatches to
    command handlers, and orchestrates the frozen primitive layers
    P1–P15. Implements no cryptography, storage, trust math, or
    gating itself — every command calls into a frozen primitive.

    Generative commands (dream/think/reason/ask) shell out to LLLM.
    If LLLM is unavailable, they fail cleanly with exit 1. No other
    LLM backend. No cloud fallback.

    Exit codes:
        0    Success
        1    Runtime failure (layer error, LLLM unavailable, gate refusal)
        2    Usage error (bad args, missing required flag, missing ledger)
        130  Interrupted (Ctrl-C during passphrase)

Public API:
    1. main(argv) -> int  — dispatch entry point

Command handlers (private, numbered per-command below):
    remember, cube, cubes, trust, verify-ledger, ledger, health, status,
    dream, think, reason, ask, pending, approve, refuse,
    sign, verify, record, web, migrate-scp

Tier:     Tier 1 — Consumer (The Cockpit)
Depends:  P2, P3, P4, P6, P7, P8, P9, P12, P13, P14, P15
LLM:      LLLM only, via subprocess
Version:  1.0.0 (on freeze; 0.0.0-dev until then)
Licence:  MSL-1.0
Author:   James Gilbert (Giblets Forge)
"""

import os
import sys
import json
import sqlite3
import getpass
import argparse
import subprocess
import hashlib

# ---------------------------------------------------------------------------
# Lazy layer loader. Missing layers degrade to RuntimeError on use,
# not at import time. This lets commands that don't touch a layer
# still run when that layer is absent.
# ---------------------------------------------------------------------------
_LAYER_CACHE = {}

def _layer(name):
    if name in _LAYER_CACHE:
        return _LAYER_CACHE[name]
    here = os.path.dirname(os.path.abspath(__file__))
    # Try both <name>-layer and <name>
    p = None
    for cand in (name + "-layer", name):
        candidate = os.path.abspath(os.path.join(here, "..", cand))
        if os.path.isdir(candidate):
            p = candidate
            break
    if p is None:
        raise RuntimeError(
            f"layer '{name}' not found (tried {name}-layer and {name} "
            f"under {os.path.dirname(p) if p else os.path.join(here, '..')})"
        )
    if p not in sys.path:
        sys.path.insert(0, p)
    # Convert dir name to module name
    modname = name.replace("-", "_").replace("layer", "").strip("_")
    # Special cases matching actual module filenames
    mapping = {
        "envelope": "envelope_v2",
        "sign": "sign",
        "freeze": "freeze",
        "ledger": "ledger",
        "genesis": "genesis",
        "canon-verify": "canon_verify",
        "record": "record",
        "store": "store",
        "substrate": "substrate",
        "weight": "weight",
        "trust": "trust",
        "leighton-engine": "leighton_engine",
        "rules": "rules",
        "datacube": "datacube",
        "hal": "hal",
    }
    base = name.replace("-layer", "")
    modname = mapping.get(base, base.replace("-", "_"))
    import importlib
    mod = importlib.import_module(modname)
    _LAYER_CACHE[name] = mod
    return mod


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
def _forge_home():
    home = os.environ.get("FORGE_HOME")
    if not home:
        home = os.path.expanduser("~/.forge")
        os.makedirs(home, exist_ok=True)
    return home

def _ledger_path():
    return os.path.join(_forge_home(), "ledger.jsonl")

def _db_path():
    return os.path.join(_forge_home(), "forge.db")

def _key_path():
    return os.path.join(_forge_home(), "key.pem")


# ---------------------------------------------------------------------------
# Face validation
# ---------------------------------------------------------------------------
_FACES = ("FACT", "COUNTER", "OPINION", "FICTION", "CONTEXT", "UNKNOWN")
_GATE_FACES = ("FACT", "COUNTER", "CONTEXT")

def _parse_claim(text):
    """Split 'The sky is blue' into {subject, object}. Simple heuristic."""
    t = text.strip()
    for prefix in ("The ", "A ", "An "):
        if t.startswith(prefix):
            t = t[len(prefix):]
            break
    if " is " in t:
        subj, obj = t.split(" is ", 1)
        return {"subject": subj.strip(), "object": obj.strip()}
    words = t.split()
    if len(words) <= 2:
        return {"subject": t, "object": ""}
    mid = len(words) // 2
    return {"subject": " ".join(words[:mid]), "object": " ".join(words[mid:])}


# ---------------------------------------------------------------------------
# Passphrase + key loading
# ---------------------------------------------------------------------------
def _load_key(key_path):
    """Load a PEM private key using getpass. Ctrl-C -> KeyboardInterrupt."""
    passphrase = getpass.getpass(f"Passphrase for {key_path}: ")
    record = _layer("record")
    return record.load_private_key(key_path, passphrase)


# ---------------------------------------------------------------------------
# LLLM availability
# ---------------------------------------------------------------------------
def _lllm_available():
    home = os.environ.get("LLLM_HOME")
    if not home:
        return False, "LLLM_HOME is not set"
    if not os.path.isdir(home):
        return False, f"LLLM_HOME does not exist: {home}"
    return True, ""


def _lllm_call(subcmd, *args):
    """Shell out to lllm. Returns (stdout, build_id) or raises."""
    ok, reason = _lllm_available()
    if not ok:
        raise RuntimeError(f"LLLM unavailable: {reason}")
    try:
        result = subprocess.run(
            ["lllm", subcmd, *args],
            capture_output=True,
            text=True,
            timeout=120,
            check=True,
        )
    except FileNotFoundError:
        raise RuntimeError("LLLM unavailable: `lllm` not on PATH")
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"LLLM failed: {e.stderr.strip()[:200]}")
    # Best-effort build_id extraction from "lllm info"
    build_id = ""
    try:
        info = subprocess.run(["lllm", "info"], capture_output=True, text=True, timeout=10)
        for line in info.stdout.splitlines():
            if "build" in line.lower() and ":" in line:
                build_id = line.split(":", 1)[1].strip().split()[0]
                break
    except Exception:
        pass
    return result.stdout, build_id


# ---------------------------------------------------------------------------
# Substrate helper: enumerate active claims (direct SQL, since substrate
# does not expose a list function; we read its schema, not edit it)
# ---------------------------------------------------------------------------
def _list_active_claims(db_path):
    if not os.path.exists(db_path):
        return []
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT capsule FROM claims WHERE is_active = 1"
        ).fetchall()
    except sqlite3.OperationalError:
        rows = []
    finally:
        conn.close()
    out = []
    for (cap,) in rows:
        try:
            out.append(json.loads(cap))
        except json.JSONDecodeError:
            pass
    return out


# ---------------------------------------------------------------------------
# 1. main — top-level dispatch
# ---------------------------------------------------------------------------
def main(argv):
    try:
        return _dispatch(argv)
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130


def _dispatch(argv):
    if not argv:
        _usage()
        return 2
    cmd = argv[0]
    rest = argv[1:]

    handlers = {
        "remember": _cmd_remember,
        "cube": _cmd_cube,
        "cubes": _cmd_cubes,
        "trust": _cmd_trust,
        "verify-ledger": _cmd_verify_ledger,
        "ledger": _cmd_ledger,
        "health": _cmd_health,
        "status": _cmd_status,
        "dream": _cmd_dream,
        "think": _cmd_think,
        "reason": _cmd_reason,
        "ask": _cmd_ask,
        "pending": _cmd_pending,
        "approve": _cmd_approve,
        "refuse": _cmd_refuse,
        "sign": _cmd_sign,
        "verify": _cmd_verify,
        "record": _cmd_record,
        "web": _cmd_web,
        "migrate-scp": _cmd_migrate_scp,
    }
    handler = handlers.get(cmd)
    if handler is None:
        print(f"unknown command: {cmd}", file=sys.stderr)
        _usage()
        return 2
    return handler(rest)


def _usage():
    print(
        "usage: forge <command> [args]\n"
        "  remember <text> --face <FACE>\n"
        "  cube <id> | cubes [--face <FACE>]\n"
        "  trust <claim_id>\n"
        "  verify-ledger | ledger | health | status\n"
        "  dream | think | reason <q> | ask <q>\n"
        "  pending | approve <id> --key <pem> --lambda <f>\n"
        "           | refuse  <id> --key <pem> --lambda <f> --reason <r>\n"
        "  sign <file> | verify <file> | record <capsule.json> --key <pem>\n"
        "  web | migrate-scp <dir>",
        file=sys.stderr,
    )


# ---------------------------------------------------------------------------
# 2. _cmd_remember — classify, sign, store, append
# ---------------------------------------------------------------------------
def _cmd_remember(rest):
    p = argparse.ArgumentParser(prog="forge remember")
    p.add_argument("text", nargs="+")
    p.add_argument("--face", required=True)
    try:
        args = p.parse_args(rest)
    except SystemExit:
        return 2
    face = args.face.upper()
    if face not in _FACES:
        print(f"invalid face: {face}. must be one of {_FACES}", file=sys.stderr)
        return 2
    text = " ".join(args.text).strip()
    if not text:
        print("empty text", file=sys.stderr)
        return 2

    claim = _parse_claim(text)

    if face == "UNKNOWN":
        existing = _list_active_claims(_db_path())
        gate_input = []
        for cap in existing:
            gate_input.append({
                "subject": cap.get("subject"),
                "object": cap.get("object"),
                "face": cap.get("face", "FACT"),
            })
        dc = _layer("datacube")
        try:
            dc.keystone_gate(claim, gate_input)
        except ValueError as e:
            print(f"keystone gate: {e}", file=sys.stderr)
            return 1

    try:
        dc = _layer("datacube")
        cube = dc.create_cube(claim)
        dc.set_face(cube, face, text)

        key = _load_key(_key_path())

        sign_mod = _layer("sign")
        signed = sign_mod.sign_capsule(cube, key)

        substrate = _layer("substrate")
        substrate.init_db(_db_path())
        claim_id = substrate.write_claim(_db_path(), signed, key)

        ledger = _layer("ledger")
        ledger.append_entry(_ledger_path(), signed, key)

        print(claim_id)
        return 0
    except KeyboardInterrupt:
        raise
    except Exception as e:
        print(f"remember failed: {e}", file=sys.stderr)
        return 1


# ---------------------------------------------------------------------------
# 3. _cmd_cube — fetch a single claim by id
# ---------------------------------------------------------------------------
def _cmd_cube(rest):
    if len(rest) != 1:
        print("usage: forge cube <id>", file=sys.stderr)
        return 2
    try:
        substrate = _layer("substrate")
        cap = substrate.get_claim(_db_path(), rest[0])
    except Exception as e:
        print(f"cube failed: {e}", file=sys.stderr)
        return 1
    if cap is None:
        print(f"claim not found: {rest[0]}", file=sys.stderr)
        return 1
    print(json.dumps(cap, indent=2, sort_keys=True))
    return 0


# ---------------------------------------------------------------------------
# 4. _cmd_cubes — list claims, optional face filter
# ---------------------------------------------------------------------------
def _cmd_cubes(rest):
    p = argparse.ArgumentParser(prog="forge cubes")
    p.add_argument("--face", default=None)
    try:
        args = p.parse_args(rest)
    except SystemExit:
        return 2
    want = None
    if args.face:
        want = args.face.upper()
        if want not in _FACES:
            print(f"invalid face: {want}", file=sys.stderr)
            return 2

    claims = _list_active_claims(_db_path())
    if want:
        claims = [c for c in claims if c.get("face") == want]
    print(json.dumps(claims, indent=2, sort_keys=True))
    return 0


# ---------------------------------------------------------------------------
# 5. _cmd_trust — P14 compute_lambda for a claim
# ---------------------------------------------------------------------------
def _cmd_trust(rest):
    if len(rest) != 1:
        print("usage: forge trust <claim_id>", file=sys.stderr)
        return 2
    try:
        substrate = _layer("substrate")
        cap = substrate.get_claim(_db_path(), rest[0])
        if cap is None:
            print(f"claim not found: {rest[0]}", file=sys.stderr)
            return 1
        observations = [{"timestamp": 0.0, "value": 1.5}]
        import time as _t
        now = _t.time()
        engine = _layer("leighton-engine")
        result = engine.compute_lambda(
            observations, k=0.1, reference_time=now, computed_at=now,
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except Exception as e:
        print(f"trust failed: {e}", file=sys.stderr)
        return 1


# ---------------------------------------------------------------------------
# 6. _cmd_verify_ledger — P6 independent verification
# ---------------------------------------------------------------------------
def _cmd_verify_ledger(rest):
    lp = _ledger_path()
    if not os.path.exists(lp):
        print(f"ledger missing: {lp}", file=sys.stderr)
        return 2
    try:
        cv = _layer("canon-verify")
        key_path = _key_path()
        if not os.path.exists(key_path):
            print(f"key missing: {key_path}", file=sys.stderr)
            return 2
        key = _load_key(key_path)
        env = _layer("envelope")
        did = env.did_key_encode(key.public_key())
        ok = cv.verify_ledger(lp, did)
        if ok:
            print("OK: ledger intact")
            return 0
        print("PROBLEM: ledger verification failed", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        raise
    except Exception as e:
        print(f"verify-ledger failed: {e}", file=sys.stderr)
        return 1


# ---------------------------------------------------------------------------
# 7. _cmd_ledger — print all ledger entries
# ---------------------------------------------------------------------------
def _cmd_ledger(rest):
    lp = _ledger_path()
    if not os.path.exists(lp):
        print(f"ledger missing: {lp}", file=sys.stderr)
        return 2
    count = 0
    with open(lp, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            print(f"seq={entry.get('seq')} hash={entry.get('hash','')[:12]} signer={entry.get('signer','')[:20]}")
            count += 1
    print(f"\n{count} entries", file=sys.stderr)
    return 0


# ---------------------------------------------------------------------------
# 8. _cmd_health — probe each layer
# ---------------------------------------------------------------------------
def _cmd_health(rest):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    checks = []

    def probe(name, fn):
        try:
            fn()
            checks.append((name, "PASS", ""))
        except Exception as e:
            checks.append((name, "FAIL", str(e)[:80]))

    def p1():
        env = _layer("envelope")
        env.canonicalise({"a": 1})
    def p2():
        sign_mod = _layer("sign")
        key = Ed25519PrivateKey.generate()
        signed = sign_mod.sign_capsule({"test": True}, key)
        assert sign_mod.verify_capsule(signed, key.public_key())
    def p3():
        fr = _layer("freeze")
        key = Ed25519PrivateKey.generate()
        out = fr.freeze_capsule({"content": "x"}, key)
        assert "document_sha256" in out
    def p4():
        lg = _layer("ledger")
        assert hasattr(lg, "append_entry")
    def p5():
        gn = _layer("genesis")
        assert hasattr(gn, "mint_genesis")
    def p6():
        cv = _layer("canon-verify")
        assert hasattr(cv, "verify_ledger")
    def p7():
        rec = _layer("record")
        assert hasattr(rec, "load_private_key")
    def p8():
        st = _layer("store")
        assert hasattr(st, "init_db")
    def p9():
        sb = _layer("substrate")
        assert hasattr(sb, "write_claim")
    def p10():
        w = _layer("weight")
        assert w.leighton_weight(1.0, 0.0, 0.1) == 1.0
    def p11():
        tr = _layer("trust")
        assert hasattr(tr, "calculate_lambda")
    def p12():
        ru = _layer("rules")
        eng = ru.create_engine()
        assert eng.list_rules() == []
    def p13():
        dc = _layer("datacube")
        cube = dc.create_cube({"subject": "x", "object": "y"})
        assert dc.count_faces(cube) == 0
    def p14():
        le = _layer("leighton-engine")
        result = le.compute_lambda(
            [{"timestamp": 0.0, "value": 1.5}],
            k=0.1, reference_time=0.0, computed_at=0.0,
        )
        assert "lambda" in result
    def p15():
        h = _layer("hal")
        assert h.tier_for_lambda(2.0) == "AUTHORITY"

    probe("P1 Envelope", p1)
    probe("P2 Sign", p2)
    probe("P3 Freeze", p3)
    probe("P4 Ledger", p4)
    probe("P5 Genesis", p5)
    probe("P6 Canon Verify", p6)
    probe("P7 Record", p7)
    probe("P8 Store", p8)
    probe("P9 Substrate", p9)
    probe("P10 Weight", p10)
    probe("P11 Trust", p11)
    probe("P12 Rules", p12)
    probe("P13 DataCube", p13)
    probe("P14 Leighton Engine", p14)
    probe("P15 HAL", p15)

    for name, status, reason in checks:
        pad = " " * max(0, 24 - len(name))
        line = f"{name}{pad} {status}"
        if reason:
            line += f"  ({reason})"
        print(line)
    any_fail = any(s == "FAIL" for _, s, _ in checks)
    return 1 if any_fail else 0


# ---------------------------------------------------------------------------
# 9. _cmd_status — comprehensive summary
# ---------------------------------------------------------------------------
def _cmd_status(rest):
    home = _forge_home()
    print(f"FORGE_HOME: {home}")
    print(f"ledger:     {_ledger_path()} ({'exists' if os.path.exists(_ledger_path()) else 'missing'})")
    print(f"db:         {_db_path()} ({'exists' if os.path.exists(_db_path()) else 'missing'})")
    print(f"key:        {_key_path()} ({'exists' if os.path.exists(_key_path()) else 'missing'})")
    claims = _list_active_claims(_db_path())
    print(f"claims:     {len(claims)} active")
    ll_home = os.environ.get("LLLM_HOME", "(unset)")
    print(f"LLLM_HOME:  {ll_home}")
    return 0


# ---------------------------------------------------------------------------
# 10. _cmd_dream — LLLM generate, Keystone Gate, store as UNKNOWN
# ---------------------------------------------------------------------------
def _cmd_dream(rest):
    try:
        text, build_id = _lllm_call("gen", "dream")
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 1

    claim = _parse_claim(text.split("\n")[0][:200])
    existing = _list_active_claims(_db_path())
    gate_input = []
    for cap in existing:
        gate_input.append({
            "subject": cap.get("subject"),
            "object": cap.get("object"),
            "face": cap.get("face", "FACT"),
        })
    dc = _layer("datacube")
    try:
        dc.keystone_gate(claim, gate_input)
    except ValueError as e:
        print(f"keystone gate: {e}", file=sys.stderr)
        return 1

    try:
        cube = dc.create_cube(claim)
        dc.set_face(cube, "UNKNOWN", text[:500])
        cube["build_id"] = build_id
        cube["lllm_output_sha256"] = hashlib.sha256(text.encode("utf-8")).hexdigest()

        key = _load_key(_key_path())
        sign_mod = _layer("sign")
        signed = sign_mod.sign_capsule(cube, key)
        substrate = _layer("substrate")
        substrate.init_db(_db_path())
        claim_id = substrate.write_claim(_db_path(), signed, key)
        ledger = _layer("ledger")
        ledger.append_entry(_ledger_path(), signed, key)
        print(f"claim_id={claim_id}")
        print(f"build_id={build_id}")
        return 0
    except KeyboardInterrupt:
        raise
    except Exception as e:
        print(f"dream failed: {e}", file=sys.stderr)
        return 1


# ---------------------------------------------------------------------------
# 11. _cmd_think — LLLM generate, sign, store (no gate)
# ---------------------------------------------------------------------------
def _cmd_think(rest):
    try:
        text, build_id = _lllm_call("gen", "think")
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 1
    try:
        dc = _layer("datacube")
        cube = dc.create_cube(_parse_claim(text.split("\n")[0][:200]))
        dc.set_face(cube, "OPINION", text[:500])
        cube["build_id"] = build_id
        key = _load_key(_key_path())
        sign_mod = _layer("sign")
        signed = sign_mod.sign_capsule(cube, key)
        substrate = _layer("substrate")
        substrate.init_db(_db_path())
        claim_id = substrate.write_claim(_db_path(), signed, key)
        ledger = _layer("ledger")
        ledger.append_entry(_ledger_path(), signed, key)
        print(claim_id)
        return 0
    except KeyboardInterrupt:
        raise
    except Exception as e:
        print(f"think failed: {e}", file=sys.stderr)
        return 1


# ---------------------------------------------------------------------------
# 12. _cmd_reason — LLLM over substrate
# ---------------------------------------------------------------------------
def _cmd_reason(rest):
    if not rest:
        print("usage: forge reason <question>", file=sys.stderr)
        return 2
    q = " ".join(rest)
    try:
        text, build_id = _lllm_call("gen", q)
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 1
    try:
        dc = _layer("datacube")
        cube = dc.create_cube(_parse_claim(q[:200]))
        dc.set_face(cube, "CONTEXT", text[:500])
        cube["build_id"] = build_id
        key = _load_key(_key_path())
        sign_mod = _layer("sign")
        signed = sign_mod.sign_capsule(cube, key)
        substrate = _layer("substrate")
        substrate.init_db(_db_path())
        claim_id = substrate.write_claim(_db_path(), signed, key)
        ledger = _layer("ledger")
        ledger.append_entry(_ledger_path(), signed, key)
        print(claim_id)
        return 0
    except KeyboardInterrupt:
        raise
    except Exception as e:
        print(f"reason failed: {e}", file=sys.stderr)
        return 1


# ---------------------------------------------------------------------------
# 13. _cmd_ask — LLLM ask, return answer + citation
# ---------------------------------------------------------------------------
def _cmd_ask(rest):
    if not rest:
        print("usage: forge ask <question>", file=sys.stderr)
        return 2
    q = " ".join(rest)
    try:
        text, build_id = _lllm_call("ask", q)
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 1
    print(text)
    if build_id:
        print(f"\n[build_id: {build_id}]", file=sys.stderr)
    return 0


# ---------------------------------------------------------------------------
# 14. _cmd_pending — list unsigned HAL proposals
# ---------------------------------------------------------------------------
def _cmd_pending(rest):
    lp = _ledger_path()
    pending = []
    if os.path.exists(lp):
        with open(lp, "r") as f:
            for line in f:
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                rec = entry.get("record", {})
                if rec.get("pending_hal"):
                    pending.append({
                        "seq": entry.get("seq"),
                        "hash": entry.get("hash", "")[:12],
                        "record": rec,
                    })
    print(json.dumps(pending, indent=2, sort_keys=True))
    return 0


# ---------------------------------------------------------------------------
# 15. _cmd_approve — P15 create_seal(approve)
# ---------------------------------------------------------------------------
def _cmd_approve(rest):
    p = argparse.ArgumentParser(prog="forge approve")
    p.add_argument("id")
    p.add_argument("--key", required=True)
    p.add_argument("--lambda", dest="lam", type=float, required=True)
    try:
        args = p.parse_args(rest)
    except SystemExit:
        return 2
    hal = _layer("hal")
    if not hal.can_validate(args.lam):
        print(f"quarantine: lambda={args.lam} below threshold 0.60", file=sys.stderr)
        return 2
    try:
        key = _load_key(args.key)
        seal = hal.create_seal(
            decision="approve",
            action_type="pending_action",
            subject_id=args.id,
            rationale="approved via forge",
            validator_lambda=args.lam,
            timestamp=0.0,
        )
        signed = hal.sign_seal(seal, key)
        ledger = _layer("ledger")
        ledger.append_entry(_ledger_path(), signed, key)
        env = _layer("envelope")
        print(env.sha256_hex(env.canonical_bytes(signed)))
        return 0
    except KeyboardInterrupt:
        raise
    except ValueError as e:
        print(f"approve refused: {e}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"approve failed: {e}", file=sys.stderr)
        return 1


# ---------------------------------------------------------------------------
# 16. _cmd_refuse — P15 create_seal(refuse)
# ---------------------------------------------------------------------------
def _cmd_refuse(rest):
    p = argparse.ArgumentParser(prog="forge refuse")
    p.add_argument("id")
    p.add_argument("--key", required=True)
    p.add_argument("--lambda", dest="lam", type=float, required=True)
    p.add_argument("--reason", required=True)
    try:
        args = p.parse_args(rest)
    except SystemExit:
        return 2
    hal = _layer("hal")
    if not hal.can_validate(args.lam):
        print(f"quarantine: lambda={args.lam} below threshold 0.60", file=sys.stderr)
        return 2
    try:
        key = _load_key(args.key)
        seal = hal.create_seal(
            decision="refuse",
            action_type="pending_action",
            subject_id=args.id,
            rationale=args.reason,
            validator_lambda=args.lam,
            timestamp=0.0,
        )
        signed = hal.sign_seal(seal, key)
        ledger = _layer("ledger")
        ledger.append_entry(_ledger_path(), signed, key)
        env = _layer("envelope")
        print(env.sha256_hex(env.canonical_bytes(signed)))
        return 0
    except KeyboardInterrupt:
        raise
    except ValueError as e:
        print(f"refuse refused: {e}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"refuse failed: {e}", file=sys.stderr)
        return 1


# ---------------------------------------------------------------------------
# 17. _cmd_sign — P2 sign_artifact
# ---------------------------------------------------------------------------
def _cmd_sign(rest):
    if len(rest) != 1:
        print("usage: forge sign <file>", file=sys.stderr)
        return 2
    try:
        key = _load_key(_key_path())
        sign_mod = _layer("sign")
        sig_path = sign_mod.sign_artifact(rest[0], key)
        print(sig_path)
        return 0
    except KeyboardInterrupt:
        raise
    except Exception as e:
        print(f"sign failed: {e}", file=sys.stderr)
        return 1


# ---------------------------------------------------------------------------
# 18. _cmd_verify — P2 verify_artifact
# ---------------------------------------------------------------------------
def _cmd_verify(rest):
    if len(rest) != 1:
        print("usage: forge verify <file>", file=sys.stderr)
        return 2
    try:
        key = _load_key(_key_path())
        sign_mod = _layer("sign")
        ok = sign_mod.verify_artifact(rest[0], rest[0] + ".sig", key.public_key())
        print("OK" if ok else "PROBLEM")
        return 0 if ok else 1
    except KeyboardInterrupt:
        raise
    except Exception as e:
        print(f"verify failed: {e}", file=sys.stderr)
        return 1


# ---------------------------------------------------------------------------
# 19. _cmd_record — P7 save_signed_record
# ---------------------------------------------------------------------------
def _cmd_record(rest):
    p = argparse.ArgumentParser(prog="forge record")
    p.add_argument("capsule")
    p.add_argument("--key", required=True)
    try:
        args = p.parse_args(rest)
    except SystemExit:
        return 2
    try:
        with open(args.capsule, "r") as f:
            cap = json.load(f)
        key = _load_key(args.key)
        record = _layer("record")
        out = args.capsule + ".sc.json"
        record.save_signed_record(cap, out, key)
        print(out)
        return 0
    except KeyboardInterrupt:
        raise
    except Exception as e:
        print(f"record failed: {e}", file=sys.stderr)
        return 1


# ---------------------------------------------------------------------------
# 20. _cmd_web — minimal placeholder (read-only UI stub)
# ---------------------------------------------------------------------------
def _cmd_web(rest):
    print("web UI not yet implemented in v1 (read-only stub)", file=sys.stderr)
    print("see SPEC.md §10", file=sys.stderr)
    return 1


# ---------------------------------------------------------------------------
# 21. _cmd_migrate_scp — one-way .scp.json importer
# ---------------------------------------------------------------------------
def _cmd_migrate_scp(rest):
    if len(rest) != 1:
        print("usage: forge migrate-scp <dir>", file=sys.stderr)
        return 2
    root = rest[0]
    if not os.path.isdir(root):
        print(f"not a directory: {root}", file=sys.stderr)
        return 1
    scp_files = []
    for dirpath, _, filenames in os.walk(root):
        for fn in filenames:
            if fn.endswith(".scp.json"):
                scp_files.append(os.path.join(dirpath, fn))
    if not scp_files:
        print(f"no .scp.json files found in {root}", file=sys.stderr)
        return 1
    try:
        key = _load_key(_key_path())
        dc = _layer("datacube")
        sign_mod = _layer("sign")
        substrate = _layer("substrate")
        ledger = _layer("ledger")
        substrate.init_db(_db_path())
        migrated = 0
        for path in scp_files:
            try:
                with open(path, "r") as f:
                    payload = json.load(f)
            except (json.JSONDecodeError, IOError):
                continue
            claim = _parse_claim(str(payload)[:200])
            cube = dc.create_cube(claim)
            dc.set_face(cube, "CONTEXT", json.dumps(payload, sort_keys=True)[:1000])
            cube["migrated_from"] = path
            signed = sign_mod.sign_capsule(cube, key)
            substrate.write_claim(_db_path(), signed, key)
            ledger.append_entry(_ledger_path(), signed, key)
            migrated += 1
        print(f"migrated {migrated}/{len(scp_files)}")
        return 0
    except KeyboardInterrupt:
        raise
    except Exception as e:
        print(f"migrate-scp failed: {e}", file=sys.stderr)
        return 1


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
