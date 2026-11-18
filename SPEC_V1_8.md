# SPEC V1.8 — explorer-d334-forge (The Cockpit: drafts in the order written)

SPEC_V1_8.md — specification for forge_cli_v1_8.py, the layer above Cockpit v1.7.

Function:
    Found by the VPS check on 2026-11-18. A draft's id is
    `<milliseconds>-<8 hex of its sha256>`, and v1.2's `_pending_drafts`
    sorts by that id. Two drafts written in the same millisecond are
    therefore ordered by their hash, which is effectively random. The
    inbox could list them, and `inbox commit` could sign them, in an
    order other than the one they were written in. v1.8 orders the inbox
    by each draft's own `created_at` and writes `created_at` so it
    always increases. James: "yes" (2026-11-18). SPEC_V1_7.md remains
    authoritative for everything this document does not change.
    forge_cli.py and forge_cli_v1_1 to v1_7 are not edited.

Tier:      Tier 1 — Consumer (The Cockpit)
Depends:   forge_cli_v1_7.py (1.7.0), forge_cli_v1_2.py (inbox, filing)
Version:   SPEC V1.8 1.8.0
Licence:   MSL-1.0
Author:    James Gilbert (Giblets Forge)

---

## 1. Order of the inbox

`pending_drafts()` returns `(id, path)` for every `*.json` in
`$FORGE_HOME/inbox`, sorted by:

1. the draft's `created_at`, if the file reads as a JSON object with a
   finite number there; otherwise the id's millisecond prefix / 1000
   (as v1.2), or 0 if the id has none;
2. then the id.

A draft that cannot be read is still listed, and refused at commit, as
in v1.7.

## 2. Writing

`write_draft_any(fields)` is v1.7's, with one change: `created_at` is
`max(time.time(), latest + 0.000001)`, where `latest` is the greatest
`created_at` among pending drafts. Each new draft therefore sorts after
every draft already waiting, even when the clock has not moved. The file
shape, the id rule (`<int(created_at*1000)>-<sha256[:8]>`), the
validation and the atomic write are v1.7's. A claim draft keeps exactly
v1.2's keys.

## 3. `forge inbox`

`list`, `commit` and `drop` behave as in v1.7, but use §1's order.
Commit still goes entities, then subjects, then claims, and within each
kind it now follows the order written. Every other command is v1.7's.

## 4. Tests (test_forge_v1_8.py)

- Drafts written while the clock is frozen are listed, and committed, in
  the order written; their `created_at` values strictly increase.
- Drafts written by an older Cockpit in the same millisecond, whose
  hashes sort the other way, are ordered by `created_at`.
- An unreadable draft is listed by its id and refused at commit.
- A v1.8 claim draft has exactly v1.2's keys; `drop` and other commands
  are v1.7's.

The v1.2 suite's `test_inbox_commit_and_refuse` relied on two drafts
landing in different milliseconds, which is v1.2's own guarantee. Its
1.7.0 file is kept byte-identical in `archive/1.7.0/`, and
`test_forge_v1_2_v2.py` waits for the next millisecond between those two
writes. Same-millisecond order is tested here, against v1.8.

---

## Document control

- **SPEC V1.8 1.8.0** — 2026-11-18, by the VS Code AI on James's "yes".
  Not frozen.
