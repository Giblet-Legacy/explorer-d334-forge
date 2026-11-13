# SPEC V1.2 — explorer-d334-forge (The Cockpit: LLLM provenance, inbox, status)

SPEC_V1_2.md — specification for forge_cli_v1_2.py, the layer above Cockpit v1.1.0.

Function:
    Three additions above Cockpit v1.1.0 (SPEC_V1_1.md), needed for
    The Legacy's Projection: every LLLM-generated claim names the exact
    build it came from and that build is anchored in the ledger; drafts
    written by The Legacy are committed here, in the terminal, with the
    passphrase entered here; and a passphrase-free status summary that
    The Legacy can show. forge_cli.py and forge_cli_v1_1.py are frozen
    and not edited. Where this document is silent, SPEC_V1_1.md applies.

Tier:      Tier 1 — Consumer (The Cockpit)
Depends:   Cockpit v1.1.0; LLLM (`lllm gen`, `lllm info`, and
           `$LLLM_HOME/models/<build_id>/build.json`, read-only)
Version:   SPEC 1.2.0
Licence:   MSL-1.0
Author:    James Gilbert (Giblets Forge)

---

## 1. LLLM provenance

### 1.1 Why

v1.1 records `build_id` by scraping `lllm info` and ignores the
warnings that command prints ("capsule edited since this build",
"<file> changed since this build"). A dream made by edited code was
recorded under a build_id that no longer describes the generator.
LLLM already writes a content-addressed identity for every build
(`models/<build_id>/build.json`: corpus hash, trained-doc hash, code
hashes, capsule id); nothing on the Forge side recorded it.

### 1.2 lllm_provenance() -> dict

Runs `lllm info`. Reads the build id from its `build:` line and every
line starting `WARNING`. Reads `$LLLM_HOME/models/<build_id>/build.json`
and returns `{build_id, build_json_sha256, identity, warnings}`.
RuntimeError if LLLM is unavailable, reports no current build, or the
build.json is missing or not JSON.

### 1.3 dream / think / reason

As v1.1, plus, after `lllm gen` and before anything is written:
1. Provenance (§1.2). Any warning → exit 1, "LLLM build no longer
   matches its code: …; run `lllm build`". Nothing is written.
2. The capsule carries `build_id` (as v1.1) and
   `lllm: {build_id, build_json_sha256}`.
3. **Anchor.** If the ledger holds no record with `type ==
   "lllm.build"` for this `build_json_sha256`, one is appended first,
   signed by the operator key: `{type: "lllm.build", build_id,
   build_json_sha256, identity}`. Then the claim is committed (v1.1
   §4). So every generated claim's build is anchored earlier in the
   same ledger.

## 2. The inbox (drafts from The Legacy)

The Legacy never signs and never sees a passphrase (Cockpit SPEC.md
§9: passphrases only through getpass). It writes **drafts**; the
operator commits them here.

### 2.1 Draft format

`$FORGE_HOME/inbox/<epoch_ms>-<sha256[:8]>.json`, UTF-8 JSON:

    {"draft": "forge.draft/1", "subject": str, "object": str,
     "text": str, "face": FACE, "created_at": float}

`validate_draft(d)` raises ValueError unless: exactly those keys;
`draft` is `forge.draft/1`; subject and object are non-empty str of at
most 200 characters; text is a non-empty str of at most 2000; face is
one of the six; created_at is a finite number. `write_draft(fields)`
validates, writes atomically (temp file + `os.replace`) and returns the
draft id (file name without `.json`). Drafts are untrusted input.

### 2.2 forge inbox [list | commit | drop <id>]

- `list` (default): pending drafts, each validated (invalid ones are
  listed as invalid with the reason).
- `commit`: one passphrase prompt; each pending draft, oldest first,
  goes through the v1.1 write path for its face (Keystone Gate for
  UNKNOWN). Success → moved to `inbox/done/` with `claim_id` added;
  refusal or invalid draft → moved to `inbox/refused/` with `reason`.
  Exit 0 if every draft was handled, 1 if a ledger check fails (nothing
  further is processed).
- `drop <id>`: moved to `inbox/refused/` with reason "dropped by
  operator".

## 3. status() -> dict (no passphrase, read-only)

    {claims: {total, by_face{FACE: n}, attested, unverified},
     ledger: {entries, self_consistent, signer, p8_mirror},
     pending_proposals, inbox: {pending, done, refused},
     lllm_anchors: [build_id, ...]}

`self_consistent` is canon_verify_v2 against the signer named in the
ledger's own genesis entry. It proves the chain is intact and
single-signer, not whose key it is (that needs the passphrase:
`forge verify-ledger`). `p8_mirror` is True when `store.db`'s export
equals the ledger bytes, None when there is no store. `forge status`
prints it as JSON.

## 4. Polarity (for the Voice)

LLLM, the Voice (`Giblet-Legacy/lllm`, SPEC §4), answers only from
claims whose capsule has `polarity` `affirm` or `negate`. Decided
2026-11-13 (LLLM NOTES Q5, Q8; James: "i sign, yo decide"):

- `remember` and `inbox commit` write `polarity` for **FACT, COUNTER
  and CONTEXT** claims only. OPINION, FICTION and UNKNOWN claims get
  none, so the Voice never speaks them as fact.
- An object starting "not " means `negate`, and the "not " is removed
  ("The cat is not a dog" → subject `cat`, object `a dog`, negate).
  Otherwise `affirm`.
- `remember --polarity affirm|negate` overrides the detection. On a
  face without polarity, or with any other value, it is a usage error
  (exit 2) and nothing is written.
- Known limitation: P13's Keystone Gate compares subject and object
  only, not polarity.

## 5. LLLM output is OPINION, in its own database

James, 2026-11-13: "lllm should be stored in a different db and be
opinions". `dream`, `think` and `reason` now write to
`$FORGE_HOME/lllm.db` (P9 schema, through substrate_v3), always with
face OPINION, `source: "lllm"` and `generated_by: <command>`, and
never to `forge.db`. The Keystone Gate guards UNKNOWN claims, so it no
longer runs for generated text. The ledger, the P8 mirror and the LLLM
build anchor (§1.3) are unchanged: one audit trail for both
databases. `status()` adds `lllm_opinions`.

## 6. Tests (test_forge_v1_2.py)

- Provenance: parses `lllm info`; warnings, missing build or missing
  build.json refuse; nothing written on refusal.
- Dream: capsule carries the build hash, face OPINION, in lllm.db and
  not forge.db; the anchor precedes the claim in the ledger; a second dream on the same build adds no anchor; the
  ledger still verifies under P6.
- Inbox: drafts written by `write_draft` are committed; a contradicting
  UNKNOWN and an invalid file go to refused/ with a reason; drop works;
  the ledger grows by exactly the committed claims.
- status(): correct counts without a passphrase; a tampered ledger is
  not self-consistent.
- Polarity: FACT affirm, "is not" negate with "not" removed, CONTEXT
  override, none for FICTION / UNKNOWN / OPINION, usage errors; inbox
  drafts get the same rule.

---

## Document control

- **SPEC 1.2.0** — 2026-11-13, by the VS Code AI for James's "whole
  projection" request.
- Revised before freeze, 2026-11-13: §4 polarity and §5 LLLM output
  (James's answers to LLLM NOTES Q5–Q9).
