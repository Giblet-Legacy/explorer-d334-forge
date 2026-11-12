# SPEC — explorer-d334-forge (The Cockpit)

SPEC.md — the complete consumer specification for The Cockpit.

Function:
    This document is the authoritative specification for Tier 1
    consumer explorer-d334-forge. It defines what the CLI does, what
    it refuses to do, and how every command maps onto the frozen
    primitive layers P1–P15.

Tier:      Tier 1 — Consumer (The Cockpit)
Depends:   P2, P3, P4, P6, P7, P8, P9, P12, P13, P14, P15
LLM:       LLLM only, via `lllm` subprocess
Version:   SPEC 1.0.0
Licence:   MSL-1.0
Author:    James Gilbert (Giblets Forge)

---

## 1. What The Cockpit Is

The Cockpit is the operator surface for The Legacy. It is a CLI
(`./forge`) plus a reduced read-only web view. Every meaningful
human action routes through a frozen primitive. No cryptography,
no storage, no trust math, no gating is implemented here.

The Cockpit is the first place the whole stack becomes usable by a
human instead of a test suite.

## 2. The Migration Discipline

Every command calls exactly one frozen primitive (or a short chain).
If a command cannot be expressed as a clean call into P1–P15, it is
NOT in v1.

| Old pattern (from explorer-d334 v1.0.0) | New frozen layer |
|---|---|
| `.scp.json` sidecar on every file     | P1 + P2 + P3      |
| `datacube.jsonl` flat file            | P4 + P8           |
| `lens_interactions` (SQLite)          | P9 substrate      |
| `simple_trust.py`                     | P10 + P11 + P14   |
| Six Lenses                            | P13 six faces     |
| `forge_config.py` SECRET_KEY          | P7 record (PEM)   |
| Dream / hypothesis writes             | P13 Keystone Gate |
| Human approval for consequential ops  | P15 HAL ladder    |
| 210 integration tests                 | Acceptance gate   |

## 3. Command Surface — V1 Mapped Commands

### Declare & Sign
| Command | Calls | Notes |
|---|---|---|
| `forge sign <file>` | P2 `sign_artifact` | Detached `.sig` sidecar |
| `forge verify <file>` | P2 `verify_artifact` | |
| `forge record <capsule.json> --key <pem>` | P7 `save_signed_record` | Passphrase via getpass |

### Remember & Classify
| Command | Calls | Notes |
|---|---|---|
| `forge remember "<text>" --face F` | P13 `create_cube` + `set_face` + `inspection_grade` → P2 `sign_capsule` → P9 `write_claim` → P4/P8 append | `--face` REQUIRED. No auto-classify. Keystone Gate fires on UNKNOWN |
| `forge cube <id>` | P9 `get_claim` → P13 `inspection_grade` | Shows all 6 faces + grade |
| `forge cubes [--face F]` | P9 list + filter | Paginated |

### Dream & Reason (LLLM required)
| Command | Calls | Notes |
|---|---|---|
| `forge dream` | `lllm gen` → P13 `keystone_gate` → P2 sign → P9 write (UNKNOWN) → P4/P8 append with `build_id` | Refuses if contradicts FACT/COUNTER/CONTEXT |
| `forge think` | `lllm gen` → P2 sign → P9 write | No gate — thoughts are not claims |
| `forge reason "<q>"` | P9 query + `lllm gen` → P2 sign → P9 write | |
| `forge ask "<q>"` | `lllm ask "<q>"` | Returns answer + citation + build_id |

### Trust & Verify
| Command | Calls | Notes |
|---|---|---|
| `forge trust <claim_id>` | P14 `compute_lambda` | λ + full parameter block |
| `forge verify-ledger` | P6 independent verify | Zero-trust — reads `.jsonl` directly |
| `forge ledger` | P4 / P8 list entries | |

### Human Gate (HAL)
| Command | Calls | Notes |
|---|---|---|
| `forge pending` | P15 list unsigned proposals | |
| `forge approve <id> --key <pem> --lambda <f>` | P15 `create_seal(approve)` + `sign_seal` → P4 append | Quarantine < 0.60 enforced |
| `forge refuse <id> --key <pem> --lambda <f> --reason "<r>"` | P15 `create_seal(refuse)` + `sign_seal` → P4 append | Refusal is an event, not silence |

