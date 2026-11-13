# CHANGELOG — explorer-d334-forge (The Cockpit)

CHANGELOG.md — build history for The Cockpit, latest entry at top.

Function:
    Records the Good / Bad / Ugly of every build step for this
    consumer. Updated at every sign-off. Format never changes shape,
    even when a section is empty.

## [Unreleased]

### Good

- (none)

### Bad

- (none)

### Ugly

- (none)

## [v1.2.0] — 2026-11-13 — FROZEN

### Good

- Revised before freeze (SPEC_V1_2 §4, §5), from James's answers to
  LLLM NOTES Q5–Q9: `remember` and `inbox commit` write `polarity` for
  FACT / COUNTER / CONTEXT ("is not" → negate, `--polarity`
  overrides), so the Voice can answer; `dream` / `think` / `reason`
  store LLLM output as OPINION in its own `lllm.db`, never in
  forge.db (one ledger for both). 46/46 pass.
- `SPEC_V1_2.md`, `test_forge_v1_2.py` (6 tests, run red first) and `forge_cli_v1_2.py`. 44/44 pass (v1.0 22, v1.1 16, v1.2 6).
- LLLM provenance: `dream`/`think`/`reason` read the build identity LLLM already writes (`$LLLM_HOME/models/<id>/build.json`), record its sha256 in the claim, refuse when `lllm info` warns the code or capsule changed since the build, and anchor each build in the ledger once (`type: lllm.build`) before the first claim it produced.
- Inbox: The Legacy writes drafts (`forge.draft/1`); `forge inbox [list | commit | drop <id>]` commits them here, passphrase via getpass. Drafts are validated as untrusted input; refusals are filed with a reason.
- `status()`: passphrase-free, read-only summary (claims by face, attested, ledger self-consistency via P6 v2, P8 mirror, open proposals, inbox, LLLM anchors) for The Legacy; `forge status` prints it.
- Frozen at 1.2.0 (James: "freeze", 2026-11-13).

### Bad

- Frozen on the laptop run alone (2026-11-13); confirmed on the S24 by James, 2026-11-13.
- Claims remembered before this revision have no `polarity`, so the
  Voice will not speak them; re-remember them (or supersede) to add it.
- The LLLM repo pushed to GitHub has no `ask` command (its README lists one), so `forge ask` fails against it. Left to LLLM's own roadmap (REBUILD_SPEC Stage 5).

### Ugly

- Provenance reads `lllm info` just after `lllm gen`; a build switched between the two calls would be misattributed. LLLM's runs/ journal (its ROADMAP Phase 4) would close this.

## [v1.1.0] — 2026-11-13 — FROZEN

### Good

- `SPEC_V1_1.md`, `test_forge_v1_1.py` (16 tests, run red first) and `forge_cli_v1_1.py`: the Cockpit now runs on the current layer of every primitive (P2 sign_v2 … P15 hal_v2, P5 genesis_v3, P6 canon_verify_v2, P9 substrate_v3, P12 rules_v3, P14 leighton_engine_v3). forge_cli.py is frozen and never patched globally; its 22 tests still run on v1 in the same process. 38/38 pass from the repo and its parent.
- Every write goes P9 → P4 (genesis_v3 for the first entry, ledger_v2 after) → P8: `store.db` mirrors the ledger and must match it byte for byte. Nothing wrote P8 before.
- Capsules record their `face`, so the Keystone Gate sees real faces (v1 gated every claim as a FACT) and `cubes --face` filters. Gate memory fails closed.
- `forge trust` uses P14 V3 in days (λ₀ 1.5, k 0.1 per day): a fresh claim shows λ ≈ 1.5. v1 always printed 1.00.
- HAL loop works end to end: new `forge propose`, `pending` lists open proposals, `approve`/`refuse` take a seq or hash prefix, accept an optional λ attestation, append the seal to the ledger and link it to the claim in P9 (so SCP Substrate's glow can light).
- `verify-ledger` uses P6 v2 (empty ledger is exit 2, not "intact") and checks the P8 mirror. `health` probes every current layer with a real round trip (`probe_layers()`, reused by The Legacy). `web` names the read-only views (SCP Substrate 8085, Legacy 8080).
- README status corrected: it still said 0.0.0-dev after the v1.0.0 freeze.
- Built on James's delegation ("fix all 11 issues"). Frozen at 1.1.0 on James's sign-off ("freeze all", 2026-11-13).

### Bad

- Frozen on the laptop run alone (2026-11-13); confirmed on the S24 by James, 2026-11-13.
- A CRLF ledger written by Cockpit v1.0 on Windows is refused with a pointer to ledger-layer NOTES D1; v1.1 does not convert it. No such ledger exists on the laptop today.
- Claims written by v1.0 with an empty subject or object, or with no single face, make the gate refuse every UNKNOWN write (fail closed by design).

### Ugly

- `sign`, `verify` and `record` reuse v1.0.0's handlers by swapping `forge_cli._layer` for the duration of the call. Single-threaded CLI only.
- The first write session was lost when this repo was re-cloned at 16:39 before it was committed; the files were rewritten from the same spec and re-run red, then green.

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
