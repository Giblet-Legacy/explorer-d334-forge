# NOTES — explorer-d334-forge (The Cockpit)

NOTES.md — open questions, decisions, and harvested lessons for
The Cockpit.

Function:
    Records the reasoning behind The Cockpit's design decisions,
    the harvest from prior explorer-d334 clones, and any open
    questions that require owner review before v1 freeze.

## Harvest sources

Three local clones of the old `explorer-d334` were found:

| Path | README | CHANGELOG |
|---|---|---|
| `~/repos/The_Forge/explorer-d334`         | 2ee8032d (8KB) | 206 lines (full) |
| `~/repos/github/The_Forge/explorer-d334`  | 94109b97 (8KB) | 14 lines |
| `~/repos/github/explorer-d334-forge`      | 2ee8032d (8KB) | 14 lines |

Canonical harvest:
- README from `2ee8032d` (matches two of three clones).
- CHANGELOG from the 206-line version (the only one with history).
- The `94109b97` README is a hiring-pitch variant, not the product
  README. Not harvested for content, only noted.

## Decisions taken at spec time

1. **Faces, not Lenses.** The frozen P13 DataCube uses "faces". The
   old Cockpit used "Lenses". Renamed throughout.
2. **LLLM only.** No Ollama, no OpenRouter, no cloud backend.
   Generative commands call `lllm` as a subprocess. All other
   commands work without LLLM.
3. **Explicit --face always.** No auto-classification. The user (or
   calling agent) must state which face they intend.
4. **Passphrases via getpass only.** No `--passphrase` flag, no env
   var, no stdin redirect. Ctrl-C exits 130 cleanly.
5. **Reduced web UI.** Read-only view over P8 SQLite in v1. No
   writes through the web. No SpatialPod, no Exocortex.
6. **Dropped commands.** `evolve`, `cyber`, `exo*`, `spatial*`,
   `telemetry-*`, `improve`, `meditate`. Reasons in SPEC §4.
7. **`.scp.json` one-way import.** New command `migrate-scp`.
   Re-signs through P2, writes to P9 as face=CONTEXT, appends to
   ledger. Originals remain untouched on disk.

## Inherited debt dropped

- `.scp.json` sidecars (replaced by P2 `.sig` + canonical `.json`)
- `forge_config.py` hardcoded SECRET_KEY (replaced by P7 PEM)
- `simple_trust.py` ad-hoc trust math (replaced by P10/P11/P14)
- `datacube.jsonl` flat file (replaced by P4/P8)
- Six Lenses naming (replaced by Six Faces)
- `unified_consciousness.py` duplicate class (pattern not repeated)

## Open questions for owner review before v1 freeze

- **Freeze forge_cli_v1_4 at 1.4.0?** Entities, subjects, predicates
  (SPEC_V1_4.md). Built and green on the laptop (56/56). Not yet run on
  the S24. Raised 2026-11-13. Owner: James.
  **Resolved 2026-11-14 — James: "phone worked freeze please".** Frozen on the laptop run; S24 run still to be confirmed.

- **Freeze forge_cli_v1_3 at 1.3.0?** P13 v3 gate, commit_cube, attest
  (SPEC_V1_3.md), and the LLLM engine via LLLM_CLI. Built and green on the laptop (53/53). Not yet run on
  the S24. Raised 2026-11-13. Owner: James.
  **Resolved 2026-11-13 — James: "freeze commmit and push".** Frozen on the laptop run; S24 run still to be confirmed.

- **Q1. Signing key location.** Where does the operator's PEM key
  live by default? `~/.forge/key.pem`? Somewhere else? Configurable
  via env var or always flag-passed?
- **Q2. Ledger location.** Where does the Cockpit's own ledger live
  by default? `~/.forge/ledger.jsonl`? Per-workspace?
- **Q3. Migration scope.** Does `migrate-scp` process a single file
  or walk a directory? Current spec says directory. Confirm.
- **Q4. Health check depth.** 15 layer probes may take a few seconds.
  Is a `--quick` variant (skip LLM checks) wanted for CI-like use?
- **Q5. Web UI port.** 8085 default. Configurable? Env var or flag?
  **Resolved 2026-11-13 (SPEC_V1_1 §10), by the VS Code AI on James's
  delegation:** the Cockpit runs no web server. 8085 belongs to SCP
  Substrate, 8080 to The Legacy; `forge web` points at both.
- **Q6. Freeze v1.1.0?** **Resolved 2026-11-13 — James: "freeze all".** Frozen on the laptop run; confirmed on the S24 by James, 2026-11-13. forge_cli_v1_1.py built and green on the
  laptop (38/38 with v1). Not yet run on the S24. Raised 2026-11-13.
  Owner: James.

- **Q7. Freeze v1.2.0?** **Resolved 2026-11-13 — James: "freeze".** Frozen on the laptop run; confirmed on the S24 by James, 2026-11-13. forge_cli_v1_2.py (LLLM provenance, inbox,
  status) built and green on the laptop (44/44). Not yet run on the S24
  or against a real LLLM. Raised 2026-11-13. Owner: James.

## Known issues carried forward (from old CHANGELOG)

- Casing glitch in generated paths — not applicable to The Cockpit
  directly, but if `forge generate` returns paths from LLLM output,
  may need normalisation.
- LLLM dedupe credits first-sorted path, not origin repo — noted
  for LLLM v2, not blocking for The Cockpit.

## Not-yet-written (v2 candidates)

- Evolutionary code system (`forge evolve`)
- CyberForge dashboard (`forge cyber`)
- Exocortex (`forge exo*`)
- SpatialPod (`forge spatial*`)
- Write-through web UI
- Multi-user mode with key separation
- Telemetry (explicitly rejected — do not implement)
