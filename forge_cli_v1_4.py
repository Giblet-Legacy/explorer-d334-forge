"""
forge_cli_v1_4.py — The Cockpit v1.4: entities, subjects and claims with a predicate

Function:
    The entry point from v1.4 (SPEC_V1_4.md). Registers the nouns P9 v4
    stores, entities (James is one) and subjects (each repo is one),
    and appends each new signed record to the ledger too. Commits cubes
    with an optional predicate ("depends on"). `forge entity add`,
    `forge subject add` and `forge subjects` are new; every other
    command is v1.3's. forge_cli.py and forge_cli_v1_1 to v1_3 are not
    edited.

Public API:
    1. main(argv) -> int
    2. register(kind_of, name, key, kind=None) -> (id, new)
    3. commit_cube(subject, obj, faces, key, predicate=None) -> (claim_id, entry | None)
    (re-exported from v1.3: gate, attest, engine_command, run_lllm,
     lllm_gen, lllm_provenance, status, write_draft, validate_draft)

Internal helpers:
    4. _substrate_v4 — P9 substrate_v4 from ../substrate-layer
    5. _cmd_add      — entity add / subject add
    6. _cmd_subjects — the registered and unregistered names, as JSON

Tier:     Tier 1 — Consumer (The Cockpit)
Depends:  forge_cli_v1_3.py (1.3.0), P9 substrate_v4 (4.0.0)
Spec:     SPEC_V1_4.md 1.4.0 (over SPEC_V1_3.md 1.3.0)
Version:  1.4.0
Licence:  MSL-1.0
Author:   James Gilbert (Giblets Forge)
"""

import argparse
import importlib
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import forge_cli as _v1  # noqa: E402
import forge_cli_v1_1 as _v11  # noqa: E402
import forge_cli_v1_2 as _v12  # noqa: E402
import forge_cli_v1_3 as _v13  # noqa: E402

_layer = _v11._layer
gate, attest = _v13.gate, _v13.attest
engine_command, run_lllm, lllm_gen, lllm_provenance = (_v13.engine_command, _v13.run_lllm,
                                                       _v13.lllm_gen, _v13.lllm_provenance)
status, write_draft, validate_draft, _pending_drafts = (_v13.status, _v13.write_draft,
                                                        _v13.validate_draft, _v13._pending_drafts)
_P9 = []


# ---------------------------------------------------------------------------
# 4. _substrate_v4
#    P9 v4 by its own name; v1.1's layer map (substrate_v3) is untouched.
# ---------------------------------------------------------------------------
def _substrate_v4():
    if not _P9:
        path = os.path.abspath(os.path.join(_HERE, "..", "substrate-layer"))
        if path not in sys.path:
            sys.path.insert(0, path)
        _P9.append(importlib.import_module("substrate_v4"))
    return _P9[0]


# ---------------------------------------------------------------------------
# 2. register
#    SPEC_V1_4 §1: P9 v4 record, and the same signed record in the ledger.
# ---------------------------------------------------------------------------
def register(kind_of, name, key, kind=None):
    if kind_of not in ("entity", "subject"):
        raise ValueError("kind_of must be 'entity' or 'subject'")
    p9, db = _substrate_v4(), _v1._db_path()
    p9.init_db(db)
    before = p9.find(db, name) if isinstance(name, str) and name.strip() else None
    _v11._check_ledger(key)
    add = p9.add_entity if kind_of == "entity" else p9.add_subject
    thing_id = add(db, name, key, kind=kind)
    if before is not None and before["id"] == thing_id:
        return thing_id, False
    record = next(r for r in (p9.list_entities(db) if kind_of == "entity" else p9.list_subjects(db))
                  if r["id"] == thing_id)["capsule"]
    _v11._append(record, key)
    return thing_id, True


# ---------------------------------------------------------------------------
# 3. commit_cube
#    SPEC_V1_4 §2: v1.3's, with an optional predicate on the capsule.
# ---------------------------------------------------------------------------
def commit_cube(subject, obj, faces, key, predicate=None):
    if predicate is None:
        return _v13.commit_cube(subject, obj, faces, key)
    if not isinstance(predicate, str) or not predicate.strip():
        raise ValueError("predicate must be a non-empty string")
    if not isinstance(faces, dict) or not faces:
        raise ValueError("faces must be a non-empty dict of face -> text")
    for face, text in faces.items():
        if face not in _v13.FACES:
            raise ValueError(f"unknown face {face!r}; must be one of {_v13.FACES}")
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"{face} text must be a non-empty string")
    main_face = next((f for f in _v13._ASSERTED if f in faces), None) or next(f for f in _v13.FACES if f in faces)
    claim = {"subject": subject.strip(), "object": obj.strip()}
    capsule = _v12._asserted_capsule(claim, main_face, faces[main_face].strip())
    if "UNKNOWN" in faces:
        checked = {"subject": capsule["subject"], "object": capsule["object"]}
        if "polarity" in capsule:
            checked["polarity"] = capsule["polarity"]
        else:
            checked["object"] = claim["object"]
        gate(checked)
    dc = _v13._datacube()
    for face in _v13.FACES:
        if face in faces and face != main_face:
            dc.set_face(capsule, face, faces[face].strip())
    capsule["predicate"] = predicate.strip()
    return _v11._commit(capsule, key)


# ---------------------------------------------------------------------------
# 5. _cmd_add
# ---------------------------------------------------------------------------
def _cmd_add(kind_of, rest):
    p = argparse.ArgumentParser(prog=f"forge {kind_of} add")
    p.add_argument("name", nargs="+")
    p.add_argument("--kind", default=None)
    try:
        args = p.parse_args(rest)
    except SystemExit:
        return 2
    name = " ".join(args.name)
    try:
        key = _v11._load_key(_v1._key_path())
        thing_id, new = register(kind_of, name, key, kind=args.kind)
    except KeyboardInterrupt:
        raise
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2
    except Exception as e:
        print(f"{kind_of} add failed: {e}", file=sys.stderr)
        return 1
    print(f"{thing_id} {'registered' if new else 'already registered'}")
    return 0


# ---------------------------------------------------------------------------
# 6. _cmd_subjects
#    Read-only; a database without P9 v4 tables lists none registered.
# ---------------------------------------------------------------------------
def _cmd_subjects(rest):
    p9, db = _substrate_v4(), _v1._db_path()
    if not os.path.exists(db):
        print(json.dumps({"entities": [], "subjects": [], "unregistered": []}))
        return 0
    row = lambda r: {"id": r["id"], "name": r["name"], "kind": r["kind"]}  # noqa: E731
    print(json.dumps({"entities": [row(r) for r in p9.list_entities(db)],
                      "subjects": [row(r) for r in p9.list_subjects(db)],
                      "unregistered": p9.unregistered(db)}, indent=2, ensure_ascii=False))
    return 0


# ---------------------------------------------------------------------------
# 1. main
# ---------------------------------------------------------------------------
def main(argv):
    if len(argv) >= 2 and argv[0] in ("entity", "subject") and argv[1] == "add":
        return _cmd_add(argv[0], argv[2:])
    if argv and argv[0] == "subjects":
        return _cmd_subjects(argv[1:])
    return _v13.main(argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
