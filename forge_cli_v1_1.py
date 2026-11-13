"""
forge_cli_v1_1.py — The Cockpit CLI v1.1 (current-layer wiring)

Function:
    The layer above the frozen Cockpit v1.0.0 (forge_cli.py), and the
    entry point to run from v1.1 on. It routes every command through
    the current layer of each primitive instead of the frozen v1
    modules, mirrors the ledger into P8, records each claim's face so
    the Keystone Gate and `cubes` see real faces, computes trust with
    an explicit time unit, gives HAL proposals a way to exist, and
    links seals to their claims in P9 (SPEC_V1_1.md).

    forge_cli.py is not edited and is never patched globally: its own
    v1 tests still run on v1 in the same process.

    Exit codes are SPEC.md's: 0 success, 1 runtime failure, 2 usage
    error (and quarantine), 130 interrupted.

Public API:
    1. main(argv) -> int
    2. probe_layers() -> list[dict]   (also used by The Legacy)

Internal helpers (numbered below):
    3.  _layer          — current-layer module loader
    4.  _store_path     — FORGE_HOME/store.db
    5.  _load_key       — getpass + P7 v2
    6.  _face_of        — a capsule's face (v1.1 key or single filled face)
    7.  _memory         — active claims as Keystone Gate input
    8.  _capsule        — P13 cube + face + provenance
    9.  _check_ledger   — CRLF and P4 v2 checks before any write
    10. _append         — P5 genesis or P4 append, then the P8 mirror
    11. _mirror         — bring store.db level with the ledger, compare bytes
    12. _commit         — P9 write (idempotent), then _append
    13. _ledger_entries — parsed ledger lines
    14. _pending        — open HAL proposals
    15. _with_current   — run a v1 handler with forge_cli._layer swapped in
    16. _usage

Command handlers (17–30, numbered below): remember, _store_claim,
    dream/think/reason, cube, cubes, trust, verify-ledger, health,
    status, propose, pending, approve/refuse, web, migrate-scp.
    ask, ledger, sign, verify and record are v1.0.0's.

Tier:     Tier 1 — Consumer (The Cockpit)
Depends:  P1–P15, current layers (SPEC_V1_1.md header)
Spec:     SPEC_V1_1.md 1.1.0 (over SPEC.md 1.0.0)
Version:  1.1.0
Licence:  MSL-1.0
Author:   James Gilbert (Giblets Forge)
"""

import argparse
import getpass
import hashlib
import importlib
import json
import os
import sys
import tempfile
import time
from datetime import datetime

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import forge_cli as _v1  # noqa: E402

from forge_cli import (  # noqa: E402
    _FACES, _db_path, _forge_home, _key_path, _ledger_path,
    _lllm_call, _parse_claim,
)

CLAIM_LAMBDA_ZERO = 1.5
_CURRENT = {
    "envelope": "envelope_v2", "sign": "sign_v2", "freeze": "freeze_v2",
    "ledger": "ledger_v2", "genesis": "genesis_v3", "canon-verify": "canon_verify_v2",
    "record": "record_v2", "store": "store_v2_1", "substrate": "substrate_v3",
    "weight": "weight_v2", "trust": "trust_v2", "leighton-engine": "leighton_engine_v3",
    "rules": "rules_v3", "datacube": "datacube_v2", "hal": "hal_v2",
}
_CACHE = {}


# ---------------------------------------------------------------------------
# 3. _layer
#    SPEC_V1_1 §2. Sibling <name>-layer directory, current module.
# ---------------------------------------------------------------------------
def _layer(name):
    if name in _CACHE:
        return _CACHE[name]
    path = os.path.abspath(os.path.join(_HERE, "..", name + "-layer"))
    if not os.path.isdir(path):
        raise RuntimeError(f"layer '{name}' not found at {path}")
    if path not in sys.path:
        sys.path.insert(0, path)
    mod = importlib.import_module(_CURRENT[name])
    _CACHE[name] = mod
    return mod


