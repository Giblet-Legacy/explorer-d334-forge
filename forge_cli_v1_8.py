"""
forge_cli_v1_8.py — The Cockpit v1.8: drafts in the order written

Function:
    The entry point from v1.8 (SPEC_V1_8.md). v1.2 sorted the inbox by
    draft id, `<ms>-<hash>`, so two drafts written in the same
    millisecond came out in hash order, and `inbox commit` could sign
    them in that order (found by the VPS check, 2026-11-18). v1.8 sorts
    by each draft's own `created_at`, then id, and writes `created_at`
    so it always increases. `inbox` list, commit and drop are v1.7's
    behaviour in that order; every other command is v1.7's.
    forge_cli.py and forge_cli_v1_1 to v1_7 are not edited.

Public API:
    1. main(argv) -> int
    2. pending_drafts() -> [(id, path)] in the order written
    3. write_draft_any(fields) -> draft_id
    4. write_draft(fields) -> draft_id (a claim draft)
    (re-exported from v1.7: validate_any, describe)

Internal helpers:
    5. _created_at — a draft file's created_at, else its id's ms / 1000
    6. _cmd_inbox  — v1.7's list / commit / drop over pending_drafts

Tier:     Tier 1 — Consumer (The Cockpit)
Depends:  forge_cli_v1_7.py (1.7.0), forge_cli_v1_2.py (inbox, filing)
Spec:     SPEC_V1_8.md 1.8.0 (over SPEC_V1_7.md 1.7.0)
Version:  1.8.0
Licence:  MSL-1.0
Author:   James Gilbert (Giblets Forge)
"""

import hashlib
import json
import math
import os
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import forge_cli as _v1  # noqa: E402
import forge_cli_v1_1 as _v11  # noqa: E402
import forge_cli_v1_2 as _v12  # noqa: E402
import forge_cli_v1_7 as _v17  # noqa: E402

validate_any, describe = _v17.validate_any, _v17.describe
_STEP = 0.000001


# ---------------------------------------------------------------------------
# 5. _created_at
# ---------------------------------------------------------------------------
def _created_at(draft_id, path):
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        t = d.get("created_at") if isinstance(d, dict) else None
        if isinstance(t, (int, float)) and not isinstance(t, bool) and math.isfinite(t):
            return float(t)
    except (OSError, ValueError):
        pass
    head = draft_id.split("-")[0]
    return int(head) / 1000 if head.isdigit() else 0.0


# ---------------------------------------------------------------------------
# 2. pending_drafts
#    SPEC_V1_8 §1: by created_at, then id.
# ---------------------------------------------------------------------------
def pending_drafts():
    d = os.path.join(_v1._forge_home(), "inbox")
    if not os.path.isdir(d):
        return []
    found = [(n[:-5], os.path.join(d, n)) for n in os.listdir(d) if n.endswith(".json")]
    return sorted(found, key=lambda p: (_created_at(*p), p[0]))


# ---------------------------------------------------------------------------
# 3. write_draft_any
#    SPEC_V1_8 §2: v1.7's draft, created_at after every pending draft.
# ---------------------------------------------------------------------------
def write_draft_any(fields):
    if not isinstance(fields, dict):
        raise ValueError("draft must be a JSON object")
    latest = max((_created_at(*p) for p in pending_drafts()), default=None)
    now = time.time()
    if latest is not None and now <= latest:
        now = latest + _STEP
    d = dict(fields, draft=_v12.DRAFT_VERSION, created_at=now)
    if "kind" in fields:
        validate_any(d)
    else:
        _v12.validate_draft(d)
    data = json.dumps(d, sort_keys=True, ensure_ascii=False).encode("utf-8")
    draft_id = f"{int(d['created_at'] * 1000)}-{hashlib.sha256(data).hexdigest()[:8]}"
    path = os.path.join(_v12._inbox_dir(), draft_id + ".json")
    with open(path + ".tmp", "wb") as f:
        f.write(data)
    os.replace(path + ".tmp", path)
    return draft_id


# ---------------------------------------------------------------------------
# 4. write_draft
# ---------------------------------------------------------------------------
def write_draft(fields):
    if isinstance(fields, dict) and "kind" in fields:
        raise ValueError("write_draft writes claim drafts only; use write_draft_any")
    return write_draft_any(fields)


# ---------------------------------------------------------------------------
# 6. _cmd_inbox
#    SPEC_V1_8 §3: v1.7's inbox (forge_cli_v1_7 §10) over pending_drafts.
# ---------------------------------------------------------------------------
def _cmd_inbox(rest):
    action = rest[0] if rest else "list"
    if action == "drop":
        return _v12._cmd_inbox(rest)
    drafts = []
    for draft_id, path in pending_drafts():
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
    order = sorted(range(len(drafts)),
                   key=lambda i: (_v17._ORDER[_v17._kind_of(drafts[i][2])] if drafts[i][2] else 3, i))
    for i in order:
        draft_id, path, d, bad = drafts[i]
        if bad:
            _v12._file_away(draft_id, path, "refused", {"reason": bad})
            refused += 1
            continue
        try:
            note = _v17._COMMIT[_v17._kind_of(d)](d, key)
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
    return _v17.main(argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
