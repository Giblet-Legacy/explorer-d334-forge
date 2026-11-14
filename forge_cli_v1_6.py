"""
forge_cli_v1_6.py — The Cockpit v1.6: imagining

Function:
    The entry point from v1.6 (SPEC_V1_6.md). Gives the Cockpit back
    the dreaming the old explorer-d334 had: a small local model
    (Ollama, gemma2:2b by default, 127.0.0.1 only) dreams across a few
    of the owner's claims, and the dream is kept as an UNKNOWN claim,
    gated, signed and in the ledger, with the claims it came from.
    `forge dreams` shows each dream and what it dreamt from. Light on
    purpose: no trust maths, no quarantine. Every other command is
    v1.5's. forge_cli.py and forge_cli_v1_1 to v1_5 are not edited.

Public API:
    1. main(argv) -> int
    2. pick_seeds(subject=None, n=3) -> [claim rows]
    3. imagine(key, subject=None) -> (claim_id, dream, seeds)
    4. dreams(limit=10) -> [dict]
    (re-exported from v1.5: find_claim, answer, register, commit_cube,
     gate, attest)

Internal helpers:
    5. _model     — FORGE_DREAM_MODEL or gemma2:2b
    6. _post      — JSON request to the local Ollama
    7. _ollama    — prompt -> (dream text, model digest or None)
    8. _prompt    — the dream prompt from the seeds
    9. _cmd_imagine
    10. _cmd_dreams

Tier:     Tier 1 — Consumer (The Cockpit)
Depends:  forge_cli_v1_5.py; Ollama on 127.0.0.1:11434 (imagine only)
Spec:     SPEC_V1_6.md 1.6.0 (over SPEC_V1_5.md 1.5.0)
Version:  1.6.0
Licence:  MSL-1.0
Author:   James Gilbert (Giblets Forge)
"""

import argparse
import hashlib
import json
import os
import random
import sys
import urllib.error
import urllib.request

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import forge_cli as _v1  # noqa: E402
import forge_cli_v1_1 as _v11  # noqa: E402
import forge_cli_v1_5 as _v15  # noqa: E402

_layer = _v11._layer
find_claim, answer, register, commit_cube, gate, attest = (
    _v15.find_claim, _v15.answer, _v15.register, _v15.commit_cube, _v15.gate, _v15.attest)

OLLAMA_URL = "http://127.0.0.1:11434"
DEFAULT_MODEL = "gemma2:2b"
_ASSERTED = ("FACT", "CONTEXT", "COUNTER")
_MAX_DREAM = 600


class OllamaUnavailable(RuntimeError):
    """Ollama is not running, or the model is not pulled."""


# ---------------------------------------------------------------------------
# 5. _model
# ---------------------------------------------------------------------------
def _model():
    return os.environ.get("FORGE_DREAM_MODEL", "").strip() or DEFAULT_MODEL