# ---------------------------------------------------------------------------
# 4. _store_path
# ---------------------------------------------------------------------------
def _store_path():
    return os.path.join(_forge_home(), "store.db")


# ---------------------------------------------------------------------------
# 5. _load_key
#    Passphrase via getpass only (SPEC.md §9); P7 v2 refuses non-Ed25519.
# ---------------------------------------------------------------------------
def _load_key(key_path):
    passphrase = getpass.getpass(f"Passphrase for {key_path}: ")
    return _layer("record").load_private_key(key_path, passphrase)


# ---------------------------------------------------------------------------
# 6. _face_of
#    SPEC_V1_1 §5: the `face` key, else the single filled face, else None.
# ---------------------------------------------------------------------------
def _face_of(capsule):
    if not isinstance(capsule, dict):
        return None
    if capsule.get("face") in _FACES:
        return capsule["face"]
    filled = [f for f in _FACES if isinstance(capsule.get(f), str) and capsule[f]]
    return filled[0] if len(filled) == 1 else None


# ---------------------------------------------------------------------------
# 7. _memory
#    Active claims as gate input. A claim with no face is corrupt memory:
#    raise, so the gate fails closed (P13 SPEC_V2 §2.3).
# ---------------------------------------------------------------------------
def _memory():
    if not os.path.exists(_db_path()):
        return []
    out = []
    for row in _layer("substrate").list_claims(_db_path()):
        cap = row["capsule"] or {}
        face = _face_of(cap)
        if face is None:
            raise ValueError(f"claim {row['claim_id'][:12]} has no single face; gate fails closed")
        out.append({"subject": cap.get("subject"), "object": cap.get("object"), "face": face})
    return out


# ---------------------------------------------------------------------------
# 8. _capsule
#    SPEC_V1_1 §4 step 2.
# ---------------------------------------------------------------------------
def _capsule(claim, face, text, **extra):
    dc = _layer("datacube")
    cube = dc.create_cube(claim)
    dc.set_face(cube, face, text)
    return dict(cube, face=face, **extra)


# ---------------------------------------------------------------------------
# 9. _check_ledger
#    SPEC_V1_1 §4 step 1. Runs before anything is written.
# ---------------------------------------------------------------------------
def _check_ledger(key):
    lp = _ledger_path()
    if not os.path.exists(lp) or os.path.getsize(lp) == 0:
        return
    with open(lp, "rb") as f:
        data = f.read()
    if b"\r" in data:
        raise ValueError("ledger has CRLF line endings (written by Cockpit v1.0 on Windows); "
                         "convert it to LF first, see ledger-layer NOTES D1")
    if not _layer("ledger").verify_ledger(lp, key.public_key()):
        raise ValueError("ledger does not verify under the operator key")


# ---------------------------------------------------------------------------
# 11. _mirror
#    SPEC_V1_1 §4 step 5. Appends what store.db lacks, then requires the
#    store's .jsonl image to equal the ledger byte for byte.
# ---------------------------------------------------------------------------
def _mirror(key):
    store = _layer("store")
    sp, lp = _store_path(), _ledger_path()
    store.init_db(sp)
    with open(lp, "rb") as f:
        ledger_bytes = f.read()
    have = store.export_jsonl(sp).count(b"\n")
    for line in ledger_bytes.splitlines()[have:]:
        store.append_entry(sp, json.loads(line)["record"], key)
    if store.export_jsonl(sp) != ledger_bytes:
        raise RuntimeError("P8 store diverged from ledger")


# ---------------------------------------------------------------------------
# 10. _append
#    SPEC_V1_1 §4 steps 4–5.
# ---------------------------------------------------------------------------
def _append(record, key):
    lp = _ledger_path()
    if not os.path.exists(lp) or os.path.getsize(lp) == 0:
        if os.path.exists(lp):
            os.remove(lp)  # an empty file: genesis_v2 creates it exclusively
        entry = _layer("genesis").mint_genesis(lp, record, key)
    else:
        entry = _layer("ledger").append_entry(lp, record, key)
    _mirror(key)
    return entry


