# SPEC V1.7 — explorer-d334-forge (The Cockpit: entity and subject drafts)

SPEC_V1_7.md — specification for forge_cli_v1_7.py, the layer above Cockpit v1.6.

Function:
    James (2026-11-16): the Legacy's "New claim" should have tabs for a
    new entity, a new subject and a new claim, "and a way to link the
    claims we create to a subject from a drop down and subject to a
    entity from a drop down; entity does not have this option as its an
    entity". The Legacy never signs: it writes drafts and the owner
    commits them here. v1.7 lets the inbox hold two more kinds of draft
    and commits them as P9 v4 entities, subjects and memberships, signed
    and in the ledger. Claim drafts are unchanged. SPEC_V1_6.md remains
    authoritative for everything this document does not change.
    forge_cli.py and forge_cli_v1_1 to v1_6 are not edited.

Tier:      Tier 1 — Consumer (The Cockpit)
Depends:   forge_cli_v1_6.py (1.6.0), forge_cli_v1_4.register, P9 substrate_v4 (4.0.0)
Version:   SPEC V1.7 1.7.0
Licence:   MSL-1.0
Author:    James Gilbert (Giblets Forge)

---

## 1. Drafts

Every draft carries `"draft": "forge.draft/1"` and a finite
`created_at`, as v1.2. A draft with no `kind` is a **claim** draft and is
exactly v1.2's (subject, object, face, text); its file is unchanged, so
older Cockpits and Legacies read it as before.

| kind | keys (besides draft, created_at) | rules |
| :--- | :--- | :--- |
| `entity` | `kind`, `name` | name: non-empty, at most 200 characters |
| `subject` | `kind`, `name`, `entity` | name as above; `entity`: the name of the entity it belongs to, non-empty, at most 200 |

Any other key, kind or value is refused (`ValueError`), as v1.2 refuses
a malformed claim draft.

- `write_draft_any(fields) -> draft_id`: validates, then writes as v1.2's
  `write_draft` (atomic, same id scheme, same inbox).
- `validate_any(d)`: the matching validator for the draft's kind.
- `describe(d) -> dict`: `{"kind", ...the draft's own fields}` for
  display (the Legacy's pending list).

## 2. `forge inbox` (list)

Lists every pending draft of every kind, one line each: claims as
v1.2 shows them, `entity <name>`, `subject <name> -> <entity>`; a draft
that fails validation is listed as invalid with its reason.

## 3. `forge inbox commit`

Loads the key once (v1.3). Commits pending drafts in this order, so one
commit can create an entity, a subject in it and a claim about that
subject: **entities, then subjects, then claims** (each group in the
order it was drafted).

- **entity**: `register("entity", name)` (v1.4: P9 record and the same
  signed record in the ledger). Already registered: filed as done with a
  note, not an error.
- **subject**: the entity must already be registered (by name, P9
  `find`, an entity); if not, the draft is refused with a reason.
  `register("subject", name)`, then P9 `add_member(subject, entity)`; a
  new membership's signed capsule is appended to the ledger too.
- **claim**: exactly v1.3's commit (P13 v3 gate for UNKNOWN, v1.2
  capsule, v1.1 commit).

A refused draft is filed under `inbox/refused/` with its reason; a
committed one under `inbox/done/` with the ids it produced. A failure to
write stops the commit, as v1.3. Output: `committed N, refused M`.

## 4. Commands

Every other command is v1.6's.

## 5. Tests (test_forge_v1_7.py)

- entity, subject and claim drafts validate, write and describe; bad
  drafts (missing name, extra key, unknown kind, over-long name) refused.
- a claim draft written by v1.7 is byte-for-byte a v1.2 draft.
- `inbox commit` with an entity, a subject in it and a claim about the
  subject, drafted in reverse order: all three committed; P9 lists the
  entity, the subject and the membership; the ledger gains the entity,
  subject and membership records and the claim.
- a subject naming an unregistered entity is refused, named, and filed
  under refused; a second commit of an existing entity is done, not new.
- `inbox` lists every kind.

---

## Document control

- **SPEC V1.7 1.7.0** — 2026-11-16, by the VS Code AI on James's request.
