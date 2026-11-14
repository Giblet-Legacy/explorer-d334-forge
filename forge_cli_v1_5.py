"""
forge_cli_v1_5.py — The Cockpit v1.5: answering a question

Function:
    The entry point from v1.5 (SPEC_V1_5.md). A question is a claim's
    UNKNOWN face, and nothing could close one, so the Weaver's briefing
    kept every question ever asked. `forge answer` supersedes the claim
    (P9) with a signed copy whose UNKNOWN face is cleared and which
    carries the question and its answer, then appends that copy to the
    ledger. Every other command is v1.4's. forge_cli.py and
    forge_cli_v1_1 to v1_4 are not edited.

Public API:
    1. main(argv) -> int
    2. find_claim(ref) -> claim_id
    3. answer(claim_id, text, key) -> (new_claim_id, ledger entry)
    (re-exported from v1.4: register, commit_cube, gate, attest,
     engine_command, run_lllm, lllm_gen, lllm_provenance, status,
     write_draft, validate_draft)

Internal helpers:
    4. _all_claim_ids — every claim id in forge.db, active or not
    5. _cmd_answer    — forge answer <ref> <answer…>

Tier:     Tier 1 — Consumer (The Cockpit)
Depends:  forge_cli_v1_4.py (1.4.0); P9 substrate_v3 via v1.1's layer map
Spec:     SPEC_V1_5.md 1.5.0 (over SPEC_V1_4.md 1.4.0)
Version:  1.5.0-dev
Licence:  MSL-1.0
Author:   James Gilbert (Giblets Forge)
"""

import argparse
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import forge_cli as _v1  # noqa: E402
import forge_cli_v1_1 as _v11  # noqa: E402
import forge_cli_v1_4 as _v14  # noqa: E402

_layer = _v11._layer
register, commit_cube, gate, attest = _v14.register, _v14.commit_cube, _v14.gate, _v14.attest
engine_command, run_lllm, lllm_gen, lllm_provenance = (_v14.engine_command, _v14.run_lllm,
                                                       _v14.lllm_gen, _v14.lllm_provenance)
status, write_draft, validate_draft = _v14.status, _v14.write_draft, _v14.validate_draft

_REF = re.compile(r"[0-9a-f]{8,64}")


# ---------------------------------------------------------------------------
# 4. _all_claim_ids
# ---------------------------------------------------------------------------
def _all_claim_ids():
    db = _v1._db_path()
    if not os.path.exists(db):
        return []
    return [r["claim_id"] for r in _layer("substrate").list_claims(db, active_only=False)]


# ---------------------------------------------------------------------------
# 2. find_claim
#    SPEC_V1_5 §1: a full id or a unique prefix of 8+ hex characters.
# ---------------------------------------------------------------------------
def find_claim(ref):
    ref = ref.strip().lower() if isinstance(ref, str) else ""
    if not _REF.fullmatch(ref):
        raise ValueError("a claim reference is at least 8 hexadecimal characters of its id")
    found = [cid for cid in _all_claim_ids() if cid.startswith(ref)]
    if not found:
        raise KeyError(f"claim not found: {ref}")
    if len(found) > 1:
        raise ValueError(f"{ref} matches {len(found)} claims; give more of the id")
    return found[0]


# ---------------------------------------------------------------------------
# 3. answer
#    SPEC_V1_5 §2: every check before any write; then P9 supersede and
#    the ledger.
# ---------------------------------------------------------------------------
def answer(claim_id, text, key):
    if not isinstance(text, str) or not text.strip():
        raise ValueError("the answer must be a non-empty string")
    sub, db = _layer("substrate"), _v1._db_path()
    row = sub.read_claim(db, claim_id, verify=True) if os.path.exists(db) else None
    if row is None:
        raise KeyError(f"claim not found: {claim_id}")
    if not row["verified"]:
        raise ValueError(f"claim {claim_id[:12]} does not verify; not answering it")
    if not row["is_active"]:
        raise ValueError(f"claim {claim_id[:12]} is already superseded (by {row['superseded_by']})")
    old = row["capsule"] or {}
    question = old.get("UNKNOWN")
    if not isinstance(question, str) or not question.strip():
        raise ValueError(f"claim {claim_id[:12]} asks no question (its UNKNOWN face is empty)")
    _v11._check_ledger(key)
    capsule = {k: v for k, v in old.items() if k != "signature"}
    capsule["UNKNOWN"] = None
    capsule["answers"] = {"claim_id": claim_id, "question": question, "answer": text.strip()}
    new_id = sub.supersede_claim(db, claim_id, capsule, key)
    return new_id, _v11._append(sub.get_claim(db, new_id), key)


# ---------------------------------------------------------------------------
# 5. _cmd_answer
# ---------------------------------------------------------------------------
def _cmd_answer(rest):
    p = argparse.ArgumentParser(prog="forge answer")
    p.add_argument("ref")
    p.add_argument("answer", nargs="*")
    try:
        args = p.parse_args(rest)
    except SystemExit:
        return 2
    try:
        claim_id = find_claim(args.ref)
        question = (_layer("substrate").read_claim(_v1._db_path(), claim_id)["capsule"] or {}).get("UNKNOWN")
        text = " ".join(args.answer)
        if not text.strip():
            raise ValueError("give the answer after the claim id")
        key = _v11._load_key(_v1._key_path())
        new_id, _ = answer(claim_id, text, key)
    except KeyboardInterrupt:
        raise
    except (ValueError, KeyError) as e:
        print(str(e).strip("'\""), file=sys.stderr)
        return 2
    except Exception as e:
        print(f"answer failed: {e}", file=sys.stderr)
        return 1
    print(f"question: {question}")
    print(f"answer:   {text.strip()}")
    print(f"answered {claim_id[:12]} -> {new_id}")
    return 0


# ---------------------------------------------------------------------------
# 1. main
# ---------------------------------------------------------------------------
def main(argv):
    if argv and argv[0] == "answer":
        try:
            return _cmd_answer(argv[1:])
        except KeyboardInterrupt:
            print("interrupted", file=sys.stderr)
            return 130
    return _v14.main(argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
