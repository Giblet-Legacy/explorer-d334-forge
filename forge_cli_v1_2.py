"""
forge_cli_v1_2.py — The Cockpit CLI v1.2 (LLLM provenance, inbox, status)

Function:
    The layer above Cockpit v1.1.0 (forge_cli_v1_1.py), and the entry
    point to run from v1.2 on. Adds, per SPEC_V1_2.md:
    - LLLM provenance: generated claims name the exact LLLM build
      (build.json hash), a build whose code changed since it was built
      is refused, and each build is anchored in the ledger once;
    - the inbox: drafts written by The Legacy are committed here, with
      the passphrase entered here;
    - status(): a passphrase-free, read-only summary The Legacy shows;
    - polarity for FACT / COUNTER / CONTEXT claims (the Voice needs it),
      and LLLM output stored as OPINION in its own lllm.db.
    Every other command is v1.1's, unchanged.

    forge_cli.py and forge_cli_v1_1.py are frozen and not edited.

Public API:
    1. main(argv) -> int
    2. lllm_provenance() -> dict
    3. validate_draft(d) -> None
    4. write_draft(fields) -> str
    5. status() -> dict
    (re-exported from v1.1: probe_layers)

Internal helpers (numbered below):
    6.  _run_lllm      — run `lllm <args>`, return stdout
    7.  _lllm_gen      — `lllm gen <prompt>` text
    8.  _anchor        — append the lllm.build record once per build
    9.  _cmd_generated — dream / think / reason with provenance
    10. _inbox_dir     — FORGE_HOME/inbox (and done/, refused/)
    11. _pending_drafts — (id, path) oldest first
    12. _file_away     — move a draft to done/ or refused/ with a note
    13. _cmd_inbox     — list | commit | drop <id>
    14. _cmd_status    — status() as JSON
    15. _lllm_db_path  — FORGE_HOME/lllm.db (LLLM output, OPINION)
    16. _polarised     — claim + polarity for asserted faces
    17. _asserted_capsule — v1.1 capsule + polarity
    18. _commit_lllm   — v1.1 commit, into lllm.db
    19. _cmd_remember  — remember with polarity

Tier:     Tier 1 — Consumer (The Cockpit)
Depends:  Cockpit v1.1.0; LLLM CLI and $LLLM_HOME (read-only)
Spec:     SPEC_V1_2.md 1.2.0 (over SPEC_V1_1.md 1.1.0)
Version:  1.2.0
Licence:  MSL-1.0
Author:   James Gilbert (Giblets Forge)
"""

import hashlib
import json
import math
import os
import subprocess
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import forge_cli as _v1  # noqa: E402
import forge_cli_v1_1 as _v11  # noqa: E402

probe_layers = _v11.probe_layers
_layer = _v11._layer

DRAFT_VERSION = "forge.draft/1"
_DRAFT_KEYS = {"draft", "subject", "object", "text", "face", "created_at"}
POLARITY_FACES = ("FACT", "COUNTER", "CONTEXT")   # SPEC_V1_2 §4: asserted faces only
LLLM_FACE = "OPINION"                              # SPEC_V1_2 §5: LLLM output is opinion


# ---------------------------------------------------------------------------
# 15. _lllm_db_path
#     SPEC_V1_2 §5: LLLM's own P9 database, beside forge.db.
# ---------------------------------------------------------------------------
def _lllm_db_path():
    return os.path.join(_v1._forge_home(), "lllm.db")


# ---------------------------------------------------------------------------
# 16. _polarised
#     SPEC_V1_2 §4. Returns (claim, polarity or None). A leading "not "
#     on the object means negate and is removed; `override` wins.
#     ValueError for an override on a face that takes no polarity.
# ---------------------------------------------------------------------------
def _polarised(claim, face, override=None):
    obj = claim["object"]
    negated = obj.lower().startswith("not ")
    if negated:
        obj = obj[4:].strip()
    if face not in POLARITY_FACES:
        if override:
            raise ValueError(f"--polarity applies only to {', '.join(POLARITY_FACES)} claims")
        return claim, None
    if override not in (None, "affirm", "negate"):
        raise ValueError("--polarity must be affirm or negate")
    return dict(claim, object=obj), override or ("negate" if negated else "affirm")


