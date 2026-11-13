"""
forge_cli_v1_3.py — The Cockpit v1.3: P13 v3 gate, multi-face cubes, attestation with a loaded key

Function:
    The entry point from v1.3 (SPEC_V1_3.md). Every Keystone Gate check
    goes through P13 v3, whose rule lets one subject hold many claims
    (a contradiction is the same subject and object with the opposite
    polarity). Adds commit_cube, one cube with several faces, and
    attest, propose plus approve with a key already loaded, so a batch
    can be signed after one passphrase prompt. Every other command is
    v1.2's. forge_cli.py, forge_cli_v1_1.py and forge_cli_v1_2.py are
    not edited, and their `_layer` is not patched.

Public API:
    1. main(argv) -> int
    2. gate(claim) -> None
    3. commit_cube(subject, obj, faces, key) -> (claim_id, entry | None)
    4. attest(claim_id, key, lam, reason, action) -> str
    9.  engine_command() -> list[str]   — how to run the LLLM engine
    10. run_lllm(*args) -> str
    11. lllm_gen(seed) -> str            — a refusal raises
    12. lllm_provenance() -> dict
    (re-exported from v1.2: status, write_draft, validate_draft)

Internal helpers:
    5. _datacube     — P13 datacube_v3 from ../datacube-layer
    6. _memory       — v1.1 memory plus polarity
    7. _cmd_remember — v1.2's, gated by P13 v3
    8. _cmd_inbox    — v1.2's, commit gated by P13 v3
    13. _cmd_generated — v1.2's dream / think / reason, through 10–12

Tier:     Tier 1 — Consumer (The Cockpit)
Depends:  forge_cli_v1_2.py (1.2.0), P13 datacube_v3 (3.0.0), P15 hal_v2, P9 substrate_v3
Spec:     SPEC_V1_3.md 1.3.0 (over SPEC_V1_2.md 1.2.0)
Version:  1.3.0
Licence:  MSL-1.0
Author:   James Gilbert (Giblets Forge)
"""

import hashlib
import importlib
import json
import os
import shutil
import subprocess
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import forge_cli as _v1  # noqa: E402
import forge_cli_v1_1 as _v11  # noqa: E402
import forge_cli_v1_2 as _v12  # noqa: E402

_layer = _v11._layer
# v1.2's public API, re-exported unchanged, so v1.3 can stand in for v1.2.
status = _v12.status
write_draft = _v12.write_draft
validate_draft = _v12.validate_draft
_pending_drafts = _v12._pending_drafts
FACES = tuple(_v1._FACES)
_ASSERTED = ("FACT", "COUNTER", "CONTEXT")
_DC = []


# ---------------------------------------------------------------------------
# 5. _datacube
#    SPEC_V1_3 §2: P13 v3 by its own name; v1.1's layer map is untouched.
# ---------------------------------------------------------------------------
def _datacube():
    if not _DC:
        path = os.path.abspath(os.path.join(_HERE, "..", "datacube-layer"))
        if path not in sys.path:
            sys.path.insert(0, path)
        _DC.append(importlib.import_module("datacube_v3"))
    return _DC[0]


# ---------------------------------------------------------------------------
# 6. _memory
#    v1.1's memory (fails closed on a faceless claim) plus polarity.
# ---------------------------------------------------------------------------
def _memory():
    if not os.path.exists(_v1._db_path()):
        return []
    out = []
    for row in _layer("substrate").list_claims(_v1._db_path()):
        cap = row["capsule"] or {}
        face = _v11._face_of(cap)
        if face is None:
            raise ValueError(f"claim {row['claim_id'][:12]} has no single face; gate fails closed")
        entry = {"subject": cap.get("subject"), "object": cap.get("object"), "face": face}
        if "polarity" in cap:
            entry["polarity"] = cap["polarity"]
        out.append(entry)
    return out


# ---------------------------------------------------------------------------
# 2. gate
#    SPEC_V1_3 §2. ValueError naming the contradicted claim on refusal.
# ---------------------------------------------------------------------------
def gate(claim):
    _datacube().keystone_gate(claim, _memory())


# ---------------------------------------------------------------------------
# 3. commit_cube
#    SPEC_V1_3 §3.
# ---------------------------------------------------------------------------
def commit_cube(subject, obj, faces, key):
    if not isinstance(faces, dict) or not faces:
        raise ValueError("faces must be a non-empty dict of face -> text")
    for face, text in faces.items():
        if face not in FACES:
            raise ValueError(f"unknown face {face!r}; must be one of {FACES}")
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"{face} text must be a non-empty string")
    main_face = next((f for f in _ASSERTED if f in faces), None) or next(f for f in FACES if f in faces)
    claim = {"subject": subject.strip(), "object": obj.strip()}
    capsule = _v12._asserted_capsule(claim, main_face, faces[main_face].strip())
    if "UNKNOWN" in faces:
        checked = {"subject": capsule["subject"], "object": capsule["object"]}
        if "polarity" in capsule:
            checked["polarity"] = capsule["polarity"]
        else:
            checked["object"] = claim["object"]  # polarity read from a leading "not "
        gate(checked)
    dc = _datacube()
    for face in FACES:
        if face in faces and face != main_face:
            dc.set_face(capsule, face, faces[face].strip())
    return _v11._commit(capsule, key)