### System
| Command | Calls | Notes |
|---|---|---|
| `forge health` | probes P1–P15 + SQLite integrity | 20+ checks |
| `forge status` | comprehensive summary | |
| `forge web` | serves read-only HTML from P8 SQLite | port 8085 |
| `forge migrate-scp <dir>` | one-way importer | See §5 |

## 4. Dropped Commands (with reasons)

| Old command | Reason dropped |
|---|---|
| `forge evolve` | Evolutionary code system — v2 |
| `forge cyber` | CyberForge dashboard — v2 |
| `forge exo*` | P.DE.I Exocortex — deferred by owner |
| `forge spatial*` | SpatialPod — v2 UI work |
| `forge telemetry-*` | No telemetry philosophy in The Legacy. Dropped permanently |
| `forge improve` | Deferred |
| `forge meditate` | No mapping to frozen primitives |

## 5. The `.scp.json` One-Way Converter

`forge migrate-scp <dir>` walks a directory and, for each
`.scp.json` found:

1. Reads and parses the payload.
2. Re-signs the payload via P2 `sign_capsule` (new did:key, new
   canonical form).
3. Writes to P9 substrate (face = CONTEXT — this is a historical
   artefact, not an active claim).
4. Appends the signed capsule to P4/P8 ledger.
5. Leaves the original `.scp.json` file UNTOUCHED on disk.

After migration is verified, the operator deletes the originals
manually. The Cockpit never mutates source files.

Migration is manual, invoked once per directory, offline. No network.

---

## 6. LLM Integration — LLLM Only

The Cockpit does not embed an LLM and does not call Ollama,
OpenRouter, or any cloud backend. Every generative command shells
out to the LLLM CLI as a subprocess.

    forge dream   →  lllm gen "<seed>"     →  text + build_id
    forge ask     →  lllm ask "<question>" →  answer + citation + build_id
    forge think   →  lllm gen "<seed>"     →  text + build_id
    forge reason  →  lllm gen "<prompt>"   →  text + build_id

Environment:
- `LLLM_HOME` must be set for LLLM to find its builds.
- If `LLLM_HOME` is unset OR `lllm` is not on PATH, commands that
  require LLLM fail cleanly with exit code 1 and the message
  `LLLM unavailable: <reason>`. No silent fallback.

Provenance:
- Every LLLM-generated artefact records `build_id` and the SHA-256
  of the LLLM output in its P4/P8 ledger entry.
- The `build_id` is part of the record, not metadata. Any future
  verification can re-run `lllm` against that build and confirm
  the output matched.

LLM-free commands (work without LLLM):
    forge sign, forge verify, forge record, forge remember,
    forge cube, forge cubes, forge trust, forge verify-ledger,
    forge ledger, forge pending, forge approve, forge refuse,
    forge health, forge status, forge migrate-scp

LLM-required commands (fail without LLLM):
    forge dream, forge think, forge reason, forge ask

## 7. The Keystone Gate Pipeline (`forge dream`)

The dream pipeline is the canonical example of a command that
touches every relevant layer in the correct order:

    1. lllm gen "<seed>"           →  raw text + build_id
    2. Parse raw text → structured claim {subject, object, ...}
    3. P13 keystone_gate(claim, existing)  →  refuse on contradiction
    4. P13 create_cube + set_face(UNKNOWN) →  classified cube
    5. P2 sign_capsule(cube, private_key)  →  signed capsule
    6. P9 write_claim(signed capsule)      →  stored in substrate
    7. P4/P8 append_entry(record with build_id + output_sha)
                                            →  ledger entry

If step 3 refuses, steps 4–7 do not run. The dream is not stored.

## 8. Function Contracts (for forge CLI)

### 8.1 `forge remember <text> --face <F>`
- Verifies `<F>` in {FACT, COUNTER, OPINION, FICTION, CONTEXT, UNKNOWN}
- If F == UNKNOWN: fires P13 keystone_gate against existing
  FACT/COUNTER/CONTEXT. Refuses on contradiction (exit 1).
- Creates cube (P13), signs (P2), writes to substrate (P9),
  appends to ledger (P4/P8).
- Passphrase prompt for signing key.
- Prints claim_id on success. Exit 0.

### 8.2 `forge approve <id> --key <pem> --lambda <f>`
- Loads PEM key (passphrase prompt).
- Calls P15 `create_seal(decision="approve", ...)`.
  - If lambda < 0.60: P15 raises ValueError. CLI exits 2
    (quarantine is a usage error, not a runtime error).