# ---------------------------------------------------------------------------
# 6. _post
#    Loopback only (SPEC_V1_6 §1): the host is fixed, never configurable.
# ---------------------------------------------------------------------------
def _post(path, body=None, timeout=180):
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(OLLAMA_URL + path, data=data,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise OllamaUnavailable(f"model {_model()} not found; run `ollama pull {_model()}`")
        raise OllamaUnavailable(f"HTTP {e.code}")
    except (urllib.error.URLError, OSError) as e:
        raise OllamaUnavailable(f"{getattr(e, 'reason', e)}; is `ollama serve` running?")


# ---------------------------------------------------------------------------
# 7. _ollama
# ---------------------------------------------------------------------------
def _ollama(prompt):
    model = _model()
    reply = _post("/api/generate", {"model": model, "prompt": prompt, "stream": False,
                                    "options": {"temperature": 0.9}})
    digest = None
    try:
        tags = _post("/api/tags", timeout=10)
        digest = next((m.get("digest") for m in tags.get("models", []) if m.get("name") == model), None)
    except OllamaUnavailable:
        pass
    return reply.get("response", ""), digest


# ---------------------------------------------------------------------------
# 8. _prompt
# ---------------------------------------------------------------------------
def _prompt(seeds):
    lines = []
    for s in seeds:
        cap = s["capsule"]
        face = next(f for f in _ASSERTED if cap.get(f))
        lines.append(f"- {cap.get('subject')} / {cap.get('object')}: {cap[face]}")
    return ("You are Explorer, the dreaming mind of James's Forge Stack. These are things "
            "you know:\n" + "\n".join(lines) + "\n\n"
            "Dream about them. In three or four sentences, in the first person, connect them "
            "in a way nobody has written down yet: what could be built from them, what could "
            "go wrong, or what they might mean together. Be imaginative but stay with what "
            "you know. Write only the dream.")


# ---------------------------------------------------------------------------
# 2. pick_seeds
#    SPEC_V1_6 §2.
# ---------------------------------------------------------------------------
def pick_seeds(subject=None, n=3):
    db = _v1._db_path()
    if not os.path.exists(db):
        return []
    want = subject.strip().casefold() if isinstance(subject, str) and subject.strip() else None
    rows = []
    for r in _layer("substrate").list_claims(db):
        cap = r["capsule"] or {}
        if not any(isinstance(cap.get(f), str) and cap[f].strip() for f in _ASSERTED):
            continue
        if want is not None and str(cap.get("subject", "")).strip().casefold() != want:
            continue
        rows.append(r)
    return random.sample(rows, min(n, len(rows)))


# ---------------------------------------------------------------------------
# 3. imagine
#    SPEC_V1_6 §3. Ollama, then the gate, then v1.1's _commit.
# ---------------------------------------------------------------------------
def imagine(key, subject=None):
    seeds = pick_seeds(subject)
    if not seeds:
        raise ValueError("nothing to dream from: no FACT, CONTEXT or COUNTER claims"
                         + (f" about {subject.strip()!r}" if subject else ""))
    text, digest = _ollama(_prompt(seeds))
    text = (text or "").strip()[:_MAX_DREAM]
    if not text:
        raise RuntimeError("the model returned an empty dream")
    about = subject.strip() if isinstance(subject, str) and subject.strip() else seeds[0]["capsule"]["subject"]
    claim = {"subject": about, "object": "dream"}
    gate(dict(claim))
    capsule = _v11._capsule(claim, "UNKNOWN", text, source="ollama", model=_model(),
                            model_digest=digest, seeds=[s["claim_id"] for s in seeds],
                            dream_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest())
    claim_id, _ = _v11._commit(capsule, key)
    return claim_id, text, seeds


# ---------------------------------------------------------------------------
# 4. dreams
#    SPEC_V1_6 §4. Read-only.
# ---------------------------------------------------------------------------
def dreams(limit=10):
    db = _v1._db_path()
    if not os.path.exists(db):
        return []
    sub = _layer("substrate")
    rows = [r for r in sub.list_claims(db, active_only=False) if (r["capsule"] or {}).get("source") == "ollama"]
    out = []
    for r in reversed(rows[-limit:] if limit else rows):
        cap = r["capsule"]
        seeds = []
        for sid in cap.get("seeds") or []:
            s = sub.read_claim(db, sid)
            sc = (s or {}).get("capsule") or {}
            seeds.append({"claim_id": sid, "about": f"{sc.get('subject')} / {sc.get('object')}" if s else "(missing)"})
        out.append({"claim_id": r["claim_id"], "subject": cap.get("subject"), "model": cap.get("model"),
                    "dream": cap.get("UNKNOWN") or (cap.get("answers") or {}).get("question"),
                    "open": bool(r["is_active"] and cap.get("UNKNOWN")),
                    "answer": (cap.get("answers") or {}).get("answer"),
                    "created_at": r["created_at"], "seeds": seeds})
    return out


# ---------------------------------------------------------------------------
# 9. _cmd_imagine
# ---------------------------------------------------------------------------
def _cmd_imagine(rest):
    subject = " ".join(rest).strip() or None
    if not pick_seeds(subject):
        print("nothing to dream from: no FACT, CONTEXT or COUNTER claims"
              + (f" about {subject!r}" if subject else ""), file=sys.stderr)
        return 2
    try:
        key = _v11._load_key(_v1._key_path())
        claim_id, text, seeds = imagine(key, subject)
    except KeyboardInterrupt:
        raise
    except OllamaUnavailable as e:
        print(f"Ollama unavailable: {e}", file=sys.stderr)
        return 1
    except ValueError as e:
        print(f"not kept: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"imagine failed: {e}", file=sys.stderr)
        return 1
    print("dreaming from:")
    for s in seeds:
        print(f"  {s['capsule'].get('subject')} / {s['capsule'].get('object')}  ({s['claim_id'][:12]})")
    print(f"\n{text}\n")
    print(f"kept as {claim_id}  (forge answer {claim_id[:12]} \"...\" when it's settled)")
    return 0


# ---------------------------------------------------------------------------
# 10. _cmd_dreams
# ---------------------------------------------------------------------------
def _cmd_dreams(rest):
    p = argparse.ArgumentParser(prog="forge dreams")
    p.add_argument("--limit", type=int, default=10)
    try:
        args = p.parse_args(rest)
    except SystemExit:
        return 2
    found = dreams(args.limit)
    if not found:
        print("no dreams yet; try `forge imagine`")
        return 0
    for d in found:
        state = "open" if d["open"] else "answered" if d["answer"] else "closed"
        print(f"{d['claim_id'][:12]}  {d['created_at'][:16]}  {d['subject']}  [{d['model']}, {state}]")
        print(f"  {d['dream']}")
        for s in d["seeds"]:
            print(f"    from {s['about']}  ({s['claim_id'][:12]})")
        if d["answer"]:
            print(f"  answer: {d['answer']}")
        print()
    return 0


# ---------------------------------------------------------------------------
# 1. main
# ---------------------------------------------------------------------------
def main(argv):
    handlers = {"imagine": _cmd_imagine, "dreams": _cmd_dreams}
    if argv and argv[0] in handlers:
        try:
            return handlers[argv[0]](argv[1:])
        except KeyboardInterrupt:
            print("interrupted", file=sys.stderr)
            return 130
    return _v15.main(argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