# ---------------------------------------------------------------------------
# 12. _commit
#    SPEC_V1_1 §4 steps 1–5. Returns (claim_id, ledger entry or None when
#    the claim was already remembered).
# ---------------------------------------------------------------------------
def _commit(capsule, key):
    env, sign, sub = _layer("envelope"), _layer("sign"), _layer("substrate")
    _check_ledger(key)
    signed = sign.sign_capsule(capsule, key)
    claim_id = env.sha256_hex(env.canonical_bytes(signed))
    db = _db_path()
    sub.init_db(db)
    if sub.read_claim(db, claim_id) is not None:
        return claim_id, None
    written = sub.write_claim(db, capsule, key)
    if written != claim_id:
        raise RuntimeError("P9 claim id differs from the signed capsule's hash")
    return claim_id, _append(sub.get_claim(db, claim_id), key)


# ---------------------------------------------------------------------------
# 13. _ledger_entries
# ---------------------------------------------------------------------------
def _ledger_entries():
    lp = _ledger_path()
    if not os.path.exists(lp):
        return []
    with open(lp, "rb") as f:
        return [json.loads(line) for line in f.read().splitlines() if line.strip()]


# ---------------------------------------------------------------------------
# 14. _pending
#    SPEC_V1_1 §7: proposals with no later seal for the same subject and
#    action type.
# ---------------------------------------------------------------------------
def _pending():
    open_ = []
    for entry in _ledger_entries():
        rec = entry.get("record") or {}
        if rec.get("pending_hal") is True:
            open_.append({"seq": entry["seq"], "hash": entry["hash"],
                          "action_type": rec.get("action_type"),
                          "subject_id": rec.get("subject_id"), "note": rec.get("note", "")})
        elif "decision" in rec and "seal_version" in rec:
            open_ = [p for p in open_ if (p["subject_id"], p["action_type"])
                     != (rec.get("subject_id"), rec.get("action_type"))]
    return open_


# ---------------------------------------------------------------------------
# 15. _with_current
#    Runs an unchanged v1.0.0 handler with forge_cli._layer pointing at the
#    current layers for the duration of the call only (SPEC_V1_1 §11).
# ---------------------------------------------------------------------------
def _with_current(handler):
    def run(rest):
        saved = _v1._layer
        _v1._layer = _layer
        try:
            return handler(rest)
        finally:
            _v1._layer = saved
    return run


