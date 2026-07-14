# Society live-persona pilot — preregistration + design source (rev 1)

Status: council-routed design source under the **OWNER live-persona pilot
authorization (2026-07-14)** — the first governed live-model experiment on the
society substrate. This document IS the preregistration: on integration it is
the frozen commitment the single governed live run is measured against.
Authorizes SOLELY the design, audit, implementation, and ONE governed live
evidence pack of the bounded pilot below — nothing else (no training, no
adaptive intervention, no additional live runs, no society expansion). Parent
substrate: the integrated Society Seed (impl 001270) over S0..S2D + calibration.

## 1. Bounded scope (exactly the owner authorization)

The pilot re-runs the integrated `society_seed_v1` world UNCHANGED — three rooms
A–B–C, one portable token, cy's private Boolean fact, the one hard-coded
institutional rule `institution.token_stays_in_a.v1`, the six-kind action
vocabulary, eight deterministic ticks (scheduler rounds 0–7), six integer trust
edges — but **exactly one agent acts as a live pinned Ollama persona; the other
two remain scripted CONTROLS**.

- **Live agent:** `ada`. Rationale: ada both HANDLES the token (so it acts under
  the institutional constraint — a token-holder in room A is blocked from
  leaving) and perceives partially (room-scoped fog). `bo` and `cy` stay scripted
  (their integrated intent tails), so cy's private fact + the controls are
  preserved.
- **The one authenticated counterfactual fork is NOT run in the live pilot** (it
  requires deterministic intent substitution, which a live agent cannot provide).
  "Counterfactual propagation" is instead measured as the **live-vs-scripted-
  baseline departure** (§7) against the pinned Society Seed baseline
  (`society_seed_v1--seed42--b4f03e16d88940f3`, outcome `7ff002a7…`). The world,
  ticks, actions, institution, and evidence-authentication contracts are
  preserved; the fork is a scripted-baseline-only artifact.

## 2. Preregistered model, decoding, budgets (frozen at integration)

- **Model:** `huihui_ai/qwen2.5-abliterate:7b-instruct`, **pinned by served
  digest** (verified at run time against the preregistered digest via the
  audited `sweep` pinned-digest mechanism; a repulled/differing digest is a hard
  abort BEFORE any compute — never silently a different model). Backend: the
  integrated `ollama_local` driver / `LLMAgent` Ollama backend at the LAN
  endpoint (localhost:11434); the ONLY network egress.
- **Decoding:** temperature `0.0` (greedy), `num_predict` cap `256` tokens,
  a fixed backend `seed` (recorded; seed-support probed + logged, never assumed).
  These enter the run's regime identity.
- **Budgets:** at most one model call per live-agent activation; at most 8 live
  decisions (one per tick); a per-call wall-clock deadline (recorded as
  non-identity metadata). No retries that change identity — a failed/timed-out
  call resolves through the failure taxonomy (§5), never a silent re-ask.

## 3. Prompt (frozen template) + perception non-interference

Each live activation builds ONE prompt from the agent's **S2C actor-safe
observation ONLY** (the closed `trs.observation.actor.v1` content — visible room,
visible entities, actor-visible placements, departing portals) plus the
**society-legal action set** (§4) rendered as an enumerated menu. The prompt
carries NO privileged content, NO other agent's trust, NO private facts, NO chain
hashes, NO scripted intents. `prompt_version` is frozen and enters the regime.

**Leakage check (mandatory):** the prompt string is built exclusively by an
allowlist projection of the actor content + the legal-action ids; a regression
runs `assert_no_privileged_leak`-style structural checks on the assembled prompt
and asserts that mutating any privileged-only world fact never changes the
prompt bytes. A privileged token appearing in a prompt fails closed.

## 4. Legal-action enforcement (institution preserved)

The menu offered to the model is the **society-legal candidate set** at the
current state: the integrated S2B `candidate_effects` for the live body, filtered
by the frozen `institutional_filter` (a token-holder's blocked move-out is
removed). The model returns a choice; the parser (§5) maps it to exactly one
menu id. **The committed action is therefore always society-legal by
construction** — the institution constrains the live agent identically to a
scripted one. An out-of-menu / unparseable / empty response is a failure (§5),
never an illegal committed action.

## 5. Parser + preregistered failure taxonomy

`parser_version` frozen. The completion is parsed to a menu id by the integrated
`parse_llm_response` discipline (strict, versioned). Preregistered failure
taxonomy (each deterministic, coded, and reported — never silently retried,
never relabeled as success):

| code | trigger | resolution |
|---|---|---|
| `parse_failure` | no menu id extractable | the activation resolves to the canonical fallback (`pass` if the society dispatch permits it at that head; else the run terminates with a coded `parse_failure_termination`) |
| `illegal_selection` | a well-formed choice outside the offered menu | same canonical fallback / `invalid_action_termination` |
| `budget_exhausted` | call deadline/token cap hit | `externally_imposed_truncation` |
| `backend_unavailable` | model/endpoint/digest failure | hard abort BEFORE writing a partial pack (no run identity minted) |

