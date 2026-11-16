"""
forge_cli_v1_7.py — The Cockpit v1.7: entity and subject drafts in the inbox

Function:
    The entry point from v1.7 (SPEC_V1_7.md). The Legacy writes drafts
    and never signs; v1.7 lets those drafts be an entity, a subject
    (belonging to an entity) or a claim, and `forge inbox commit` signs
    them in that order: P9 v4 records, the membership that links a
    subject to its entity, and the claim, each in the ledger too. Claim
    drafts are v1.2's, byte for byte. Every other command is v1.6's.
    forge_cli.py and forge_cli_v1_1 to v1_6 are not edited.

Public API:
    1. main(argv) -> int
    2. write_draft_any(fields) -> draft_id
    3. validate_any(d)
    4. describe(d) -> dict
    (re-exported: register, _substrate_v4 from v1.4)

Internal helpers:
    5. _kind_of        — "entity" | "subject" | "claim"
    6. _check_name     — a non-empty name of at most 200 characters
    7. _commit_entity  — one entity draft
    8. _commit_subject — one subject draft and its membership
    9. _commit_claim   — one claim draft (v1.3's commit)
    10. _cmd_inbox     — list every kind; commit in order; drop is v1.2's

Tier:     Tier 1 — Consumer (The Cockpit)
Depends:  forge_cli_v1_6.py (1.6.0), forge_cli_v1_4.py (register), P9 substrate_v4 (4.0.0)
Spec:     SPEC_V1_7.md 1.7.0 (over SPEC_V1_6.md 1.6.0)
Version:  1.7.0
Licence:  MSL-1.0
Author:   James Gilbert (Giblets Forge)
"""

import hashlib
import json
import os
import sqlite3
import sys
import time
from contextlib import closing

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import forge_cli as _v1  # noqa: E402
import forge_cli_v1_1 as _v11  # noqa: E402
import forge_cli_v1_2 as _v12  # noqa: E402
import forge_cli_v1_3 as _v13  # noqa: E402
import forge_cli_v1_4 as _v14  # noqa: E402
import forge_cli_v1_6 as _v16  # noqa: E402

register, _substrate_v4 = _v14.register, _v14._substrate_v4
_NOUN_KEYS = {"entity": {"draft", "kind", "name", "created_at"},
              "subject": {"draft", "kind", "name", "entity", "created_at"}}
_ORDER = {"entity": 0, "subject": 1, "claim": 2}


# ---------------------------------------------------------------------------
# 5. _kind_of
# ---------------------------------------------------------------------------
def _kind_of(d):
    return d.get("kind", "claim") if isinstance(d, dict) else "claim"


# ---------------------------------------------------------------------------
# 6. _check_name
# ---------------------------------------------------------------------------
def _check_name(label, v):
    if not isinstance(v, str) or not v.strip() or len(v) > 200:
        raise ValueError(f"{label} must be a non-empty str of at most 200 characters")


# ---------------------------------------------------------------------------
# 3. validate_any
#    SPEC_V1_7 §1: no kind is a v1.2 claim draft; entity and subject have
#    exactly their keys.
# ---------------------------------------------------------------------------
def validate_any(d):
    if not isinstance(d, dict):
        raise ValueError("draft must be a JSON object")
    if "kind" not in d:
        return _v12.validate_draft(d)
    kind = d["kind"]
    if kind not in _NOUN_KEYS:
        raise ValueError(f"kind must be one of {sorted(_NOUN_KEYS)} (a claim draft has no kind)")
    if set(d) != _NOUN_KEYS[kind]:
        raise ValueError(f"a {kind} draft must have exactly the keys {sorted(_NOUN_KEYS[kind])}")
    if d["draft"] != _v12.DRAFT_VERSION:
        raise ValueError(f"draft version must be {_v12.DRAFT_VERSION}")
    _check_name("name", d["name"])
    if kind == "subject":
        _check_name("entity", d["entity"])
    ts = d["created_at"]
    if isinstance(ts, bool) or not isinstance(ts, (int, float)) or ts != ts or ts in (float("inf"), float("-inf")):
        raise ValueError("created_at must be a finite number")


# ---------------------------------------------------------------------------
# 2. write_draft_any
#    SPEC_V1_7 §1: claims through v1.2's write_draft (unchanged files);
#    entity and subject drafts written the same way.
# ---------------------------------------------------------------------------
def write_draft_any(fields):
    if not isinstance(fields, dict):
        raise ValueError("draft must be a JSON object")
    if "kind" not in fields:
        return _v12.write_draft(fields)
    d = dict(fields, draft=_v12.DRAFT_VERSION, created_at=time.time())
    validate_any(d)
    data = json.dumps(d, sort_keys=True, ensure_ascii=False).encode("utf-8")
    draft_id = f"{int(d['created_at'] * 1000)}-{hashlib.sha256(data).hexdigest()[:8]}"
    path = os.path.join(_v12._inbox_dir(), draft_id + ".json")
    with open(path + ".tmp", "wb") as f:
        f.write(data)
    os.replace(path + ".tmp", path)
    return draft_id


