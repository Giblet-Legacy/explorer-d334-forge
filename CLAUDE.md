# Forge Stack Context — The Cockpit (explorer-d334-forge)

CLAUDE.md — Context briefing for AI assistants working in this repository.

## What this repo is
This is a Tier 1 Consumer, not a primitive layer. It orchestrates
P1–P15. It never reimplements them. If a command needs crypto, storage,
trust, or gating, it calls the frozen primitive.

## The Immutable Rule
Entry point from v1.2: `forge_cli_v1_2.py` (SPEC_V1_2.md: LLLM provenance, inbox, status, polarity, lllm.db; frozen 1.2.0) over frozen `forge_cli_v1_1.py` (SPEC_V1_1.md) over frozen `forge_cli.py` v1.0.0 — never edit those or patch their `_layer` globally.
`forge_cli_v1_3.py` (SPEC_V1_3.md: P13 v3 gate, commit_cube, attest, LLLM engine via LLLM_CLI; frozen 1.3.0) is the entry point from v1.3.
`forge_cli_v1_4.py` (SPEC_V1_4.md: P9 v4 entities and subjects, predicates; frozen 1.4.0) is the layer over v1.3.
`forge_cli_v1_5.py` (SPEC_V1_5.md: `forge answer`; 1.5.0-dev, not frozen) is the layer over v1.4.
`forge_cli_v1_6.py` (SPEC_V1_6.md: `forge imagine`, `forge dreams`; 1.6.0-dev, not frozen) is the layer over v1.5.

Never rewrite a primitive. Add a layer. If a Cockpit behaviour needs
a primitive change, that is a new layer ABOVE the primitive, not an
edit to the primitive itself.

## LLM: LLLM, plus local Ollama for dreams only
The Cockpit never embeds an LLM and never calls OpenRouter or any
cloud backend. Every generative command is a subprocess call to LLLM
(`lllm gen`, `lllm ask`), with one exception James made on 2026-11-14
(NOTES): from v1.6, `forge imagine` may ask a local Ollama model
(127.0.0.1 only, gemma2:2b by default) to write the UNKNOWN face, and
nothing else. Never let Ollama write an asserted face (FACT, COUNTER,
CONTEXT). If LLLM or Ollama is unavailable, the commands that need it
fail with exit 1; nothing falls back. Commands that do not need them
must continue to work without them.

## Faces are explicit
Every `remember` and every claim uses an explicit `--face FACT|
COUNTER|OPINION|FICTION|CONTEXT|UNKNOWN`. No auto-classification in v1.

## Passphrases
Always via getpass interactive prompt. Never an env var. Never a
flag. Never logged. Never in shell history.

## Web UI scope
Reduced v1. The UI is a view over P8 SQLite and P9 substrate. No
writes through the UI in v1. No SpatialPod, no Exocortex.

## Dual-Device Workflow
We build on an S24 (Termux) and a laptop (VS Code). State is
confirmed, never assumed. LF-only. British English (-ise, artefact).
Good/Bad/Ugly CHANGELOG, latest at top.

## Header Discipline
Every file has a top header paragraph and a numbered function list.
Every function has a numbered header.