# ---------------------------------------------------------------------------
# 2. probe_layers
#    SPEC_V1_1 §9. One real round trip per layer, in a private temp dir.
# ---------------------------------------------------------------------------
def probe_layers():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    rows = []
    key = Ed25519PrivateKey.generate()
    pub = key.public_key()
    with tempfile.TemporaryDirectory() as tmp:
        lp, sp, db = (os.path.join(tmp, n) for n in ("l.jsonl", "s.db", "f.db"))

        def p1():
            assert _layer("envelope").canonicalise({"b": 1, "a": 2}) == '{"a":2,"b":1}'

        def p2():
            s = _layer("sign")
            assert s.verify_capsule(s.sign_capsule({"t": 1}, key), pub)

        def p3():
            fr = _layer("freeze")
            assert fr.verify_frozen_capsule(fr.freeze_capsule({"c": "x"}, key), pub)

        def p5():
            gn = _layer("genesis")
            gn.mint_genesis(lp, {"probe": "genesis"}, key)
            assert gn.verify_genesis(lp, pub)

        def p4():
            lg = _layer("ledger")
            lg.append_entry(lp, {"probe": "ledger"}, key)
            assert lg.verify_ledger(lp, pub)

        def p6():
            assert _layer("canon-verify").verify_ledger(lp, _layer("envelope").did_key_encode(pub))

        def p7():
            rec = _layer("record")
            pem = os.path.join(tmp, "k.pem")
            with open(pem, "wb") as f:
                f.write(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                          serialization.BestAvailableEncryption(b"probe")))
            k2 = rec.load_private_key(pem, "probe")
            out = os.path.join(tmp, "r.sc.json")
            rec.save_signed_record({"probe": 7}, out, k2)
            assert rec.verify_record_file(out, pub)

        def p8():
            st = _layer("store")
            st.init_db(sp)
            st.append_entry(sp, {"probe": "genesis"}, key)
            st.append_entry(sp, {"probe": "ledger"}, key)
            assert st.verify_store(sp, pub)
            with open(lp, "rb") as f:
                assert st.export_jsonl(sp) == f.read()

        def p9():
            sub = _layer("substrate")
            sub.init_db(db)
            cid = sub.write_claim(db, {"subject": "a", "object": "b"}, key)
            assert sub.read_claim(db, cid, verify=True)["verified"]

        def p10():
            assert _layer("weight").leighton_weight(1.5, 0.0, 0.1) == 1.5

        def p11():
            assert _layer("trust").calculate_lambda([{"timestamp": 0.0, "value": 1.5}], 0.1, 0.0) == 1.5

        def p12():
            ru = _layer("rules")
            rules = ru.load_rules([{"name": "all", "predicate_spec": {}}])
            assert ru.preview(rules, _layer("sign").sign_capsule({"x": 1}, key), pub) == ["all"]

        def p13():
            dc = _layer("datacube")
            dc.create_cube({"subject": "a", "object": "b"})
            try:
                dc.keystone_gate({"subject": "a", "object": "c", "face": "UNKNOWN"},
                                 [{"subject": "a", "object": "b", "face": "FACT"}])
            except ValueError:
                return
            raise AssertionError("gate did not refuse a contradiction")

        def p14():
            le = _layer("leighton-engine")
            r = le.compute_lambda([{"timestamp": 0.0, "value": 1.5}], le.STACK_CLAIM_K, 864000.0, 0.0,
                                  time_unit=le.STACK_TIME_UNIT)
            assert le.reproduce_lambda(r["parameters"]) == r["lambda"]

        def p15():
            h = _layer("hal")
            assert h.tier_for_lambda(2.0) == "AUTHORITY" and not h.can_validate(0.5)

        order = [("P1 Envelope", p1), ("P2 Sign", p2), ("P3 Freeze", p3),
                 ("P5 Genesis", p5), ("P4 Ledger", p4), ("P6 Canon Verify", p6),
                 ("P7 Record", p7), ("P8 Store", p8), ("P9 Substrate", p9),
                 ("P10 Weight", p10), ("P11 Trust", p11), ("P12 Rules", p12),
                 ("P13 DataCube", p13), ("P14 Leighton Engine", p14), ("P15 HAL", p15)]
        for name, fn in order:
            try:
                fn()
                rows.append({"layer": name, "status": "PASS", "error": ""})
            except Exception as e:  # a broken layer is a FAIL row, never a crash
                rows.append({"layer": name, "status": "FAIL", "error": f"{type(e).__name__}: {e}"[:100]})
    rows.sort(key=lambda r: int(r["layer"].split()[0][1:]))
    return rows


# ---------------------------------------------------------------------------
# 17. _cmd_remember
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
    claim = _parse_claim(text)
    if not claim["subject"] or not claim["object"]:
        print(f"cannot split {text!r} into subject and object; "
              "phrase it as '<subject> is <object>'", file=sys.stderr)
        return 2
    return _store_claim(claim, face, text, label="remember")


