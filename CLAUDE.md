# Forge Stack Context — The Cockpit (explorer-d334-forge)

CLAUDE.md — Context briefing for AI assistants working in this repository.

## What this repo is
This is a Tier 1 Consumer, not a primitive layer. It orchestrates
P1–P15. It never reimplements them. If a command needs crypto, storage,
trust, or gating, it calls the frozen primitive.

## The Immutable Rule
Entry point from v1.2: `forge_cli_v1_2.py` (SPEC_V1_2.md: LLLM provenance, inbox, status, polarity, lllm.db; frozen 1.2.0) over frozen `forge_cli_v1_1.py` (SPEC_V1_1.md) over frozen `forge_cli.py` v1.0.0 — never edit those or patch their `_layer` globally.
`forge_cli_v1_3.py` (SPEC_V1_3.md: P13 v3 gate, commit_cube, attest, LLLM engine via LLLM_CLI; frozen 1.3.0) is the entry point from v1.3.

Never rewrite a primitive. Add a layer. If a Cockpit behaviour needs
a primitive change, that is a new layer ABOVE the primitive, not an
edit to the primitive itself.

## LLM: LLLM only
The Cockpit never embeds an LLM and never calls Ollama, OpenRouter,
or any cloud backend. Every generative command is a subprocess call
to LLLM (`lllm gen`, `lllm ask`). If LLLM is unavailable, those
commands fail with exit 1. Commands that do not need LLLM must
continue to work without it.

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
