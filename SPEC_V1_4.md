# SPEC V1.4 — explorer-d334-forge (The Cockpit: entities, subjects, predicates)

SPEC_V1_4.md — specification for forge_cli_v1_4.py, the layer above Cockpit v1.3.0.

Function:
    Lets the Cockpit write the nouns P9 v4 stores (James: "i am an
    entity … hal layer is a subject"), and claims with a predicate, such
    as "the-legacy depends on explorer-d334-forge". SPEC_V1_3.md remains
    authoritative for everything this document does not change.
    forge_cli.py and forge_cli_v1_1 to v1_3 are not edited.

Tier:      Tier 1 — Consumer (The Cockpit)
Depends:   forge_cli_v1_3.py (1.3.0), P9 substrate_v4 (4.0.0)
Version:   SPEC V1.4 1.4.0
Licence:   MSL-1.0
Author:    James Gilbert (Giblets Forge)

---

## 1. register(kind_of, name, key, kind=None) -> (id, new)

- `kind_of` is "entity" or "subject" (else ValueError). P9 v4 is loaded
  from `../substrate-layer` by name; `init_db` (v4) runs on forge.db
  first, so a v3 database gains the tables.
- Calls P9 v4 `add_entity` / `add_subject` (its name rules and errors
  apply). `new` is False when the name was already registered.
- When new, the stored signed record (the P9 v4 capsule) is appended to
  the ledger with v1.1's `_append` (P4, P8 mirror), after
  `_check_ledger`, so the ledger still holds everything P9 does.

## 2. commit_cube(subject, obj, faces, key, predicate=None)

v1.3's commit_cube, with an optional predicate: a non-empty string
(else ValueError), stored as the capsule's `predicate` before signing.
Without it the cube is exactly v1.3's.

## 3. Commands

- `forge entity add <name…> [--kind K]` and
  `forge subject add <name…> [--kind K]`: print the id and
  "registered" or "already registered"; exit 2 on a bad name or kind.
  Passphrase via getpass, as every write.
- `forge subjects`: JSON `{"entities": [...], "subjects": [...],
  "unregistered": [...]}` from P9 v4, read-only, no passphrase.

Every other command is v1.3's.

## 4. Tests (test_forge_v1_4.py)

- register: entity and subject rows in P9, one ledger record each,
  the same name again is not new and appends nothing, a name of the
  other type and a bad kind_of are refused; the ledger verifies.
- commit_cube with a predicate stores it; a bad predicate is refused.
- the three commands, including `subjects` listing unregistered claim
  subjects.

---

## Document control

- **SPEC V1.4 1.4.0** — 2026-11-13, by the VS Code AI on James's
  delegation ("the subjects need their own orb with their claims
  orbiting them … connections between each other").
