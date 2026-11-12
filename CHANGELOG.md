# CHANGELOG — explorer-d334-forge (The Cockpit)

CHANGELOG.md — build history for The Cockpit, latest entry at top.

Function:
    Records the Good / Bad / Ugly of every build step for this
    consumer. Updated at every sign-off. Format never changes shape,
    even when a section is empty.

## [v1.0.0] — 2026-11-12

### Good
- `forge_cli.py` implemented to SPEC v1.0.0 (948 lines).
- 22/22 pytest tests pass.
- Full command surface: remember, cube, cubes, trust, verify-ledger,
  ledger, health, status, dream, think, reason, ask, pending,
  approve, refuse, sign, verify, record, web, migrate-scp.
- Explicit --face required. Keystone Gate enforced on UNKNOWN.
- LLLM-only integration. Generative commands fail with exit 1 if LLLM
  unavailable. All other commands work without it.
- HAL quarantine enforced: lambda < 0.60 exits 2.
- Passphrase via getpass only. Ctrl-C exits 130.
- P6 independent verification for `verify-ledger` (does not trust P4).

### Bad
- First test run: 11 failures. Root cause: `_layer()` looked for
  `../<name>` instead of `../<name>-layer`, so every layer import
  failed. Fixed by trying both `<name>-layer` and `<name>` in order.
  Single-function patch, all 11 resolved.

### Ugly
- (none)

### Good
- Repository scaffolded: `Giblet-Legacy/explorer-d334-forge` created
  as Tier 1 Consumer (The Cockpit).
- Harvested from three prior clones of `explorer-d334` (v1.0.0, 210
  tests passing at time of last release). Six Lenses renamed to Six
  Faces to match the frozen primitive vocabulary.
- LLM integration decision: LLLM only. No Ollama, no OpenRouter, no
  cloud fallback. Generative commands shell out to `lllm`.
- Passphrase decision: interactive getpass only. No env vars, no
  flags, no history leakage.
- Web UI scope reduced to read-only view over P8/P9 in v1.
- Face classification: explicit `--face` only. No auto-classify.

### Bad
- Old Cockpit carried ad-hoc debt: `.scp.json` sidecars, hardcoded
  SECRET_KEY in `forge_config.py`, `simple_trust.py` duplicated
  trust math, `datacube.jsonl` flat file. All replaced by frozen
  primitives (P2/P3/P7/P10/P11/P14/P4/P8/P13).

### Ugly
- (none)
