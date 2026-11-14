# SPEC V1.6 — explorer-d334-forge (The Cockpit: imagining)

SPEC_V1_6.md — specification for forge_cli_v1_6.py, the layer above Cockpit v1.5.

Function:
    Gives the Cockpit back the dreaming the old explorer-d334 had: a
    small local model (Ollama, gemma2:2b by default) dreams across a
    few of the owner's own claims, and the dream is kept as an UNKNOWN
    claim, gated, signed and in the ledger, with the claims it came
    from. Kept light on purpose (James: "keep it leight"): no trust
    maths, no quarantine; a dream is a dream, and the owner keeps it
    or answers it (`forge answer`, v1.5). SPEC_V1_5.md remains
    authoritative for everything this document does not change.
    forge_cli.py and forge_cli_v1_1 to v1_5 are not edited.

Tier:      Tier 1 — Consumer (The Cockpit)
Depends:   forge_cli_v1_5.py; Ollama on 127.0.0.1:11434 (only for `imagine`)
Version:   SPEC V1.6 1.6.0
Licence:   MSL-1.0
Author:    James Gilbert (Giblets Forge)

---

## 1. The Ollama rule

The v1.0 rule "LLLM only, no Ollama" is narrowed by James, not
removed: a local Ollama model may write the **UNKNOWN face only**, and
only through `forge imagine`. Everything asserted (FACT, COUNTER,
CONTEXT) stays the owner's or the LLLM's. Ollama is reached at
`http://127.0.0.1:11434` only; no other host, no cloud. If Ollama is
not running or the model is missing, `imagine` fails with exit 1 and
`Ollama unavailable: <reason>`; nothing falls back. Every other
command works without Ollama.

The model is `gemma2:2b`, or `FORGE_DREAM_MODEL` if set (a model
name, not a host).

## 2. pick_seeds(subject=None, n=3) -> [claim rows]

- Active claims in forge.db that have a FACT, CONTEXT or COUNTER text.
- With `subject`, only claims whose subject equals it, ignoring case
  and surrounding spaces.
- Up to `n` of them, chosen at random (`random.sample`). An empty list
  when there are none.

## 3. imagine(key, subject=None) -> (claim_id, dream text, seeds)

1. Seeds from `pick_seeds(subject)`; ValueError if there are none.
2. The prompt gives each seed as "subject / object: text" and asks for
   a short dream, in the first person, that connects them: what could
   be built, what could go wrong, what they might mean together.
3. Ollama `POST /api/generate` (stream off). The reply, stripped and
   cut to 600 characters, is the dream; an empty reply is a
   RuntimeError.
4. The claim: subject = `subject` if given, else the first seed's
   subject; object = "dream"; UNKNOWN face = the dream. Extra fields:
   `source: "ollama"`, `model` (name), `model_digest` (from
   `/api/tags`, or null), `seeds` (the seed claim ids),
   `dream_sha256`.
5. P13 Keystone Gate (v1.3's `gate`) on subject and object; a refusal
   is a ValueError and nothing is stored.
6. Signed and written to P9, appended to the ledger, as every claim
   (v1.1's `_commit`).

## 4. dreams(limit=10) -> [dict]

Active and superseded claims with `source: "ollama"`, newest first:
claim id, subject, model, the dream, whether it is still open (active
with UNKNOWN set) and its seeds as "subject / object" with their ids.
Read-only; no passphrase.

## 5. Commands

- `forge imagine [subject…]`: prints what it dreamt from, the dream and
  the new claim id. Passphrase via getpass. Exit 1 when Ollama is
  unavailable or the gate refuses; 2 when there is nothing to dream
  from.
- `forge dreams [--limit N]`: the dreams and their seeds, most recent
  first. Read-only.

Every other command is v1.5's.

## 6. Tests (test_forge_v1_6.py)

The Ollama call is replaced in tests; nothing reaches a network.

- pick_seeds: only asserted claims, the subject filter, the limit.
- imagine: the claim's faces, subject, object and provenance fields;
  the ledger gains it and verifies; a gate refusal stores nothing;
  no seeds is a ValueError.
- the Ollama URL is loopback.
- the commands, including exit 1 when Ollama is unavailable and
  `dreams` listing seeds.

---

## Document control

- **SPEC V1.6 1.6.0** — 2026-11-14, by the VS Code AI on James's
  delegation ("explorer was able to dream", "keep it leight"), after
  finding the old explorer-d334 dreamt through Ollama gemma2:2b.