# ---------------------------------------------------------------------------
# 17. _asserted_capsule
#     v1.1's capsule (P13 cube + face + provenance) plus `polarity` for
#     the asserted faces, the field the Voice requires (LLLM SPEC §4).
# ---------------------------------------------------------------------------
def _asserted_capsule(claim, face, text, override=None, **extra):
    claim, polarity = _polarised(claim, face, override)
    capsule = _v11._capsule(claim, face, text, **extra)
    if polarity:
        capsule["polarity"] = polarity
    return capsule


# ---------------------------------------------------------------------------
# 18. _commit_lllm
#     SPEC_V1_2 §5: as v1.1's _commit, into lllm.db instead of forge.db.
#     The ledger and P8 mirror are the same single audit trail.
# ---------------------------------------------------------------------------
def _commit_lllm(capsule, key):
    env, sign, sub = _layer("envelope"), _layer("sign"), _layer("substrate")
    _v11._check_ledger(key)
    signed = sign.sign_capsule(capsule, key)
    claim_id = env.sha256_hex(env.canonical_bytes(signed))
    db = _lllm_db_path()
    sub.init_db(db)
    if sub.read_claim(db, claim_id) is not None:
        return claim_id, None
    if sub.write_claim(db, capsule, key) != claim_id:
        raise RuntimeError("P9 claim id differs from the signed capsule's hash")
    return claim_id, _v11._append(sub.get_claim(db, claim_id), key)


# ---------------------------------------------------------------------------
# 6. _run_lllm
# ---------------------------------------------------------------------------
def _run_lllm(*args):
    ok, reason = _v1._lllm_available()
    if not ok:
        raise RuntimeError(f"LLLM unavailable: {reason}")
    try:
        r = subprocess.run(["lllm", *args], capture_output=True, text=True, timeout=120, check=True)
    except FileNotFoundError:
        raise RuntimeError("LLLM unavailable: `lllm` not on PATH") from None
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"LLLM failed: {(e.stderr or '').strip()[:200]}") from None
    return r.stdout


# ---------------------------------------------------------------------------
# 7. _lllm_gen
# ---------------------------------------------------------------------------
def _lllm_gen(prompt):
    return _run_lllm("gen", prompt)


# ---------------------------------------------------------------------------
# 2. lllm_provenance
#    SPEC_V1_2 §1.2.
# ---------------------------------------------------------------------------
def lllm_provenance():
    text = _run_lllm("info")
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
# 8. _anchor
#    SPEC_V1_2 §1.3 step 3. Caller has already checked the ledger.
# ---------------------------------------------------------------------------
def _anchor(prov, key):
    for entry in _v11._ledger_entries():
        rec = entry.get("record") or {}
        if rec.get("type") == "lllm.build" and rec.get("build_json_sha256") == prov["build_json_sha256"]:
            return False
    record = _layer("sign").sign_capsule({
        "type": "lllm.build", "build_id": prov["build_id"],
        "build_json_sha256": prov["build_json_sha256"], "identity": prov["identity"],
        "signature": None,
    }, key)
    _v11._append(record, key)
    return True


# ---------------------------------------------------------------------------
# 9. _cmd_generated
#    SPEC_V1_2 §1.3.
# ---------------------------------------------------------------------------
def _cmd_generated(kind, face, rest):
    if kind == "reason" and not rest:
        print("usage: forge reason <question>", file=sys.stderr)
        return 2
    prompt = " ".join(rest) if kind == "reason" else kind
    try:
        text = _lllm_gen(prompt)
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
        # SPEC_V1_2 §5: LLLM output is OPINION, in lllm.db, never in forge.db.
        # The Keystone Gate guards UNKNOWN claims, so it does not apply here.
        capsule = _v11._capsule(claim, LLLM_FACE, text[:500], **extra)
        key = _v11._load_key(_v1._key_path())
        _v11._check_ledger(key)
        _anchor(prov, key)
        claim_id, entry = _commit_lllm(capsule, key)
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
# 3. validate_draft
#    SPEC_V1_2 §2.1. Drafts are untrusted input.
# ---------------------------------------------------------------------------
def validate_draft(d):
    if not isinstance(d, dict) or set(d) != _DRAFT_KEYS:
        raise ValueError(f"draft must have exactly the keys {sorted(_DRAFT_KEYS)}")
    if d["draft"] != DRAFT_VERSION:
        raise ValueError(f"draft version must be {DRAFT_VERSION}")
    for name, limit in (("subject", 200), ("object", 200), ("text", 2000)):
        v = d[name]
        if not isinstance(v, str) or not v.strip() or len(v) > limit:
            raise ValueError(f"{name} must be a non-empty str of at most {limit} characters")
    if d["face"] not in _v1._FACES:
        raise ValueError(f"face must be one of {_v1._FACES}")
    ts = d["created_at"]
    if isinstance(ts, bool) or not isinstance(ts, (int, float)) or not math.isfinite(ts):
        raise ValueError("created_at must be a finite number")