# ---------------------------------------------------------------------------
# 4. attest
#    SPEC_V1_3 §4: forge propose + forge approve, with a loaded key.
# ---------------------------------------------------------------------------
def attest(claim_id, key, lam, reason="read and approved", action="attest"):
    hal, sign, sub = _layer("hal"), _layer("sign"), _layer("substrate")
    if not hal.can_validate(lam):
        raise ValueError(f"quarantine: lambda={lam} below threshold 0.60")
    db = _v1._db_path()
    if not os.path.exists(db) or sub.read_claim(db, claim_id) is None:
        raise KeyError(f"claim not found: {claim_id}")
    _v11._check_ledger(key)
    _v11._append(sign.sign_capsule({"pending_hal": True, "action_type": action, "subject_id": claim_id,
                                    "note": reason, "proposed_at": time.time(), "signature": None}, key), key)
    seal = hal.sign_seal(hal.create_seal("approve", action, claim_id, reason, lam, time.time()), key)
    if not hal.verify_seal(seal, key.public_key()):
        raise RuntimeError("seal does not verify")
    _v11._append(seal, key)
    sub.link_attestation(db, claim_id, seal, key)
    env = _layer("envelope")
    return env.sha256_hex(env.canonical_bytes(seal))


# ---------------------------------------------------------------------------
# 9. engine_command
#    SPEC_V1_3 §5: LLLM_CLI (run with this Python), else `lllm` on PATH.
#    A bash function named lllm is invisible here, hence LLLM_CLI.
# ---------------------------------------------------------------------------
def engine_command():
    cli_path = os.environ.get("LLLM_CLI")
    if cli_path:
        if not os.path.isfile(cli_path):
            raise RuntimeError(f"LLLM unavailable: LLLM_CLI is not a file: {cli_path}")
        return [sys.executable, cli_path]
    found = shutil.which("lllm")
    if not found:
        raise RuntimeError("LLLM unavailable: set LLLM_CLI to the engine's lllm/cli.py, or put an "
                           "`lllm` executable on PATH (a shell function named lllm is not visible to Python)")
    return [found]


# ---------------------------------------------------------------------------
# 10. run_lllm
# ---------------------------------------------------------------------------
def run_lllm(*args):
    ok, reason = _v1._lllm_available()
    if not ok:
        raise RuntimeError(f"LLLM unavailable: {reason}")
    try:
        r = subprocess.run(engine_command() + list(args), capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=120)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise RuntimeError(f"LLLM unavailable: {e}") from None
    if r.returncode != 0:
        raise RuntimeError(f"LLLM failed: {((r.stderr or '') + (r.stdout or '')).strip()[:200]}")
    return r.stdout


# ---------------------------------------------------------------------------
# 11. lllm_gen
#     SPEC_V1_3 §5: a refusal is an error, never text to store.
# ---------------------------------------------------------------------------
def lllm_gen(seed):
    text = run_lllm("gen", seed)
    if not text.strip() or text.strip().startswith("(nothing"):
        raise RuntimeError(f"LLLM refused: {text.strip()[:120] or 'no output'}")
    return text


# ---------------------------------------------------------------------------
# 12. lllm_provenance
#     v1.2's rule (SPEC_V1_2 §1.2), through run_lllm.
# ---------------------------------------------------------------------------
def lllm_provenance():
    text = run_lllm("info")
    build_id, warnings = None, []
    for line in text.splitlines():
        if line.startswith("build:"):
            build_id = line.split(":", 1)[1].strip()
        elif line.startswith("WARNING"):
            warnings.append(line.split(":", 1)[-1].strip())
    if not build_id:
        raise RuntimeError(f"LLLM reports no current build: {text.strip()[:120]}")
    path = os.path.join(os.environ["LLLM_HOME"], "models", build_id, "build.json")
    try:
        with open(path, "rb") as f:
            raw = f.read()
        build = json.loads(raw)
    except (OSError, ValueError):
        raise RuntimeError(f"LLLM build.json missing or unreadable: {path}") from None
    return {"build_id": build_id, "build_json_sha256": hashlib.sha256(raw).hexdigest(),
            "identity": build.get("identity"), "warnings": warnings}


