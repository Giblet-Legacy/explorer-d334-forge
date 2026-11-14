# SPEC V1.5 — explorer-d334-forge (The Cockpit: answering a question)

SPEC_V1_5.md — specification for forge_cli_v1_5.py, the layer above Cockpit v1.4.0.

Function:
    Lets the owner answer an open question. A question is a claim's
    UNKNOWN face; until now nothing could close one, so every question
    ever asked stayed in the Weaver's briefing for good. Answering
    supersedes the claim (P9) with a signed copy whose UNKNOWN face is
    cleared and which carries the question and its answer, and appends
    that copy to the ledger. SPEC_V1_4.md remains authoritative for
    everything this document does not change. forge_cli.py and
    forge_cli_v1_1 to v1_4 are not edited.

Tier:      Tier 1 — Consumer (The Cockpit)
Depends:   forge_cli_v1_4.py (1.4.0), P9 substrate_v3 supersede_claim (via v1.1's layer map)
Version:   SPEC V1.5 1.5.0
Licence:   MSL-1.0
Author:    James Gilbert (Giblets Forge)

---

## 1. find_claim(ref) -> claim_id

- `ref` is a full claim id or a prefix of one, at least 8 hexadecimal
  characters, case-insensitive (the briefing shows 12).
- Searches every claim in forge.db, active or not.
- ValueError if `ref` is not at least 8 hex characters, or matches more
  than one claim; KeyError if it matches none (or forge.db is missing).

## 2. answer(claim_id, text, key) -> (new_claim_id, ledger entry)

Checks, in this order, before anything is written:

1. `text` is a non-empty string once stripped (else ValueError).
2. The claim exists (KeyError).
3. Its signature verifies under P9 (`read_claim(verify=True)`; else
   ValueError).
4. It is active (else ValueError: already superseded).
5. Its UNKNOWN face is a non-empty string (else ValueError: not a
   question).
6. The ledger verifies under the key (v1.1's `_check_ledger`).

Then:

- The new capsule is the old one without `signature`, with
  `UNKNOWN` set to null and one key added:
  `answers: {"claim_id": <old id>, "question": <old UNKNOWN text>,
  "answer": <text, stripped>}`. Every other key (subject, object,
  face, polarity, predicate, the other five faces) is unchanged.
- P9 `supersede_claim` signs it and, in one transaction, marks the old
  claim inactive with `superseded_by` and inserts the new one active.
- The new signed claim is appended to the ledger with v1.1's `_append`
  (P4, P8 mirror), as every claim the Cockpit writes is.

No keystone gate: the gate checks a new UNKNOWN against memory; an
answer removes one and adds none.

Effect: readers of active claims (the Weaver, the Legacy, the Field)
no longer see the question. The answer stays in the signed claim and
the ledger, with the question it closed.

## 3. Command

- `forge answer <claim-id-or-prefix> <answer…>`: prints the question,
  the answer, and `answered <old id 12> -> <new id>`. Passphrase via
  getpass, as every write. Exit 2 on a bad, unknown, ambiguous or
  already-answered reference, a claim with no question, or an empty
  answer; 1 on any other failure; 130 on Ctrl-C.

Every other command is v1.4's.

## 4. Tests (test_forge_v1_5.py)

- find_claim: full id, prefix, upper case, too short, no match,
  ambiguous.
- answer: the new claim keeps every other field, clears UNKNOWN and
  carries the question and answer; the old claim is inactive and
  superseded by it; no active claim still asks the question; the
  ledger gains exactly that signed claim and verifies.
- answer refuses an empty answer, an unknown id, a claim with no
  question and a second answer to the same question, writing nothing.
- the command, including exit 2 on a refusal.

---

## Document control

- **SPEC V1.5 1.5.0** — 2026-11-14, by the VS Code AI on James's
  delegation ("yes build it"), after the Morning Briefing kept
  returning three envelope-layer questions already resolved in NOTES.