# ---------------------------------------------------------------------------
# 10. _inbox_dir
# ---------------------------------------------------------------------------
def _inbox_dir(sub=None):
    path = os.path.join(_v1._forge_home(), "inbox", *([sub] if sub else []))
    os.makedirs(path, exist_ok=True)
    return path


# ---------------------------------------------------------------------------
# 4. write_draft
#    SPEC_V1_2 §2.1. Atomic: temp file, then os.replace.
# ---------------------------------------------------------------------------
def write_draft(fields):
    d = dict(fields, draft=DRAFT_VERSION, created_at=time.time())
    validate_draft(d)
    data = json.dumps(d, sort_keys=True, ensure_ascii=False).encode("utf-8")
    draft_id = f"{int(d['created_at'] * 1000)}-{hashlib.sha256(data).hexdigest()[:8]}"
    path = os.path.join(_inbox_dir(), draft_id + ".json")
    with open(path + ".tmp", "wb") as f:
        f.write(data)
    os.replace(path + ".tmp", path)
    return draft_id


# ---------------------------------------------------------------------------
# 11. _pending_drafts
# ---------------------------------------------------------------------------
def _pending_drafts():
    d = os.path.join(_v1._forge_home(), "inbox")
    if not os.path.isdir(d):
        return []
    names = sorted((n for n in os.listdir(d) if n.endswith(".json")),
                   key=lambda n: (int(n.split("-")[0]) if n.split("-")[0].isdigit() else 0, n))
    return [(n[:-5], os.path.join(d, n)) for n in names]


# ---------------------------------------------------------------------------
# 12. _file_away
# ---------------------------------------------------------------------------
def _file_away(draft_id, path, where, note):
    try:
        with open(path, encoding="utf-8") as f:
            body = json.load(f)
        if not isinstance(body, dict):
            body = {"raw": body}
    except (OSError, ValueError):
        with open(path, "rb") as f:
            body = {"raw": f.read().decode("utf-8", "replace")}
    body.update(note)
    target = os.path.join(_inbox_dir(where), draft_id + ".json")
    with open(target, "w", encoding="utf-8", newline="\n") as f:
        json.dump(body, f, sort_keys=True, ensure_ascii=False, indent=1)
    os.remove(path)


# ---------------------------------------------------------------------------
# 13. _cmd_inbox
#     SPEC_V1_2 §2.2.
# ---------------------------------------------------------------------------
def _cmd_inbox(rest):
    action = rest[0] if rest else "list"
    drafts = _pending_drafts()
    if action == "list":
        shown = []
        for draft_id, path in drafts:
            try:
                with open(path, encoding="utf-8") as f:
                    d = json.load(f)
                validate_draft(d)
                shown.append(dict(d, id=draft_id))
            except (OSError, ValueError) as e:
                shown.append({"id": draft_id, "invalid": str(e)})
        print(json.dumps(shown, indent=2, sort_keys=True, ensure_ascii=False))
        return 0
    if action == "drop" and len(rest) == 2:
        match = [p for i, p in drafts if i == rest[1]]
        if not match:
            print(f"no pending draft: {rest[1]}", file=sys.stderr)
            return 1
        _file_away(rest[1], match[0], "refused", {"reason": "dropped by operator"})
        return 0
    if action != "commit" or len(rest) != 1:
        print("usage: forge inbox [list | commit | drop <id>]", file=sys.stderr)
        return 2
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
            validate_draft(d)
            claim = {"subject": d["subject"].strip(), "object": d["object"].strip()}
            if d["face"] == "UNKNOWN":
                try:
                    _layer("datacube").keystone_gate(claim, _v11._memory())
                except ValueError as e:
                    raise ValueError(f"keystone gate: {e}") from None
            capsule = _asserted_capsule(claim, d["face"], d["text"])
        except (OSError, ValueError) as e:
            _file_away(draft_id, path, "refused", {"reason": str(e)})
            refused += 1
            continue
        try:
            claim_id, entry = _v11._commit(capsule, key)
        except Exception as e:
            print(f"inbox commit stopped at {draft_id}: {e}", file=sys.stderr)
            return 1
        _file_away(draft_id, path, "done", {"claim_id": claim_id,
                                            **({} if entry else {"note": "already remembered"})})
        committed += 1
    print(f"committed {committed}, refused {refused}")
    return 0


