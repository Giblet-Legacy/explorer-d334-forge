# SPEC V1.3 — explorer-d334-forge (The Cockpit: P13 v3 gate, cubes, attestation)

SPEC_V1_3.md — specification for forge_cli_v1_3.py, the layer above Cockpit v1.2.0.

Function:
    Moves every Keystone Gate check onto P13 v3 (polarity-aware, so a
    subject can hold many claims), and gives the Cockpit two calls it
    lacked: commit one cube with several faces, and attest a claim with
    a key already loaded. SPEC_V1_2.md remains authoritative for
    everything this document does not change. forge_cli.py,
    forge_cli_v1_1.py and forge_cli_v1_2.py are not edited, and their
    `_layer` is not patched.

Tier:      Tier 1 — Consumer (The Cockpit)
Depends:   forge_cli_v1_2.py (1.2.0), P13 datacube_v3 (SPEC_V3 3.0.0)
Version:   SPEC V1.3 1.3.0
Licence:   MSL-1.0
Author:    James Gilbert (Giblets Forge)

---

## 1. Why v1.3

Signing the repos as subjects with several claims each failed: under
P13 v2's rule every UNKNOWN about a subject that already had a known
claim was refused. P13 v3 fixes the rule; the Cockpit pins P13 v2 in
v1.1's layer map, so a new Cockpit layer is needed to use it. The
Cockpit also had no way to write a multi-face cube or to approve
without asking for the passphrase again for each seal.

## 2. The gate

- `_memory()` is v1.1's (active claims, fail closed on a claim with
  no single face) with each entry's `polarity` added when its capsule
  has one.
- `gate(claim)` runs P13 v3 `keystone_gate(claim, _memory())`; P13 v3
  is imported from `../datacube-layer` directly.
- `remember --face UNKNOWN` and `inbox commit` of an UNKNOWN draft gate
  through `gate`. Everything else about those commands is v1.2's.

## 3. commit_cube(subject, obj, faces, key) -> (claim_id, entry | None)

- `faces` maps face names to non-empty strings; at least one; unknown
  face names or empty text raise ValueError.
- The cube's `face` (the one recorded in memory and given polarity) is
  the first of FACT, COUNTER, CONTEXT present, else the first present
  face in P13 order. Its polarity follows v1.2 (`not ` on the object
  negates and is removed).
- If `faces` has UNKNOWN, the claim (subject, object and the cube's
  polarity) passes `gate` first; a refusal is ValueError and nothing is
  written.
- The cube is built as v1.2 does (`_asserted_capsule`) with the other
  faces set by P13, then committed with v1.1 `_commit` (P9, P4, P8).
  `entry` is None if the identical cube was already remembered.

## 4. attest(claim_id, key, lam, reason="read and approved", action="attest") -> str

Exactly what `forge propose` then `forge approve` do, with the loaded
key and no prompts: a signed `pending_hal` proposal appended to the
ledger, a HAL v2 approve seal (quarantine below λ 0.60 refused as
ValueError), verified, appended, and linked to the claim as a P9 v3
attestation. Unknown claim → KeyError. Returns the seal's SHA-256.

## 5. Reaching the LLLM engine

v1.2 ran `lllm` from PATH. The engine's README installs `lllm` as a
bash function, which `subprocess` cannot see, and on Windows a `.cmd`
wrapper is not found by bare name either; and `lllm gen` reports a
refusal as text with exit 0. v1.3:

- `engine_command()`: if `LLLM_CLI` is set it must name an existing
  file (the engine's `lllm/cli.py`), run as `[sys.executable, LLLM_CLI]`;
  otherwise the `lllm` executable `shutil.which` finds; otherwise
  RuntimeError("LLLM unavailable: ...") saying how to set it up.
- `run_lllm(*args)`: `LLLM_HOME` must be set and exist (v1 rule), then
  runs `engine_command() + args` (timeout 120 s); a non-zero exit is
  RuntimeError("LLLM failed: ...").
- `lllm_gen(seed)`: `run_lllm("gen", seed)`; empty output, or output
  starting "(nothing", is RuntimeError("LLLM refused: ..."), so a
  refusal is never stored.
- `lllm_provenance()`: v1.2's rule, through `run_lllm`.
- `dream`, `think` and `reason` are v1.2's, through these three.

## 6. main

`remember`, `inbox`, `dream`, `think` and `reason` are v1.3's; every
other command is v1.2's.

## 7. Tests (test_forge_v1_3.py)

- remember: a second UNKNOWN on a subject with a known claim of
  another object is accepted; an opposite-polarity UNKNOWN is refused.
- inbox commit gates with v3 the same way.
- commit_cube: six faces stored, polarity on the chosen face, gate
  refusal writes nothing, bad faces refused, re-commit returns None.
- attest: proposal and seal in the ledger, attestation in P9, the
  ledger verifies; λ below 0.60 and an unknown claim refused.
- v1.2 commands still work through v1.3's main.
- engine_command: LLLM_CLI wins and runs with this Python; a missing
  LLLM_CLI file or no engine at all is RuntimeError; PATH is used
  otherwise. A real engine stand-in script answers `info` and `gen`
  end to end (provenance, dream into lllm.db); a refusal stores
  nothing.

---

## Document control

- **SPEC V1.3 1.3.0** — 2026-11-13, by the VS Code AI on James's
  delegation ("fix properly").
