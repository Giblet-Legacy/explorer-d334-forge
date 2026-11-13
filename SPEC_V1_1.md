# SPEC V1.1 — explorer-d334-forge (The Cockpit, current-layer wiring)

SPEC_V1_1.md — specification for forge_cli_v1_1.py, the layer above Cockpit v1.0.0.

Function:
    Describes the changes above Cockpit v1.0.0 (SPEC.md document
    control: "SPEC v1.1.0 would describe changes above Cockpit v1.0.0,
    per the Immutable Rule"). forge_cli.py is frozen and is not edited;
    forge_cli_v1_1.py is the new entry point. Where this document is
    silent, SPEC.md 1.0.0 applies unchanged.

Tier:      Tier 1 — Consumer (The Cockpit)
Depends:   P1 envelope_v2, P2 sign_v2, P3 freeze_v2, P4 ledger_v2,
           P5 genesis_v3, P6 canon_verify_v2, P7 record_v2,
           P8 store_v2_1, P9 substrate_v3, P10 weight_v2, P11 trust_v2,
           P12 rules_v3, P13 datacube_v2, P14 leighton_engine_v3,
           P15 hal_v2
Version:   SPEC 1.1.0
Licence:   MSL-1.0
Author:    James Gilbert (Giblets Forge)

---

## 1. Why v1.1 (the 2026-11-13 stack review)

1. forge_cli.py loads the frozen **v1** module of every layer except
   P1, so the v2 fixes recorded across the stack never reached the
   one program that writes data (CRLF ledgers on Windows, crashes on
   duplicate claims, unchecked signature algorithms, NaN λ accepted
   as AUTHORITY, mis-cased faces skipping the gate).
2. `forge trust` always printed λ = 1.00: a fixed observation at
   t = 0 and k = 0.1 applied to seconds since 1970.
3. SPEC.md says "P4/P8 append", but nothing wrote to P8.
4. Every existing claim entered the Keystone Gate as a FACT, and
   `cubes --face` never matched, because the capsule did not record
   the face it was remembered under.
5. `forge pending` looked for proposals nothing could create.
6. HAL seals reached the ledger but never the claim, so SCP
   Substrate's attested glow could not light.

## 2. Layer map

`_layer(name)` returns the current layer of every primitive (header
list above). The v1.0.0 `forge_cli._layer` is never replaced or
patched globally: its own tests keep running on v1 in the same
process.

## 3. Files under FORGE_HOME (unchanged names, one addition)

| File | Owner |
| --- | --- |
| `forge.db` | P9 substrate (claims, evidence) |
| `ledger.jsonl` | P4 ledger, LF-only (P4 SPEC_V2 §2) |
| `store.db` | **new**: P8 store, the SQLite mirror of the ledger |
| `key.pem` | P7, the operator key; the ledger's only signer |

## 4. The write path (remember, dream, think, reason, propose, approve, refuse, migrate-scp)

1. **Ledger check first.** A non-empty ledger must contain no `\r`
   (else: "ledger has CRLF line endings … see ledger-layer NOTES D1",
   exit 1) and must verify under the operator key with ledger_v2
   (else exit 1). Nothing is written if this fails.
2. **Claim capsule** = the P13 cube (datacube_v2 `create_cube`,
   `set_face`) plus `face` (the face it was remembered under) and any
   provenance (`build_id`, `lllm_output_sha256`, `migrated_from`).
3. **P9.** substrate_v3 `write_claim`. If the claim id already exists
   the command prints it, says it was already remembered, and appends
   nothing (P9 v2 made the write idempotent; the ledger must match).
4. **P4.** The signed capsule is appended: genesis_v3 `mint_genesis`
   for an empty or missing ledger, else ledger_v2 `append_entry`.
5. **P8.** store_v2_1 mirrors the ledger in `store.db`: any ledger
   entries the store lacks are appended in order with the same key,
   then `export_jsonl(store.db)` must equal the ledger's bytes
   exactly, else RuntimeError ("P8 store diverged from ledger").

A subject/object split that leaves an empty part is refused: exit 2
for `remember` ("phrase it as '<subject> is <object>'"), exit 1 for
generated text (`dream parse failed: …`, SPEC.md §8.4).

## 5. Faces and the Keystone Gate

- A capsule's face is its `face` key; for v1.0.0 capsules (no key) it
  is the single filled face of the cube. A capsule with neither is
  corrupt memory.
- The gate (datacube_v2 `keystone_gate`) gets every active claim
  (substrate_v3 `list_claims`) with its real face. It fails closed: a
  corrupt or malformed memory entry refuses the UNKNOWN write (exit 1)
  and names the claim.
- `cubes [--face F]` lists active claims with `claim_id`, `face`,
  `verified` (P9 verify-on-read), `subject`, `object`, `capsule`.
- `cube <id>` prints the claim row, its verification and its latest
  attestation (P9 SPEC_V3 §3.2).

## 6. Trust (`forge trust <claim_id>`)

One observation: λ₀ = 1.5 (`CLAIM_LAMBDA_ZERO`, the Weaver's value) at
the claim's `created_at`; reference time now; `k = STACK_CLAIM_K`
(0.1) with `time_unit = STACK_TIME_UNIT` ("days"), both from P14 V3.
Output: `claim_id` plus the full P14 V3 result. A claim written a
moment ago therefore shows λ ≈ 1.5, decaying to ≈ 1.18 after 10 days.

## 7. HAL: propose, pending, approve, refuse

- `forge propose <claim_id> --action <type> [--note <text>]` appends a
  signed record `{pending_hal: true, action_type, subject_id, note,
  proposed_at}` to the ledger (§4 steps 1, 4, 5). The claim must exist
  (exit 1 otherwise).
- `forge pending` lists proposals with no later seal for the same
  `subject_id` and `action_type`: `{seq, hash, action_type,
  subject_id, note}`.
- `forge approve <id> --key <pem> --lambda <f> [--reason <r>]
  [--attestation <file> --attester <did:key>]` and
  `forge refuse <id> --key <pem> --lambda <f> --reason <r> [...]`:
  - `<id>` is a pending proposal's seq number or a hash prefix of at
    least 6 characters. No such pending proposal: exit 1.
  - Quarantine (λ < 0.60): exit 2, nothing written (SPEC.md §8.2).
  - hal_v2 `create_seal` with the proposal's `action_type` and
    `subject_id`, `timestamp = now`. With `--attestation` and
    `--attester`, the seal records separation `attested`; without,
    `none` (the honest single-operator record). Seal errors: exit 2.
  - `sign_seal` with `--key`, then `verify_seal` must pass.
  - The seal is appended to the ledger, signed by the operator key
    (`FORGE_HOME/key.pem`; a second passphrase prompt only when
    `--key` names a different file).
  - If the subject is a P9 claim, the seal is linked to it with
    substrate_v3 `link_attestation` (approve → attestation, refuse →
    refusal).
  - Prints the seal hash.

## 8. verify-ledger

- Missing **or empty** ledger: exit 2 ("no ledger yet").
- canon_verify_v2 (zero-trust, now agrees with P4 v2): exit 1 on
  failure.
- If `store.db` exists: store_v2_1 `verify_store` must pass and its
  `export_jsonl` must equal the ledger bytes, else exit 1. A missing
  store is reported, not a failure.

## 9. health

`probe_layers()` returns 15 rows `{layer, status, error}`, each a real
round trip through the current layer in a private temporary directory
(no passphrase, no FORGE_HOME access). `forge health` prints them and
exits 1 if any FAIL. The Legacy calls the same function.

## 10. web

The Cockpit runs no web server. `forge web` prints where the read-only
views are — SCP Substrate on 127.0.0.1:8085 and The Legacy on
127.0.0.1:8080 — and exits 0. This settles the port clash in SPEC.md
§10 (8085 belongs to SCP Substrate).

## 11. Unchanged commands

`ask`, `ledger`, `sign`, `verify`, `record` keep their v1.0.0
behaviour; the last three run with the current P2 and P7 layers.

## 12. Tests (test_forge_v1_1.py)

Layer map; remember (genesis, LF ledger, P8 mirror, idempotent
repeat, short text refused); gate (contradiction refused with nothing
written, compatible UNKNOWN stored); cubes face filter and
verification; trust ≈ 1.5 in days; verify-ledger (missing, empty,
tampered, store mismatch); propose → pending → approve with P9
attestation; quarantine; refuse recorded as refusal; health all PASS;
dream parse failure and success with provenance; web; CRLF ledger
refused with nothing written; v1.0.0 `forge_cli._layer` untouched.

---

## Document control

- **SPEC 1.1.0** — 2026-11-13, by the VS Code AI on James's delegation
  ("fix all 11 issues").