Failures are counted in the effective-sample accounting (§6) and coded into the
`DecisionRecord.termination_kind` taxonomy. The canonical fallback is fixed and
preregistered so a failure never becomes a free unscripted action.

## 6. Evidence contract (CAPTURE-REPLAY; live-API determinism never claimed)

The pilot run directory is a spatial evidence set PLUS a society layer PLUS a
**live-capture layer** `persona.jsonl`: per live decision `{tick,
scheduler_position, prompt_hash, raw_completion, model_id, model_digest,
decoding, parsed_menu_id, parse_status, latency_ms (non-identity)}`. The pinned
digest + prompt + decoding + captures fully determine the derived run.

**Replay = re-derive from the captures, NEVER re-invoke the model.** The replay
gate re-runs the derivation from `persona.jsonl` + the scripted controls and
byte-compares every non-latency evidence field; a `LiveSourceEvidenceBinding`
(domain-separated) binds all files including `persona.jsonl`. Latency is recorded
but excluded from identity. This is the standing two-tier determinism (scripted =
re-execute; live = replay-from-captures).

## 7. Effective-sample accounting + result audit + the measurement

- **Effective-sample accounting:** decisions requested, decisions successfully
  parsed to a legal action, per-code failure counts, and the effective-N used for
  any reported quantity. A run whose effective-N is below a preregistered floor
  is reported as `underpowered` and yields no behavioral claim.
- **Result:** the **live-vs-scripted-baseline departure report** — per tick, the
  live agent's committed action vs. the scripted-baseline action; first
  divergence coordinate; the resulting trust-matrix delta, enforcement-count
  delta, and token-terminal-location delta vs. the pinned baseline; and the
  effective-sample summary. A privileged report + a closed-schema actor-safe
  report as in the seed.
- **Result audit:** the run + report are council-audited like every slice
  (result verdict), under the audit probe-reroute policy.

## 8. Claim ceiling (fixed, enforced in code)

*"one pinned local persona acted for one agent under partial observation and one
institutional constraint across eight deterministic ticks; the report quantifies
its departure from the deterministic scripted baseline. It makes NO claim of
emergence, realistic social behavior, alignment, human fidelity, or general
live-model reliability, and no claim beyond this single governed run."* Any other
claim string refuses.

## 9. Build/test discipline + the single governed run

The actor, prompt, parser, capture, derivation, and reports are built and
UNIT-TESTED against a **deterministic MOCK persona** (a fixed canned-completion
backend — the integrated `MockLLMAgent` pattern), so the pinned baseline
identities are content-addressed and CI-stable WITHOUT any live call. The **ONE
governed live Ollama invocation is the single evidence pack** run after
integration (the digest verified against the preregistration). Stop after it.

## 10. Threat model + adversarial vectors

| # | Vector | Refusal / invariant |
|---|---|---|
| 1 | Privileged content in the prompt | allowlist-only prompt build + leakage regression (mutating hidden state never changes the prompt) |
| 2 | Illegal / out-of-menu committed action | menu = society-legal set; parser maps to a menu id or fails to the taxonomy — no illegal commit possible |
| 3 | Silent model swap / repull | pinned-digest verification aborts before compute |
| 4 | Re-invoking the model on replay (non-determinism leaking into identity) | replay re-derives from captures only; a regression asserts replay makes no backend call |
| 5 | Failure relabeled as success | coded failure taxonomy + effective-sample accounting; a failed decision is never a success or a free action |
| 6 | Latency / wall-clock entering identity | latency excluded from every identity preimage; recorded as metadata |
| 7 | Over-claim (emergence/alignment/fidelity) | fixed claim ceiling, refusal-enforced |
| 8 | Scope creep (2nd live agent / more runs / adaptive / training) | closed to exactly one live agent + one governed pack; frozen constants |
| 9 | Society/spatial contract drift | the spatial + society evidence is byte-identical to a scripted run for the non-live decisions; all seed/spatial pins intact for the control agents |

## 11. Non-goals / exclusions (per the authorization)

No training, fine-tune, LoRA, reward, or adaptive intervention; no second live
agent; no additional live runs beyond the one governed pack; no hidden suites;
no labels (T0-B); no external spend; no persistence beyond the run directory; no
emergence/alignment/fidelity/reliability claims; no society expansion. Stop after
the first governed live evidence pack; further live-persona or adaptive work
requires a NEW owner authorization.

## 12. Compatibility

Additive only: a new live-persona actor + capture/derivation/report module
(under `coliseum/textlab/society/` or a sibling), the mock persona for tests, and
docs. No change to any integrated S0..S2D / calibration / Society Seed record,
contract, or behavior; the scripted control agents' spatial+society evidence is
byte-identical to the seed; version dispatch fails closed. The reference-profile
freeze (separate owner directive) is a distinct deliverable, not part of this
pilot.