# ---------------------------------------------------------------------------
# 4. describe
# ---------------------------------------------------------------------------
def describe(d):
    kind = _kind_of(d)
    keys = {"entity": ("name",), "subject": ("name", "entity"),
            "claim": ("subject", "object", "face", "text")}[kind]
    return {"kind": kind, **{k: d[k] for k in keys}}


# ---------------------------------------------------------------------------
# 7. _commit_entity
# ---------------------------------------------------------------------------
def _commit_entity(d, key):
    entity_id, new = register("entity", d["name"].strip(), key)
    return {"entity_id": entity_id, **({} if new else {"note": "already registered"})}


# ---------------------------------------------------------------------------
# 8. _commit_subject
#    SPEC_V1_7 §3: the entity must exist; register, link, ledger the link.
# ---------------------------------------------------------------------------
def _commit_subject(d, key):
    p9, db = _substrate_v4(), _v1._db_path()
    p9.init_db(db)
    owner = p9.find(db, d["entity"].strip())
    if owner is None or owner["type"] != "entity":
        raise ValueError(f"entity not registered: {d['entity'].strip()!r} (draft or register it first)")
    subject_id, new = register("subject", d["name"].strip(), key)
    existing = [m["id"] for m in p9.members(db, subject_id)]
    membership_id = p9.add_member(db, subject_id, owner["id"], key)
    if owner["id"] not in existing:
        with closing(sqlite3.connect(db)) as conn:
            text = conn.execute("SELECT capsule FROM memberships WHERE membership_id=?",
                                (membership_id,)).fetchone()[0]
        _v11._append(json.loads(text), key)
    note = {"subject_id": subject_id, "entity_id": owner["id"], "membership_id": membership_id}
    return note if new else dict(note, note="subject already registered")


# ---------------------------------------------------------------------------
# 9. _commit_claim
#    v1.3's inbox commit for one draft: P13 v3 gate for UNKNOWN, v1.2's
#    capsule, v1.1's commit. ValueError refuses; anything else stops.
# ---------------------------------------------------------------------------
def _commit_claim(d, key):
    claim = {"subject": d["subject"].strip(), "object": d["object"].strip()}
    if d["face"] == "UNKNOWN":
        try:
            _v13.gate(claim)
        except ValueError as e:
            raise ValueError(f"keystone gate: {e}") from None
    capsule = _v12._asserted_capsule(claim, d["face"], d["text"])
    claim_id, entry = _v11._commit(capsule, key)
    return {"claim_id": claim_id, **({} if entry else {"note": "already remembered"})}


_COMMIT = {"entity": _commit_entity, "subject": _commit_subject, "claim": _commit_claim}


# ---------------------------------------------------------------------------
# 10. _cmd_inbox
# ---------------------------------------------------------------------------
def _cmd_inbox(rest):
    action = rest[0] if rest else "list"
    if action == "drop":
        return _v12._cmd_inbox(rest)
    drafts = []
    for draft_id, path in _v12._pending_drafts():
        try:
            with open(path, encoding="utf-8") as f:
                d = json.load(f)
            validate_any(d)
            drafts.append((draft_id, path, d, None))
        except (OSError, ValueError) as e:
            drafts.append((draft_id, path, None, str(e)))
    if action == "list" and len(rest) <= 1:
        if not drafts:
            print("inbox empty")
        for draft_id, _, d, bad in drafts:
            if bad:
                print(f"{draft_id}  invalid: {bad}")
                continue
            x = describe(d)
            line = {"entity": lambda: f"entity {x['name']}",
                    "subject": lambda: f"subject {x['name']} -> {x['entity']}",
                    "claim": lambda: f"claim {x['face']} {x['subject']} / {x['object']}: {x['text']}"}[x["kind"]]()
            print(f"{draft_id}  {line}")
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
    order = sorted(range(len(drafts)), key=lambda i: (_ORDER[_kind_of(drafts[i][2])] if drafts[i][2] else 3, i))
    for i in order:
        draft_id, path, d, bad = drafts[i]
        if bad:
            _v12._file_away(draft_id, path, "refused", {"reason": bad})
            refused += 1
            continue
        try:
            note = _COMMIT[_kind_of(d)](d, key)
        except ValueError as e:
            _v12._file_away(draft_id, path, "refused", {"reason": str(e)})
            refused += 1
            continue
        except Exception as e:
            print(f"inbox commit stopped at {draft_id}: {e}", file=sys.stderr)
            return 1
        _v12._file_away(draft_id, path, "done", note)
        committed += 1
    print(f"committed {committed}, refused {refused}")
    return 0


# ---------------------------------------------------------------------------
# 1. main
# ---------------------------------------------------------------------------
def main(argv):
    if argv and argv[0] == "inbox":
        return _cmd_inbox(argv[1:])
    return _v16.main(argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