# ---------------------------------------------------------------------------
# 18. _store_claim
#     Shared by remember / dream / think / reason: gate if UNKNOWN, then commit.
# ---------------------------------------------------------------------------
def _store_claim(claim, face, text, label, **extra):
    try:
        if face == "UNKNOWN":
            try:
                _layer("datacube").keystone_gate(claim, _memory())
            except ValueError as e:
                print(f"keystone gate: {e}", file=sys.stderr)
                return 1
        capsule = _capsule(claim, face, text, **extra)
        key = _load_key(_key_path())
        claim_id, entry = _commit(capsule, key)
    except KeyboardInterrupt:
        raise
    except Exception as e:
        print(f"{label} failed: {e}", file=sys.stderr)
        return 1
    if entry is None:
        print("already remembered; nothing appended", file=sys.stderr)
    if "build_id" in extra:
        print(f"claim_id={claim_id}")
        print(f"build_id={extra['build_id']}")
    else:
        print(claim_id)
    return 0


# ---------------------------------------------------------------------------
# 19. _cmd_generated
#     dream (UNKNOWN, gated), think (OPINION), reason (CONTEXT).
# ---------------------------------------------------------------------------
def _cmd_generated(kind, face, rest):
    if kind == "reason" and not rest:
        print("usage: forge reason <question>", file=sys.stderr)
        return 2
    prompt = " ".join(rest) if kind == "reason" else kind
    try:
        text, build_id = _lllm_call("gen", prompt)
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 1
    source = prompt if kind == "reason" else text.split("\n")[0]
    claim = _parse_claim(source[:200])
    if not claim["subject"] or not claim["object"]:
        print(f"{kind} parse failed: no subject and object in {source[:60]!r}", file=sys.stderr)
        return 1
    extra = {"build_id": build_id}
    if kind == "dream":
        extra["lllm_output_sha256"] = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return _store_claim(claim, face, text[:500], label=kind, **extra)


# ---------------------------------------------------------------------------
# 20. _cmd_cube
# ---------------------------------------------------------------------------
def _cmd_cube(rest):
    if len(rest) != 1:
        print("usage: forge cube <id>", file=sys.stderr)
        return 2
    try:
        sub = _layer("substrate")
        row = sub.read_claim(_db_path(), rest[0], verify=True)
        if row is None:
            print(f"claim not found: {rest[0]}", file=sys.stderr)
            return 1
        row["face"] = _face_of(row["capsule"])
        row["attestation"] = sub.latest_attestation(_db_path(), rest[0])
    except FileNotFoundError:
        print("no substrate yet", file=sys.stderr)
        return 1
    print(json.dumps(row, indent=2, sort_keys=True))
    return 0


# ---------------------------------------------------------------------------
# 21. _cmd_cubes
# ---------------------------------------------------------------------------
def _cmd_cubes(rest):
    p = argparse.ArgumentParser(prog="forge cubes")
    p.add_argument("--face", default=None)
    try:
        args = p.parse_args(rest)
    except SystemExit:
        return 2
    want = args.face.upper() if args.face else None
    if want and want not in _FACES:
        print(f"invalid face: {want}", file=sys.stderr)
        return 2
    rows = []
    if os.path.exists(_db_path()):
        for row in _layer("substrate").list_claims(_db_path(), verify=True):
            cap = row["capsule"] or {}
            face = _face_of(cap)
            if want and face != want:
                continue
            rows.append({"claim_id": row["claim_id"], "face": face, "verified": row["verified"],
                         "subject": cap.get("subject"), "object": cap.get("object"), "capsule": cap})
    print(json.dumps(rows, indent=2, sort_keys=True))
    return 0


# ---------------------------------------------------------------------------
# 22. _cmd_trust
#     SPEC_V1_1 §6.
# ---------------------------------------------------------------------------
def _cmd_trust(rest):
    if len(rest) != 1:
        print("usage: forge trust <claim_id>", file=sys.stderr)
        return 2
    try:
        row = _layer("substrate").read_claim(_db_path(), rest[0]) if os.path.exists(_db_path()) else None
        if row is None:
            print(f"claim not found: {rest[0]}", file=sys.stderr)
            return 1
        le = _layer("leighton-engine")
        created = datetime.fromisoformat(row["created_at"]).timestamp()
        now = max(time.time(), created)
        result = le.compute_lambda([{"timestamp": created, "value": CLAIM_LAMBDA_ZERO}],
                                   le.STACK_CLAIM_K, now, now, time_unit=le.STACK_TIME_UNIT)
    except Exception as e:
        print(f"trust failed: {e}", file=sys.stderr)
        return 1
    result["claim_id"] = rest[0]
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