# ---------------------------------------------------------------------------
# 13. _cmd_generated
#     v1.2's, through lllm_gen and lllm_provenance. LLLM output is
#     OPINION in lllm.db (SPEC_V1_2 §5).
# ---------------------------------------------------------------------------
def _cmd_generated(kind, rest):
    if kind == "reason" and not rest:
        print("usage: forge reason <question>", file=sys.stderr)
        return 2
    prompt = " ".join(rest) if kind == "reason" else kind
    try:
        text = lllm_gen(prompt)
        prov = lllm_provenance()
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 1
    if prov["warnings"]:
        print("LLLM build no longer matches its code: " + "; ".join(prov["warnings"])
              + "; run `lllm build`", file=sys.stderr)
        return 1
    source = prompt if kind == "reason" else text.split("\n")[0]
    claim = _v1._parse_claim(source[:200])
    if not claim["subject"] or not claim["object"]:
        print(f"{kind} parse failed: no subject and object in {source[:60]!r}", file=sys.stderr)
        return 1
    extra = {"build_id": prov["build_id"], "source": "lllm", "generated_by": kind,
             "lllm": {"build_id": prov["build_id"], "build_json_sha256": prov["build_json_sha256"]}}
    if kind == "dream":
        extra["lllm_output_sha256"] = hashlib.sha256(text.encode("utf-8")).hexdigest()
    try:
        capsule = _v11._capsule(claim, _v12.LLLM_FACE, text[:500], **extra)
        key = _v11._load_key(_v1._key_path())
        _v11._check_ledger(key)
        _v12._anchor(prov, key)
        claim_id, entry = _v12._commit_lllm(capsule, key)
    except KeyboardInterrupt:
        raise
    except Exception as e:
        print(f"{kind} failed: {e}", file=sys.stderr)
        return 1
    if entry is None:
        print("already remembered; nothing appended", file=sys.stderr)
    print(f"claim_id={claim_id}")
    print(f"build_id={prov['build_id']}")
    return 0


# ---------------------------------------------------------------------------
# 7. _cmd_remember
#    v1.2's, with the gate on P13 v3.
# ---------------------------------------------------------------------------
def _cmd_remember(rest):
    import argparse
    p = argparse.ArgumentParser(prog="forge remember")
    p.add_argument("text", nargs="+")
    p.add_argument("--face", required=True)
    p.add_argument("--polarity", default=None)
    try:
        args = p.parse_args(rest)
    except SystemExit:
        return 2
    face = args.face.upper()
    if face not in FACES:
        print(f"invalid face: {face}. must be one of {FACES}", file=sys.stderr)
        return 2
    text = " ".join(args.text).strip()
    claim = _v1._parse_claim(text)
    if not claim["subject"] or not claim["object"]:
        print(f"cannot split {text!r} into subject and object; phrase it as '<subject> is <object>'",
              file=sys.stderr)
        return 2
    try:
        capsule = _v12._asserted_capsule(claim, face, text, args.polarity)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2
    try:
        if face == "UNKNOWN":
            try:
                gate(claim)
            except ValueError as e:
                print(f"keystone gate: {e}", file=sys.stderr)
                return 1
        key = _v11._load_key(_v1._key_path())
        claim_id, entry = _v11._commit(capsule, key)
    except KeyboardInterrupt:
        raise
    except Exception as e:
        print(f"remember failed: {e}", file=sys.stderr)
        return 1
    if entry is None:
        print("already remembered; nothing appended", file=sys.stderr)
    print(claim_id)
    return 0


# ---------------------------------------------------------------------------
# 8. _cmd_inbox
#    list and drop are v1.2's; commit is v1.2's with the gate on P13 v3.
# ---------------------------------------------------------------------------
def _cmd_inbox(rest):
    if (rest[0] if rest else "list") != "commit" or len(rest) != 1:
        return _v12._cmd_inbox(rest)
    drafts = _v12._pending_drafts()
    if not drafts:
        print("inbox empty")
        return 0
    try:
        key = _v11._load_key(_v1._key_path())
        _v11._check_ledger(key)
    except KeyboardInterrupt:
        raise
    except Exception as e:
        print(f"inbox commit stopped: {e}", file=sys.stderr)
        return 1
    committed = refused = 0
    for draft_id, path in drafts:
        try:
            with open(path, encoding="utf-8") as f:
                d = json.load(f)
            _v12.validate_draft(d)
            claim = {"subject": d["subject"].strip(), "object": d["object"].strip()}
            if d["face"] == "UNKNOWN":
                try:
                    gate(claim)
                except ValueError as e:
                    raise ValueError(f"keystone gate: {e}") from None
            capsule = _v12._asserted_capsule(claim, d["face"], d["text"])
        except (OSError, ValueError) as e:
            _v12._file_away(draft_id, path, "refused", {"reason": str(e)})
            refused += 1
            continue
        try:
            claim_id, entry = _v11._commit(capsule, key)
        except Exception as e:
            print(f"inbox commit stopped at {draft_id}: {e}", file=sys.stderr)
            return 1
        _v12._file_away(draft_id, path, "done", {"claim_id": claim_id,
                                                 **({} if entry else {"note": "already remembered"})})
        committed += 1
    print(f"committed {committed}, refused {refused}")
    return 0


# ---------------------------------------------------------------------------
# 1. main
#    v1.3 commands, else v1.2's main.
# ---------------------------------------------------------------------------
def main(argv):
    handlers = {"remember": _cmd_remember, "inbox": _cmd_inbox,
                "dream": lambda rest: _cmd_generated("dream", rest),
                "think": lambda rest: _cmd_generated("think", rest),
                "reason": lambda rest: _cmd_generated("reason", rest)}
    if argv and argv[0] in handlers:
        try:
            return handlers[argv[0]](argv[1:])
        except KeyboardInterrupt:
            print("interrupted", file=sys.stderr)
            return 130
    return _v12.main(argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
