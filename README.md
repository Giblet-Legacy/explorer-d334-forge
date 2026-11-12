# explorer-d334-forge — The Cockpit

README.md — repository purpose and consumer contract for the
explorer-d334-forge (Tier 1, The Cockpit).

Function:
    The operator surface for The Legacy. A CLI (`./forge`) plus a
    reduced web UI that orchestrates the 15 frozen primitive layers
    into a usable whole. It implements nothing cryptographic itself.
    It calls P1–P15 for everything.

Tier:     Tier 1 — Consumer (The Cockpit)
Depends:  P2, P3, P4, P6, P7, P8, P9, P12, P13, P14, P15
LLM:      LLLM only (lllm CLI as subprocess). No other backend.
Licence:  MSL-1.0
Author:   James Gilbert (Giblets Forge)
Status:   0.0.0-dev (in build, pre-freeze)

## What The Cockpit does

Maps every meaningful human action onto the frozen primitive layers:

- `forge remember "<text>" --face FACT` → P13 classify → P2 sign → P9 write → P4/P8 append
- `forge dream` → LLLM generates → P13 Keystone Gate → P2 sign → P9 write (UNKNOWN)
- `forge trust <id>` → P14 compute_lambda (full provenance)
- `forge approve <id>` / `forge refuse <id>` → P15 create_seal → P4 append
- `forge verify-ledger` → P6 zero-trust independent verification

## What The Cockpit does not do

- Does not implement cryptography, storage, trust math, or gating.
- Does not embed an LLM. Calls LLLM by subprocess.
- Does not classify faces automatically. `--face` is required.
- Does not write through the web UI in v1 (read-only view).
- Does not attempt to replace P1–P15. It consumes them.

## Verifying this repository

Each command maps to a frozen primitive. Verifying the Cockpit
verifies those calls, in order:

    pytest -q test_forge.py

Independent verification of the underlying stack remains the
primitives' responsibility, not the Cockpit's.