# ---------------------------------------------------------------------------
# 23. _cmd_verify_ledger
#     SPEC_V1_1 §8.
# ---------------------------------------------------------------------------
def _cmd_verify_ledger(rest):
    lp = _ledger_path()
    if not os.path.exists(lp) or os.path.getsize(lp) == 0:
        print(f"no ledger yet: {lp}", file=sys.stderr)
        return 2
    if not os.path.exists(_key_path()):
        print(f"key missing: {_key_path()}", file=sys.stderr)
        return 2
    try:
        key = _load_key(_key_path())
        did = _layer("envelope").did_key_encode(key.public_key())
        if not _layer("canon-verify").verify_ledger(lp, did):
            print("PROBLEM: ledger verification failed (P6)", file=sys.stderr)
            return 1
        print("OK: ledger intact (P6 zero-trust)")
        sp = _store_path()
        if not os.path.exists(sp):
            print("P8 store: not created yet")
            return 0
        store = _layer("store")
        with open(lp, "rb") as f:
            same = store.export_jsonl(sp) == f.read()
        if not (store.verify_store(sp, key.public_key()) and same):
            print("PROBLEM: P8 store does not verify or does not mirror the ledger", file=sys.stderr)
            return 1
        print("OK: P8 store verifies and mirrors the ledger")
        return 0
    except KeyboardInterrupt:
        raise
    except Exception as e:
        print(f"verify-ledger failed: {e}", file=sys.stderr)
        return 1


# ---------------------------------------------------------------------------
# 24. _cmd_health
# ---------------------------------------------------------------------------
def _cmd_health(rest):
    rows = probe_layers()
    for r in rows:
        line = f"{r['layer']:<24} {r['status']}"
        if r["error"]:
            line += f"  ({r['error']})"
        print(line)
    return 1 if any(r["status"] == "FAIL" for r in rows) else 0


# ---------------------------------------------------------------------------
# 25. _cmd_status
# ---------------------------------------------------------------------------
def _cmd_status(rest):
    def state(path):
        return "exists" if os.path.exists(path) else "missing"
    print(f"FORGE_HOME: {_forge_home()}")
    for label, path in (("ledger", _ledger_path()), ("db", _db_path()),
                        ("store", _store_path()), ("key", _key_path())):
        print(f"{label + ':':<11} {path} ({state(path)})")
    claims = _layer("substrate").list_claims(_db_path()) if os.path.exists(_db_path()) else []
    print(f"claims:     {len(claims)} active")
    print(f"entries:    {len(_ledger_entries())} in ledger")
    print(f"pending:    {len(_pending())} HAL proposals")
    print(f"LLLM_HOME:  {os.environ.get('LLLM_HOME', '(unset)')}")
    return 0


# ---------------------------------------------------------------------------
# 26. _cmd_propose
#     SPEC_V1_1 §7.
# ---------------------------------------------------------------------------
def _cmd_propose(rest):
    p = argparse.ArgumentParser(prog="forge propose")
    p.add_argument("claim_id")
    p.add_argument("--action", required=True)
    p.add_argument("--note", default="")
    try:
        args = p.parse_args(rest)
    except SystemExit:
        return 2
    try:
        if not os.path.exists(_db_path()) or _layer("substrate").read_claim(_db_path(), args.claim_id) is None:
            print(f"claim not found: {args.claim_id}", file=sys.stderr)
            return 1
        key = _load_key(_key_path())
        _check_ledger(key)
        record = _layer("sign").sign_capsule({
            "pending_hal": True, "action_type": args.action, "subject_id": args.claim_id,
            "note": args.note, "proposed_at": time.time(), "signature": None,
        }, key)
        entry = _append(record, key)
    except KeyboardInterrupt:
        raise
    except Exception as e:
        print(f"propose failed: {e}", file=sys.stderr)
        return 1
    print(f"seq={entry['seq']} hash={entry['hash'][:12]}")
    return 0