- Signs the seal (P2 via P15).
- Appends signed seal to P4/P8 ledger.
- Exit 0 on success. Prints seal hash.

### 8.3 `forge refuse <id> --key <pem> --lambda <f> --reason "<r>"`
- Same as approve, with `decision="refuse"` and `rationale=<r>`.
- A refusal is a signed event, not silence.

### 8.4 `forge dream`
- Verifies LLLM available (LLLM_HOME + PATH). Exit 1 if not.
- Calls `lllm gen` with a seed. Captures text + build_id.
- Parses text into structured claim. If parse fails: exit 1
  with `dream parse failed: <reason>`. Does not store.
- Runs the Keystone Gate (step 3 of §7).
- Signs, writes to substrate, appends to ledger.
- Prints claim_id + build_id.

### 8.5 `forge verify-ledger`
- Invokes P6 standalone verifier against the current ledger file.
- Does NOT trust P4's verify_ledger. Uses P6's independent
  reimplementation.
- Exit 0 if intact, exit 1 if tampered, exit 2 if ledger missing.

### 8.6 `forge health`
- Probes each layer in dependency order:
  - P1: import check + canonicalise round-trip
  - P2: sign/verify round-trip with ephemeral key
  - P3: freeze round-trip
  - P4: ledger file exists and chain verifies
  - P5: genesis exists in root
  - P6: canon_verify import + happy-path verify
  - P7: key file present (if configured)
  - P8: SQLite integrity check
  - P9: substrate schema present
  - P10: math sanity check (t=0 → λ₀)
  - P11: fusion round-trip
  - P12: engine instantiation
  - P13: cube construction round-trip
  - P14: compute + reproduce round-trip
  - P15: tier_for_lambda sanity check
- Prints a table with PASS/FAIL per layer.
- Exit 0 if all PASS, exit 1 if any FAIL.

## 9. Passphrase Handling

All passphrase-protected operations use `getpass.getpass()`:
- No `--passphrase` flag (would end up in shell history).
- No environment variable.
- No reading from stdin (would appear in process listings).
- No writing to disk, log, journal, or error message.
- Ctrl-C during prompt exits 130 with no traceback.

## 10. Web UI Scope (v1)

The web UI serves read-only HTML from P8 SQLite on port 8085.

In scope for v1:
- Dashboard (health summary, latest entries, latest claims)
- Cube browser (filter by face, grade)
- Pending proposals (read-only view of P15 pending)
- Ledger viewer (paginated, with hash chain verification badge)

Out of scope for v1:
- Any write action (approve/refuse/remember via web)
- SpatialPod
- Exocortex
- WebSocket streaming
- Authentication (single-operator localhost only)

## 11. Known Limitations (v1.0.0)

- LLM dependency is LLLM only. No fallback to Ollama, OpenRouter, or
  cloud. This is a sovereignty guarantee, not a limitation.
- Web UI is read-only. Writes go through the CLI.
- Single-operator only. HAL records `separation: none` honestly.
- No evolutionary code (`evolve`), no CyberForge (`cyber`), no
  Exocortex (`exo*`), no SpatialPod (`spatial*`). All deferred to v2.
- No telemetry. Ever.
- LLLM subprocess failure modes (parse errors, missing builds) are
  reported and exited cleanly, never silently swallowed.
- The `.scp.json` importer is one-way. Once migrated, the originals
  are not read again by any command.

## 12. What Success Looks Like

A user can clone the repo, install the two dependencies
(`cryptography`, and LLLM's own setup), and run:

    ./forge remember "The Earth orbits the Sun" --face FACT
    ./forge dream
    ./forge cubes --face UNKNOWN
    ./forge pending
    ./forge approve 3 --key ~/.forge/key.pem --lambda 1.8
    ./forge verify-ledger
    ./forge health

If that sequence works — signed claim stored, dream gated, unknown
cubes browsable, HAL proposals approved with seal, ledger verified
independently, health all green — the Cockpit is finished.

---

## Document control

- SPEC v1.0.0, frozen at sign-off.
- Implementation of `forge` v1.0.0 must match this spec.
- Tests in `test_forge.py` must match this spec.
- Changes require a new SPEC version. SPEC v1.1.0 would describe
  changes above Cockpit v1.0.0, per the Immutable Rule.