# ---------------------------------------------------------------------------
# 5. status
#    SPEC_V1_2 §3. Read-only, no passphrase.
# ---------------------------------------------------------------------------
def status():
    db, lp, sp = _v1._db_path(), _v1._ledger_path(), _v11._store_path()
    claims = {"total": 0, "by_face": {f: 0 for f in _v1._FACES}, "attested": 0, "unverified": 0}
    if os.path.exists(db):
        sub = _layer("substrate")
        for row in sub.list_claims(db, verify=True):
            claims["total"] += 1
            if not row["verified"]:
                claims["unverified"] += 1
            face = _v11._face_of(row["capsule"])
            if face:
                claims["by_face"][face] += 1
            att = sub.latest_attestation(db, row["claim_id"])
            if att and att.get("kind") == "attestation":
                claims["attested"] += 1

    entries = []
    if os.path.exists(lp):
        with open(lp, "rb") as f:
            raw = f.read()
        for line in raw.splitlines():
            try:
                entries.append(json.loads(line))
            except ValueError:
                entries.append({})
    else:
        raw = b""
    signer = entries[0].get("signer") if entries else None
    ledger = {"entries": len(entries), "signer": signer,
              "self_consistent": (_layer("canon-verify").verify_ledger(lp, signer) if signer else None),
              "p8_mirror": (_layer("store").export_jsonl(sp) == raw) if os.path.exists(sp) else None}

    inbox = {"pending": len(_pending_drafts())}
    for where in ("done", "refused"):
        d = os.path.join(_v1._forge_home(), "inbox", where)
        inbox[where] = len([n for n in os.listdir(d) if n.endswith(".json")]) if os.path.isdir(d) else 0

    anchors = [(e.get("record") or {}).get("build_id") for e in entries
               if isinstance(e.get("record"), dict) and e["record"].get("type") == "lllm.build"]
    lllm_db = _lllm_db_path()
    opinions = len(_layer("substrate").list_claims(lllm_db)) if os.path.exists(lllm_db) else 0
    return {"claims": claims, "ledger": ledger, "pending_proposals": len(_v11._pending()) if entries else 0,
            "inbox": inbox, "lllm_anchors": anchors, "lllm_opinions": opinions}


# ---------------------------------------------------------------------------
# 14. _cmd_status
# ---------------------------------------------------------------------------
def _cmd_status(rest):
    print(json.dumps(status(), indent=2, sort_keys=True))
    return 0


# ---------------------------------------------------------------------------
# 19. _cmd_remember
#     v1.1's remember (SPEC_V1_1 §4–§5) with polarity (SPEC_V1_2 §4):
#     `--polarity affirm|negate` overrides "is not" detection; it is a
#     usage error (exit 2) on a face that takes no polarity.
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
    if face not in _v1._FACES:
        print(f"invalid face: {face}. must be one of {_v1._FACES}", file=sys.stderr)
        return 2
    text = " ".join(args.text).strip()
    claim = _v1._parse_claim(text)
    if not claim["subject"] or not claim["object"]:
        print(f"cannot split {text!r} into subject and object; phrase it as '<subject> is <object>'",
              file=sys.stderr)
        return 2
    try:
        capsule = _asserted_capsule(claim, face, text, args.polarity)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2
    try:
        if face == "UNKNOWN":
            try:
                _layer("datacube").keystone_gate(claim, _v11._memory())
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
# 1. main
#    v1.2 commands, else v1.1's main.
# ---------------------------------------------------------------------------
def main(argv):
    handlers = {
        "remember": _cmd_remember,
        "dream": lambda rest: _cmd_generated("dream", "UNKNOWN", rest),
        "think": lambda rest: _cmd_generated("think", "OPINION", rest),
        "reason": lambda rest: _cmd_generated("reason", "CONTEXT", rest),
        "inbox": _cmd_inbox,
        "status": _cmd_status,
    }
    if argv and argv[0] in handlers:
        try:
            return handlers[argv[0]](argv[1:])
        except KeyboardInterrupt:
            print("interrupted", file=sys.stderr)
            return 130
    if not argv:
        print("Cockpit v1.2 adds: inbox [list | commit | drop <id>], status (JSON)", file=sys.stderr)
    return _v11.main(argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