# ---------------------------------------------------------------------------
# 27. _cmd_pending
# ---------------------------------------------------------------------------
def _cmd_pending(rest):
    shown = [dict(p, hash=p["hash"][:12]) for p in _pending()]
    print(json.dumps(shown, indent=2, sort_keys=True))
    return 0


# ---------------------------------------------------------------------------
# 28. _cmd_decide
#     approve / refuse. SPEC_V1_1 §7.
# ---------------------------------------------------------------------------
def _cmd_decide(decision, rest):
    p = argparse.ArgumentParser(prog=f"forge {decision}")
    p.add_argument("id")
    p.add_argument("--key", required=True)
    p.add_argument("--lambda", dest="lam", type=float, required=True)
    p.add_argument("--reason", required=(decision == "refuse"), default="approved via forge")
    p.add_argument("--attestation", default=None)
    p.add_argument("--attester", default=None)
    try:
        args = p.parse_args(rest)
    except SystemExit:
        return 2
    if bool(args.attestation) != bool(args.attester):
        print("--attestation and --attester go together", file=sys.stderr)
        return 2
    hal, env = _layer("hal"), _layer("envelope")
    try:
        if not hal.can_validate(args.lam):
            print(f"quarantine: lambda={args.lam} below threshold 0.60", file=sys.stderr)
            return 2
    except (TypeError, ValueError) as e:
        print(f"invalid lambda: {e}", file=sys.stderr)
        return 2

    pending = _pending()
    if args.id.isdigit():
        match = [x for x in pending if x["seq"] == int(args.id)]
    else:
        match = [x for x in pending if len(args.id) >= 6 and x["hash"].startswith(args.id)]
    if len(match) != 1:
        print(f"no pending proposal: {args.id}", file=sys.stderr)
        return 1
    proposal = match[0]

    try:
        attestation = attester = None
        if args.attestation:
            with open(args.attestation, encoding="utf-8") as f:
                attestation = json.load(f)
            attester = env.did_key_decode(args.attester)
        seal_key = _load_key(args.key)
        same = os.path.abspath(args.key) == os.path.abspath(_key_path())
        ledger_key = seal_key if same else _load_key(_key_path())
        _check_ledger(ledger_key)
        try:
            seal = hal.create_seal(decision, proposal["action_type"], proposal["subject_id"],
                                   args.reason, args.lam, time.time(),
                                   attestation=attestation, attester_public_key=attester)
            signed = hal.sign_seal(seal, seal_key)
        except ValueError as e:
            print(f"{decision} refused: {e}", file=sys.stderr)
            return 2
        if not hal.verify_seal(signed, seal_key.public_key(), attester):
            raise RuntimeError("seal does not verify")
        _append(signed, ledger_key)
        sub = _layer("substrate")
        if os.path.exists(_db_path()) and sub.read_claim(_db_path(), proposal["subject_id"]) is not None:
            sub.link_attestation(_db_path(), proposal["subject_id"], signed, ledger_key)
    except KeyboardInterrupt:
        raise
    except Exception as e:
        print(f"{decision} failed: {e}", file=sys.stderr)
        return 1
    print(env.sha256_hex(env.canonical_bytes(signed)))
    return 0


# ---------------------------------------------------------------------------
# 29. _cmd_web
#     SPEC_V1_1 §10.
# ---------------------------------------------------------------------------
def _cmd_web(rest):
    print("The Cockpit runs no web server. Read-only views:\n"
          "  SCP Substrate (3D field): python ../scp-substrate/serve.py   http://127.0.0.1:8085/\n"
          "  The Legacy (dashboard):   python ../the-legacy/legacy_v3.py  http://127.0.0.1:8080/")
    return 0


# ---------------------------------------------------------------------------
# 30. _cmd_migrate_scp
#     SPEC.md §5 on the v1.1 write path. Unparseable or unsplittable files
#     are skipped and counted, not fatal.
# ---------------------------------------------------------------------------
def _cmd_migrate_scp(rest):
    if len(rest) != 1:
        print("usage: forge migrate-scp <dir>", file=sys.stderr)
        return 2
    root = rest[0]
    if not os.path.isdir(root):
        print(f"not a directory: {root}", file=sys.stderr)
        return 1
    files = sorted(os.path.join(d, fn) for d, _, fns in os.walk(root) for fn in fns if fn.endswith(".scp.json"))
    if not files:
        print(f"no .scp.json files found in {root}", file=sys.stderr)
        return 1
    try:
        key = _load_key(_key_path())
        migrated = 0
        for path in files:
            try:
                with open(path, encoding="utf-8") as f:
                    payload = json.load(f)
                claim = _parse_claim(str(payload)[:200])
                if not claim["subject"] or not claim["object"]:
                    raise ValueError("no subject/object")
                capsule = _capsule(claim, "CONTEXT", json.dumps(payload, sort_keys=True)[:1000],
                                   migrated_from=path)
            except (OSError, ValueError, TypeError):
                print(f"skipped: {path}", file=sys.stderr)
                continue
            _commit(capsule, key)
            migrated += 1
    except KeyboardInterrupt:
        raise
    except Exception as e:
        print(f"migrate-scp failed: {e}", file=sys.stderr)
        return 1
    print(f"migrated {migrated}/{len(files)}")
    return 0


# ---------------------------------------------------------------------------
# 16. _usage
# ---------------------------------------------------------------------------
def _usage():
    print(
        "usage: forge <command> [args]   (Cockpit v1.1)\n"
        "  remember <text> --face <FACE>\n"
        "  cube <id> | cubes [--face <FACE>] | trust <claim_id>\n"
        "  verify-ledger | ledger | health | status\n"
        "  dream | think | reason <q> | ask <q>\n"
        "  propose <claim_id> --action <type> [--note <text>] | pending\n"
        "  approve <seq|hash> --key <pem> --lambda <f> [--reason <r>]\n"
        "  refuse  <seq|hash> --key <pem> --lambda <f> --reason <r>\n"
        "          [--attestation <file> --attester <did:key>]\n"
        "  sign <file> | verify <file> | record <capsule.json> --key <pem>\n"
        "  web | migrate-scp <dir>",
        file=sys.stderr,
    )


# ---------------------------------------------------------------------------
# 1. main
# ---------------------------------------------------------------------------
def main(argv):
    handlers = {
        "remember": _cmd_remember,
        "cube": _cmd_cube,
        "cubes": _cmd_cubes,
        "trust": _cmd_trust,
        "verify-ledger": _cmd_verify_ledger,
        "ledger": _v1._cmd_ledger,
        "health": _cmd_health,
        "status": _cmd_status,
        "dream": lambda rest: _cmd_generated("dream", "UNKNOWN", rest),
        "think": lambda rest: _cmd_generated("think", "OPINION", rest),
        "reason": lambda rest: _cmd_generated("reason", "CONTEXT", rest),
        "ask": _v1._cmd_ask,
        "propose": _cmd_propose,
        "pending": _cmd_pending,
        "approve": lambda rest: _cmd_decide("approve", rest),
        "refuse": lambda rest: _cmd_decide("refuse", rest),
        "sign": _with_current(_v1._cmd_sign),
        "verify": _with_current(_v1._cmd_verify),
        "record": _with_current(_v1._cmd_record),
        "web": _cmd_web,
        "migrate-scp": _cmd_migrate_scp,
    }
    try:
        if not argv:
            _usage()
            return 2
        handler = handlers.get(argv[0])
        if handler is None:
            print(f"unknown command: {argv[0]}", file=sys.stderr)
            _usage()
            return 2
        return handler(argv[1:])
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
