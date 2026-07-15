"""Live-persona pilot — the frozen, deterministic building blocks (OWNER SC-LP
2026-07-14). Preregistration: docs/first-gladiator/SOCIETY-LIVE-PERSONA-PILOT.md
(rev 7, integrated CHANGE_INTEGRATED 001315 @ e792a198).

This module holds the PURE, replay-re-derivable pieces of the pilot: the
dedicated numeric-menu parser (`society_numeric_menu.v1`), the ACTOR-SAFE menu
projection (§4), the frozen prompt assembler (`society_persona_prompt.v1`, §3),
and the total, first-match failure-taxonomy classifier (§5). Every function here
is deterministic and pure — no wall-clock, no model call, no privileged read —
so the derived run replays byte-identically from the captured `persona.jsonl`.

The stateful live driver, capture/replay, and departure reports build on these.
"""
from __future__ import annotations

import json
import os
import re

from coliseum.textlab._content_record import ContentRecord, ContentRecordError
from coliseum.textlab.schema import canonical_json, config_hash
from coliseum.textlab.spatial.perception import RENDERER_VERSION, render_observation_pair
from coliseum.textlab.spatial.registry import SpatialSpecRegistry
from coliseum.textlab.spatial.run import (SPATIAL_RUN_SCHEMA_VERSION,
                                          _activation_rows, _observe_chain,
                                          canonical_effect_id)
from coliseum.textlab.spatial.scenario import (SPATIAL_SCENARIO_SCHEMA_VERSION,
                                               _select_effect,
                                               _society_seed_intents,
                                               build_scenario)
from coliseum.textlab.spatial.scheduler import (ADVANCE, QUIESCENT,
                                                SCHEDULER_VERSION, SchedulerRun,
                                                _mk_transition,
                                                action_script_commitment,
                                                candidate_effects, consume,
                                                initial_scheduler_state,
                                                next_step, schedule,
                                                verify_manifest)
from coliseum.textlab.spatial.world import SPATIAL_SCHEMA_VERSION
from coliseum.textlab.society.rules import (INSTITUTION_TOKEN_STAYS_IN_A,
                                            institutional_filter)
from coliseum.textlab.society.seed import (AGENTS, CLAIM_CEILING as SEED_CLAIM_CEILING,
                                           PRIVATE_FACT, PRIVATE_FACT_HOLDER,
                                           SCENARIO as SEED_SCENARIO, _pair_key,
                                           derive_society)
from coliseum.textlab.society.run import (_society_jsonl_bytes, _terminal_token_location,
                                          assert_actor_report_schema,
                                          assert_script_rule_clean)

#: frozen version constants (§2). Any drift refuses.
PROMPT_VERSION = "society_persona_prompt.v1"
PERSONA_PARSER_VERSION = "society_numeric_menu.v1"
PERSONA_ACTOR_VERSION = "0.1"

#: the pilot's single live agent (a fixed, public, preregistered constant — §1/§2;
#: it is NOT a runtime privileged read, so it cannot leak).
LIVE_AGENT_KEY = "ada"

#: decoding cap (§2); the truncation predicate re-derives budget_exhausted.
NUM_PREDICT = 256

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)
_DIGITS_RE = re.compile(r"[0-9]+")

# ---------------------------------------------------------------------------
# 1. Parser — society_numeric_menu.v1 (§5): exact, total, pure.
# ---------------------------------------------------------------------------

def parse_numeric_menu(raw, n):
    """Return (parsed_index | None, parse_status). Strip any <think>...</think>
    block, take the FIRST maximal run of ASCII digits in the remainder as an
    integer k; 1<=k<=n selects menu item k -> ("ok"); no digits -> parse_failure;
    a well-formed integer outside 1..n -> illegal_selection. Deterministic/total —
    a non-string raw (e.g. a malformed null completion) has no digit run and maps
    to parse_failure, never a TypeError."""
    if not isinstance(raw, str):
        return None, "parse_failure"
    stripped = _THINK_RE.sub("", raw)
    m = _DIGITS_RE.search(stripped)
    if m is None:
        return None, "parse_failure"
    # TOTAL over any completion length: a digit run with more significant digits
    # than N necessarily exceeds N, so we never convert an unbounded string to int
    # (Python raises on >4300-digit int() conversions — an adversarial completion
    # must NOT escape the closed taxonomy).
    digits = m.group(0).lstrip("0") or "0"
    if len(digits) > len(str(n)):
        return None, "illegal_selection"
    k = int(digits)
    if 1 <= k <= n:
        return k, "ok"
    return None, "illegal_selection"


# ---------------------------------------------------------------------------
# 2. Actor-safe menu projection (§4): institutional_filter THEN refusal of any
#    candidate naming an id absent from ada's own S2C actor content.
# ---------------------------------------------------------------------------

def actor_permitted_ids(actor_content):
    """The set of instance ids ada may reference in an offered action — derived
    SOLELY from its S2C actor content (its body id, visible room, entity list,
    portal list, and the ids inside its visible entity locations)."""
    permitted = set()
    permitted.add(actor_content["observer_identity"])
    room = actor_content["visible_room_identity"]
    if room is not None:
        permitted.add(room)
    permitted.update(actor_content["visible_entity_identities"])
    proj = actor_content["observable_state_projection"]
    for p in proj["portals"]:
        permitted.add(p["portal_instance_id"])
        permitted.add(p["to_room_instance_id"])
    for e in proj["entities"]:
        loc = e["location"]
        for key in ("room_instance_id", "agent_body_id", "portal_instance_id",
                    "origin_room_instance_id", "destination_room_instance_id"):
            if key in loc:
                permitted.add(loc[key])
    return permitted


def _effect_referenced_ids(effect):
    """Every instance-id value an effect names (all values except the action
    discriminator; effect dicts hold only the action string + instance ids)."""
    return [v for k, v in effect.items() if k != "action"]


def actor_safe_menu(body_id, state, closure, registry, ids):
    """The offered menu (§4): candidate_effects for ``body_id`` filtered FIRST by
    the frozen institutional_filter (legality) THEN by refusal of any candidate
    whose canonical serialization names an id absent from ada's actor content
    (partial observability). Returned as concrete legal effects sorted ascending
    by canonical_effect_id — the exact activations.jsonl candidate ordering."""
    cands = candidate_effects(body_id, state, closure, registry)
    filtered, _blocked = institutional_filter(cands, state, ids)
    actor, _priv = render_observation_pair(state, body_id, closure, registry)
    permitted = actor_permitted_ids(actor.content["content"])
    kept = []
    for _kind, effs in filtered.items():
        for eff in effs:
            if all(v in permitted for v in _effect_referenced_ids(eff)):
                kept.append(eff)
    kept.sort(key=canonical_effect_id)
    return kept


# ---------------------------------------------------------------------------
# 3. Prompt assembler — society_persona_prompt.v1 (§3): exact bytes.
# ---------------------------------------------------------------------------

def _entities_block(actor_content):
    lines = [
        f"- {e['entity_id']}: {e['entity_kind']}: {canonical_json(e['location'])}"
        for e in actor_content["observable_state_projection"]["entities"]
    ]
    return "\n".join(lines) if lines else "- (none)"


def _portals_block(actor_content):
    lines = [
        f"- {p['portal_instance_id']} -> {p['to_room_instance_id']}"
        for p in actor_content["observable_state_projection"]["portals"]
    ]
    return "\n".join(lines) if lines else "- (none)"


def _menu_block(menu):
    # action_id = canonical_effect_id(effect); the canonical JSON contains braces,
    # so the prompt is assembled by concatenation, never str.format.
    return "\n".join(f"{k}. {canonical_effect_id(eff)}"
                     for k, eff in enumerate(menu, 1))


#: the frozen prompt template `society_persona_prompt.v1` (§3), the single source
#: of truth for the assembled bytes. Its config_hash is pinned as a regression.
PROMPT_TEMPLATE = (
    "You are agent {agent_key} in a simple world of rooms connected by doors.\n"
    "You can only perceive your own room. Current logical step: {logical_step}.\n"
    "You are in room {visible_room}.\n"
    "You can see these entities here (id: kind: location):\n"
    "{visible_entities_block}\n"
    "Doors leading out of your room (id -> destination room):\n"
    "{visible_portals_block}\n"
    "It is your turn. Choose EXACTLY ONE action by replying with only its number:\n"
    "{numbered_menu_block}\n"
    "Reply with only the number of your chosen action.\n"
)


def assemble_prompt(actor_content, menu):
    """Build the ONE frozen-template prompt from ada's S2C actor content + the
    actor-safe menu. Deterministic; no privileged content ever enters (§3). Built
    from PROMPT_TEMPLATE by ordered placeholder replacement — the scalar values
    (agent key, step, room id) and the serialized blocks never contain a
    placeholder token, so replacement is unambiguous."""
    room = actor_content["visible_room_identity"]
    out = PROMPT_TEMPLATE
    out = out.replace("{agent_key}", LIVE_AGENT_KEY)
    out = out.replace("{logical_step}", str(actor_content["logical_step"]))
    out = out.replace("{visible_room}", "none" if room is None else room)
    out = out.replace("{visible_entities_block}", _entities_block(actor_content))
    out = out.replace("{visible_portals_block}", _portals_block(actor_content))
    out = out.replace("{numbered_menu_block}", _menu_block(menu))
    return out


# ---------------------------------------------------------------------------
# 4. Failure-taxonomy classifier (§5): total, mutually-exclusive, first-match.
# ---------------------------------------------------------------------------

#: closed transport-outcome enum recorded on every persona.jsonl row (§6).
CALL_OUTCOMES = ("responded", "deadline_exceeded", "backend_exception")

#: code -> terminal coding when the failed decision terminates the run (§5).
#: `ok` has no terminal coding (the run advances); pass has no fallback — every
#: coded failure on a requested (activate) decision terminates.
_TERMINAL_CODING = {
    "budget_exhausted": "externally_imposed_truncation",
    "parse_failure": "parse_failure_termination",
    "illegal_selection": "invalid_action_termination",
    "deadline_exceeded": "externally_imposed_truncation",
    "backend_failure_midrun": "infrastructure_failure",
    "no_actor_safe_action": "no_actor_safe_action_termination",
    # a CONTROL desync: once ada diverges, a scripted control's next intent may be
    # illegal at the actual state (e.g. bo cannot `drop` a token ada never gave
    # it). The controlled comparison can no longer proceed as designed, so the run
    # terminates (incomplete pack, no behavioral claim) rather than fabricating a
    # control action — the conservative, honest handling of §12.1.
    "control_desync": "control_desync_termination",
}


def _truncated(completion_reason, eval_count):
    return completion_reason == "length" or (
        eval_count is not None and eval_count >= NUM_PREDICT)


def classify_decision(call_outcome, raw_completion, completion_reason,
                      eval_count, n):
    """Re-derive the exact §5 code from ONE persona.jsonl row, with no model call
    and no re-timing. Returns (code, parsed_index | None, terminal_coding | None).

    Precedence — step 0 partitions by call_outcome; a `responded` row resolves by
    first match: (1) a valid in-range parse -> ok (truncation is irrelevant, the
    parser reads only the first digit run); (2) else truncated -> budget_exhausted
    (truncation is the primary cause); (3) else parse_failure / illegal_selection.
    `ok` advances (terminal_coding None); every other code terminates the run."""
    if call_outcome not in CALL_OUTCOMES:
        raise ValueError(f"unknown call_outcome {call_outcome!r}")
    if call_outcome == "deadline_exceeded":
        return "deadline_exceeded", None, _TERMINAL_CODING["deadline_exceeded"]
    if call_outcome == "backend_exception":
        return ("backend_failure_midrun", None,
                _TERMINAL_CODING["backend_failure_midrun"])
    # responded: parser + fixed precedence
    parsed, parse_status = parse_numeric_menu(raw_completion, n)
    if parse_status == "ok":
        return "ok", parsed, None                          # step 1
    if _truncated(completion_reason, eval_count):
        return "budget_exhausted", None, _TERMINAL_CODING["budget_exhausted"]  # step 2
    return parse_status, None, _TERMINAL_CODING[parse_status]                  # step 3


def terminal_coding_for(code):
    """The terminal coding a coded failure resolves to when it terminates the
    run (§5); `ok` has none. Total over the closed code set."""
    if code == "ok":
        return None
    return _TERMINAL_CODING[code]


def _as_int(v):
    return v if isinstance(v, int) and not isinstance(v, bool) else None


def _normalize_decision(d):
    """Enforce the closed persona decision schema (§6). Returns
    (call_outcome, raw_completion, completion_reason, eval_count,
    prompt_eval_count). Any transport outcome outside the closed enum maps to
    backend_exception (a closed non-response failure). A non-response outcome
    forces EVERY response-derived field to null. A responded outcome coerces the
    response fields to their closed types (raw -> str, reason -> str|null, the
    counts -> int|null), so a malformed persona output cannot admit inconsistent
    evidence or escape the total taxonomy."""
    co = d.get("call_outcome")
    if co not in CALL_OUTCOMES:
        co = "backend_exception"
    if co in ("deadline_exceeded", "backend_exception"):
        return co, None, None, None, None
    raw = d.get("raw_completion")
    raw = raw if isinstance(raw, str) else ""
    reason = d.get("completion_reason")
    reason = reason if isinstance(reason, str) else None
    return co, raw, reason, _as_int(d.get("eval_count")), _as_int(d.get("prompt_eval_count"))


_PERSONA_ROW_KEYS = frozenset({
    "tick", "scheduler_position", "prompt_hash", "call_outcome", "model_id",
    "model_digest", "decoding", "raw_completion", "completion_reason",
    "eval_count", "prompt_eval_count", "parsed_menu_id", "parse_status"})


def _validate_persona_row(row):
    """The closed persona.jsonl row schema (§6), enforced at the replay boundary so
    a tampered/malformed source row cannot be authenticated: exactly the permitted
    keys; a non-response call_outcome REQUIRES every response-derived field null; a
    responded row requires a string raw_completion and null-or-typed metadata.
    Raises ContentRecordError on any violation."""
    if not isinstance(row, dict) or set(row) != _PERSONA_ROW_KEYS:
        raise ContentRecordError("persona row must have exactly the closed key set")
    co = row["call_outcome"]
    if co not in CALL_OUTCOMES:
        raise ContentRecordError(f"unknown call_outcome {co!r} in persona row")
    resp_fields = ("raw_completion", "completion_reason", "eval_count",
                   "prompt_eval_count", "parsed_menu_id", "parse_status")
    if co in ("deadline_exceeded", "backend_exception"):
        if any(row[k] is not None for k in resp_fields):
            raise ContentRecordError(
                f"{co} row must null every response-derived field")
        return
    # responded
    if not isinstance(row["raw_completion"], str):
        raise ContentRecordError("responded row raw_completion must be a string")
    if row["completion_reason"] is not None and \
            not isinstance(row["completion_reason"], str):
        raise ContentRecordError("responded row completion_reason must be str|null")
    for k in ("eval_count", "prompt_eval_count"):
        if row[k] is not None and (not isinstance(row[k], int) or isinstance(row[k], bool)):
            raise ContentRecordError(f"responded row {k} must be int|null")
    if row["parse_status"] not in ("ok", "parse_failure", "illegal_selection"):
        raise ContentRecordError("responded row parse_status must be a parser status")


# ===========================================================================
# STATEFUL LAYER — personas, the live driver, capture/replay, evidence binding,
# and the departure report. All deterministic given the captured persona.jsonl.
# ===========================================================================

#: frozen pilot constants (§1/§2). The live run is its own scenario name; it
#: SHARES society_seed_v1's world/genesis/institution ids (control invariant §12).
LIVE_SCENARIO = "society_live_persona_v1"
SEED = 42
TICKS = 8
DECODING = {"temperature": 0.0, "num_predict": NUM_PREDICT, "seed": 42}
DEADLINE_MS = 120000
EFFECTIVE_N_FLOOR = 6
PILOT_MODEL_ID = "huihui_ai/qwen2.5-abliterate:7b-instruct"
PILOT_MODEL_DIGEST = (
    "103482475c9b4d4032999dd5d7383478cad8b966ae6ae984d525daf7352c2219")
LIVE_CLAIM_CEILING = (
    "one pinned local persona acted for one agent under partial observation and "
    "one institutional constraint across eight deterministic ticks; the report "
    "quantifies its departure from the deterministic scripted baseline. It makes "
    "NO claim of emergence, realistic social behavior, alignment, human fidelity, "
    "or general live-model reliability, and no claim beyond this single governed "
    "run.")

#: the LiveSourceEvidenceBinding sets (§6): the spatial six + the society layer +
#: persona.jsonl. persona_latency.jsonl is EXCLUDED (non-identity). A COMPLETE
#: pack binds society.jsonl (the derived trust/tick layer exists); an INCOMPLETE
#: pack (a decision terminated before 8 ticks, so derive_society cannot run) has
#: no society.jsonl and binds the spatial six + persona.jsonl only. The two shapes
#: are the ONLY admissible key sets — fail-closed.
_SPATIAL_SIX = ("run.json", "chain.jsonl", "transitions.jsonl",
                "observations.jsonl", "activations.jsonl", "closure.json")
LIVE_EVIDENCE_FILES_COMPLETE = _SPATIAL_SIX + ("society.jsonl", "persona.jsonl")
LIVE_EVIDENCE_FILES_INCOMPLETE = _SPATIAL_SIX + ("persona.jsonl",)
#: the replay-compared set is whatever the pack actually wrote (see replay).
LIVE_EVIDENCE_FILES = LIVE_EVIDENCE_FILES_COMPLETE   # back-compat alias


# --- personas ---------------------------------------------------------------
# A persona answers ONE menu decision. The frozen interface is
#   decide(prompt, menu, context) -> decision dict with keys
#   {call_outcome, raw_completion, completion_reason, eval_count,
#    prompt_eval_count, latency_ms}.
# Only the mock/replay doubles may read `menu`/`context`; the live Ollama persona
# uses ONLY `prompt` (a leakage regression asserts the prompt is actor-safe).

class MockPersona:
    """A deterministic, canned-completion persona for CI (§9): zero live calls.
    ``plan`` is a list, one entry per ada activation IN ORDER — a raw string
    (responded, completion_reason 'stop', small eval_count) or a dict overriding
    any decision field (to exercise truncation / deadline / backend paths)."""
    model_id = "mock-persona"

    def __init__(self, plan, model_digest=None):
        self._plan = list(plan)
        self._i = 0
        self.decoding = dict(DECODING)
        self.backend_version = "mock"
        self.seed_supported = None
        self.model_digest = model_digest or (
            "mock:" + config_hash({"plan": self._plan}))

    def decide(self, prompt, menu, context):
        if self._i >= len(self._plan):
            raise ContentRecordError("mock persona plan exhausted")
        item = self._plan[self._i]
        self._i += 1
        if isinstance(item, str):
            d = {"call_outcome": "responded", "raw_completion": item,
                 "completion_reason": "stop", "eval_count": len(item),
                 "prompt_eval_count": 0, "latency_ms": 0.0}
        else:
            d = {"call_outcome": item.get("call_outcome", "responded"),
                 "raw_completion": item.get("raw_completion"),
                 "completion_reason": item.get("completion_reason"),
                 "eval_count": item.get("eval_count"),
                 "prompt_eval_count": item.get("prompt_eval_count"),
                 "latency_ms": 0.0}
        d.update(model_id=self.model_id, model_digest=self.model_digest,
                 decoding=self.decoding)
        return d


class ScriptFollowingPersona:
    """A deterministic mock that, at each ada activation, returns the menu NUMBER
    of the effect matching the next scripted-ada intent — producing the
    'mock-mimics-scripted' live run used for the faithfulness + control-invariant
    regressions. It reads only the menu (like a perfect actor), never privileged
    state. Falls back to menu item 1 if the intent is not actor-safe here."""
    model_id = "mock-script-follower"

    def __init__(self, intents, ids):
        self._intents = list(intents)
        self._ids = ids
        self._i = 0
        self.decoding = dict(DECODING)
        self.backend_version = "mock"
        self.seed_supported = None
        self.model_digest = "mock:" + config_hash(
            {"intents": [list(i) for i in intents]})

    def decide(self, prompt, menu, context):
        intent = self._intents[self._i]
        self._i += 1
        chosen = None
        for k, eff in enumerate(menu, 1):
            if _effect_matches_intent(eff, intent, self._ids):
                chosen = k
                break
        if chosen is None:                       # intent not actor-safe here
            chosen = 1
        return {"call_outcome": "responded", "raw_completion": str(chosen),
                "completion_reason": "stop", "eval_count": 1,
                "prompt_eval_count": 0, "latency_ms": 0.0,
                "model_id": self.model_id, "model_digest": self.model_digest,
                "decoding": self.decoding}


class ReplayPersona:
    """Serves the CAPTURED persona.jsonl rows back by scheduler_position — the
    replay decision source (§6). Makes ZERO backend calls; a regression asserts
    it. Also authenticates the re-assembled prompt_hash against the captured row
    so a tampered capture cannot pass replay."""
    model_id = "replay"

    def __init__(self, persona_rows):
        self._by_pos = {r["scheduler_position"]: r for r in persona_rows}
        self.backend_calls = 0
        self.model_digest = None
        self.decoding = None
        self.backend_version = None
        self.seed_supported = None

    def decide(self, prompt, menu, context):
        self.backend_calls += 1                  # NOT a backend call — a lookup
        row = self._by_pos.get(context["scheduler_position"])
        if row is None:
            raise ContentRecordError(
                f"no captured persona row at position {context['scheduler_position']}")
        if row["prompt_hash"] != config_hash(prompt):
            raise ContentRecordError(
                "replay prompt_hash != captured prompt_hash — tampered capture")
        return {"call_outcome": row["call_outcome"],
                "raw_completion": row["raw_completion"],
                "completion_reason": row["completion_reason"],
                "eval_count": row["eval_count"],
                "prompt_eval_count": row["prompt_eval_count"],
                "latency_ms": None,
                "model_id": row["model_id"], "model_digest": row["model_digest"],
                "decoding": row["decoding"]}


class BackendUnavailable(ContentRecordError):
    """Pre-run, no-evidence abort (§5 backend_unavailable): the pinned
    endpoint/model/DIGEST could not be authenticated BEFORE the first decision.
    No run identity or partial pack is minted."""


class OllamaPersona:
    """The SINGLE governed live persona (used only for the one authorized pack).
    Verifies the served digest against the preregistered pin BEFORE any decision
    (mismatch => BackendUnavailable, a pre-run abort). Each decision is exactly one
    _post at temperature 0.0 / num_predict 256 / seed 42 with the 120s deadline;
    the raw done_reason/eval_count/prompt_eval_count are captured as identity so
    budget_exhausted re-derives on replay. A timeout is deadline_exceeded; any
    other backend exception is backend_exception (§5). Uses ONLY the prompt."""
    model_id = PILOT_MODEL_ID

    def __init__(self, host=None, expected_digest=PILOT_MODEL_DIGEST):
        from coliseum.textlab.sweep import norm_digest
        from coliseum.textlab.agents import OllamaAgent
        self._agent = OllamaAgent(PILOT_MODEL_ID, host=host)
        served = getattr(self._agent, "model_digest", "")
        if getattr(self._agent, "digest_status", "missing") != "ok" or \
                norm_digest(served) != norm_digest(expected_digest):
            raise BackendUnavailable(
                f"served digest {served!r} does not authenticate against the "
                f"pinned {expected_digest!r} — pre-run abort (no evidence)")
        self.model_digest = expected_digest
        self.decoding = dict(DECODING)
        self.backend_calls = 0
        # §2: resolve backend_version + probe seed support BEFORE the regime is
        # hashed, never assumed. These are the governed run's environment facts
        # (they require live calls — legitimate at governed-run time, never during
        # the doc/source audit). The wrapped LLMAgent's verify_seeded_sampling is
        # NOT used: its deterministic (temp 0) sampling config forbids a
        # sampler_seed, so it would send no seed and always record false. Instead
        # we probe with the EXACT pilot options — temperature 0, seed 42, the same
        # options every real decision sends — so the recorded result reflects the
        # backend's behaviour UNDER seed 42, never a faked or seedless probe.
        self._agent.resolve_effective_config()
        self.backend_version = self._agent.backend_version
        self.seed_supported = self._probe_seed_support()

    def _probe_seed_support(self):
        """Send the SAME probe prompt twice with the exact frozen pilot options
        (temperature 0, seed 42); byte-equal output records seed support. Never
        captured, never latency-measured (warmup-adjacent, like the seed probe in
        the integrated backend)."""
        opts = {"temperature": 0.0, "num_predict": 8, "seed": 42}
        probe = "Reply with one word: ready"
        try:
            a = self._agent._post(probe, 8, 60, options_override=opts).get("response", "")
            b = self._agent._post(probe, 8, 60, options_override=opts).get("response", "")
        except Exception:
            return False
        return a == b

    def decide(self, prompt, menu, context):
        import socket
        import time as _time
        self.backend_calls += 1
        options = {"temperature": 0.0, "num_predict": NUM_PREDICT, "seed": 42}
        base = {"model_id": self.model_id, "model_digest": self.model_digest,
                "decoding": self.decoding}
        t0 = _time.monotonic()
        try:
            out = self._agent._post(prompt, NUM_PREDICT, DEADLINE_MS / 1000.0,
                                    options_override=options)
        except (TimeoutError, socket.timeout):
            return {"call_outcome": "deadline_exceeded", "raw_completion": None,
                    "completion_reason": None, "eval_count": None,
                    "prompt_eval_count": None,
                    "latency_ms": round((_time.monotonic() - t0) * 1000, 3), **base}
        except Exception:
            return {"call_outcome": "backend_exception", "raw_completion": None,
                    "completion_reason": None, "eval_count": None,
                    "prompt_eval_count": None,
                    "latency_ms": round((_time.monotonic() - t0) * 1000, 3), **base}
        return {"call_outcome": "responded",
                "raw_completion": out.get("response", ""),
                "completion_reason": out.get("done_reason"),
                "eval_count": out.get("eval_count"),
                "prompt_eval_count": out.get("prompt_eval_count"),
                "latency_ms": round((_time.monotonic() - t0) * 1000, 3), **base}


def _effect_matches_intent(eff, intent, ids):
    """True iff a concrete effect realizes a symbolic intent tuple (mirrors the
    scenario's _select_effect matching, but as a predicate over the menu)."""
    kind = intent[0]
    if eff.get("action") != kind:
        return False
    if kind == "move":
        return eff["to_room_instance_id"] == ids[intent[1]]
    if kind in ("take", "drop"):
        return eff["object_instance_id"] == ids[intent[1]]
    if kind == "give":
        return (eff["object_instance_id"] == ids[intent[1]]
                and eff["recipient_agent_body_id"] == ids[intent[2]])
    if kind in ("put_inside", "take_out"):
        return (eff["object_instance_id"] == ids[intent[1]]
                and eff["container_object_instance_id"] == ids[intent[2]])
    return False


# --- the live driver: step the scheduler; ada -> persona, bo/cy -> scripted --

def _drive(persona, base_sc, registry, control_intents, ada_budget=TICKS):
    """Step the S2B dispatch over a probe run; at ada's `activate` heads query the
    persona over the actor-safe menu (capturing one persona row per requested
    decision), at bo/cy heads resolve their scripted intent. Returns the resolved
    concrete-effect script + captures + terminal disposition. Deterministic given
    the persona's answers (identical for the mock; captured for the live run)."""
    genesis, closure, ids = base_sc["genesis"], base_sc["closure"], base_sc["ids"]
    wl_id, glx = base_sc["world_line"].id, base_sc["world_line_genesis"]
    key_of = {ids[k]: k for k in AGENTS}
    probe = SchedulerRun(wl_id, glx.id, action_script_commitment([]),
                         explicit_stop_position=None)
    registry.register(probe)
    cursor = initial_scheduler_state(probe, genesis, registry)
    state = genesis
    script, persona_rows, latency_rows = [], [], []
    pending = {k: list(v) for k, v in control_intents.items()}   # bo, cy only
    ada_used = 0
    terminated = None
    total = ada_budget + sum(len(v) for v in control_intents.values())
    consumed = 0
    while True:
        step = next_step(cursor, state, closure, registry)
        if step == QUIESCENT:
            break
        if step == ADVANCE:
            t = _mk_transition(state, {"action": "advance_step"}, registry)
            cursor, state = consume(cursor, state, t, closure, registry)
            continue
        body = step.content["agent_body_id"]
        key = key_of[body]
        pos = step.content["scheduler_position"]
        tick = step.content["round_index"]
        if step.content["outcome_kind"] == "pass":
            cursor, state = consume(cursor, state, None, closure, registry)
            continue
        if key == LIVE_AGENT_KEY:
            if ada_used >= ada_budget:           # 8-tick terminal for the live head
                break
            menu = actor_safe_menu(body, state, closure, registry, ids)
            if not menu:                         # pre-call terminal (§5); no row
                terminated = {"code": "no_actor_safe_action", "tick": tick,
                              "scheduler_position": pos,
                              "terminal_coding": terminal_coding_for(
                                  "no_actor_safe_action")}
                break
            actor, _priv = render_observation_pair(state, body, closure, registry)
            prompt = assemble_prompt(actor.content["content"], menu)
            n = len(menu)
            d = persona.decide(prompt, menu, {"scheduler_position": pos, "tick": tick})
            # ENFORCE the closed decision schema BEFORE any capture (§6): a
            # non-response outcome forces every response-derived field to null; a
            # responded outcome coerces the response fields to their closed types
            # (a malformed null/non-string completion can never escape the taxonomy
            # or admit inconsistent evidence).
            co, raw, reason, ec, pec = _normalize_decision(d)
            if co == "responded":
                parsed, parse_status = parse_numeric_menu(raw, n)
                parsed_menu_id = (canonical_effect_id(menu[parsed - 1])
                                  if parse_status == "ok" else None)
            else:
                parsed, parse_status, parsed_menu_id = None, None, None
            persona_rows.append({
                "tick": tick, "scheduler_position": pos,
                "prompt_hash": config_hash(prompt),
                "call_outcome": co,
                "model_id": d["model_id"], "model_digest": d["model_digest"],
                "decoding": d["decoding"], "raw_completion": raw,
                "completion_reason": reason, "eval_count": ec,
                "prompt_eval_count": pec,
                "parsed_menu_id": parsed_menu_id, "parse_status": parse_status})
            latency_rows.append({"scheduler_position": pos,
                                 "latency_ms": d.get("latency_ms"),
                                 "wall_clock_note": "non-identity"})
            ada_used += 1
            code, _p, term = classify_decision(co, raw, reason, ec, n)
            if code == "ok":
                eff = menu[parsed - 1]
                t = _mk_transition(state, eff, registry, actor=body)
                cursor, state = consume(cursor, state, t, closure, registry)
                script.append(eff)
                consumed += 1
            else:
                terminated = {"code": code, "tick": tick,
                              "scheduler_position": pos, "terminal_coding": term}
                break
        else:                                    # bo / cy — scripted CONTROL
            if not pending.get(key):
                break                            # control intents exhausted -> terminal
            intent = pending[key].pop(0)
            cands = candidate_effects(body, state, closure, registry)
            cands, _blocked = institutional_filter(cands, state, ids)
            try:
                eff = _select_effect(cands, intent, ids)
            except ContentRecordError:
                terminated = {"code": "control_desync", "tick": tick,
                              "scheduler_position": pos, "control": key,
                              "terminal_coding": terminal_coding_for("control_desync")}
                break
            t = _mk_transition(state, eff, registry, actor=body)
            cursor, state = consume(cursor, state, t, closure, registry)
            script.append(eff)
            consumed += 1
        in_transit = any(p["location"]["tag"] == "in_transit"
                         for p in state.content["placements"])
        if consumed == total and not in_transit and ada_used >= ada_budget:
            break
    return {"script": script, "stop_position": cursor.content["scheduler_position"],
            "persona_rows": persona_rows, "latency_rows": latency_rows,
            "terminated": terminated, "complete": terminated is None}


# --- evidence write (spatial six) — mirrors execute_spatial_run's control path,
#     kept in this new module so no frozen spatial file changes (§12). A
#     faithfulness regression byte-compares a mock-mimics-scripted run's chain/
#     transitions/observations/activations/closure against a scripted baseline. --

def _write_spatial_evidence(sc, registry, scenario, seed, out_root):
    chain, transitions, manifest = schedule(
        sc["run"], sc["genesis"], list(sc["script"]), sc["closure"], registry)
    verify_manifest(manifest, sc["run"], sc["genesis"], list(sc["script"]),
                    sc["closure"], registry)
    observations = _observe_chain(chain, sc, registry)
    activations = _activation_rows(chain, transitions, sc, registry)
    run_id = f"{scenario}--seed{seed}--{manifest.id[:16]}"
    summary = {
        "spatial_run_schema_version": SPATIAL_RUN_SCHEMA_VERSION,
        "scenario_schema_version": SPATIAL_SCENARIO_SCHEMA_VERSION,
        "spatial_schema_version": SPATIAL_SCHEMA_VERSION,
        "scheduler_version": SCHEDULER_VERSION,
        "renderer_version": RENDERER_VERSION,
        "run_id": run_id, "scenario": scenario, "seed": seed,
        "world_line_id": sc["world_line"].id,
        "world_line_genesis_id": sc["world_line_genesis"].id,
        "genesis_state_id": sc["genesis"].id,
        "topology_closure_hash":
            sc["world_line_genesis"].content["topology_closure_hash"],
        "scheduler_run_id": sc["run"].id,
        "action_script_commitment": sc["run"].content["action_script_commitment"],
        "manifest_id": manifest.id, "chain_length": len(chain),
        "terminal_scheduler_state_id": chain[-1].id,
        "terminal_world_state_id": chain[-1].content["current_world_state_hash"],
        "explicit_stop_position": sc["explicit_stop_position"],
        "fork_position": sc["fork_position"], "fork_state_hash": sc["fork_state_hash"],
        "random_stream_id": sc["random_stream"].id,
        "observers": {k: sc["ids"][k] for k in sc["observers"]},
        "private_object_key": sc["private_object_key"],
        "instance_ids": sc["ids"], "observation_count": len(observations),
    }
    run_dir = os.path.join(out_root, run_id)
    os.makedirs(run_dir, exist_ok=True)
    _write_line(run_dir, "run.json", canonical_json(summary))
    _write_lines(run_dir, "chain.jsonl",
                 [canonical_json({"scheduler_state_id": c.id, "content": c.content})
                  for c in chain])
    _write_lines(run_dir, "transitions.jsonl",
                 [canonical_json({"transition_id": t.id, "content": t.content})
                  for t in transitions])
    _write_lines(run_dir, "observations.jsonl",
                 [canonical_json(r) for r in observations])
    _write_lines(run_dir, "activations.jsonl",
                 [canonical_json(r) for r in activations])
    _write_line(run_dir, "closure.json", canonical_json(sc["closure"]))
    return summary, run_dir, manifest


def _write_line(run_dir, name, line):
    with open(os.path.join(run_dir, name), "w", encoding="utf-8") as fh:
        fh.write(line + "\n")


def _write_lines(run_dir, name, lines):
    with open(os.path.join(run_dir, name), "w", encoding="utf-8") as fh:
        for line in lines:
            fh.write(line + "\n")


def _write_jsonl(run_dir, name, rows):
    _write_lines(run_dir, name, [canonical_json(r) for r in rows])


def _sha256_file(path):
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(65536), b""):
            h.update(block)
    return h.hexdigest()


# --- the live-source evidence binding (domain-separated, §6) -----------------

class LiveSourceEvidenceBinding(ContentRecord):
    """Content-addresses the live pilot's provenance anchor: the spatial six + the
    derived society layer (complete packs) + persona.jsonl (the behavioral
    capture). Domain-separated from the spatial, society, and calibration
    bindings. persona_latency.jsonl is EXCLUDED (§6). The bound `pack_kind`
    (complete|incomplete) fixes which of the two admissible key sets applies —
    fail-closed: any other key set refuses."""
    __slots__ = ()
    DOMAIN = "trs.source_evidence.live.v1"
    ID_FIELD = "source_evidence_id"

    def __init__(self, run_id, evidence_file_hashes, pack_kind):
        if not isinstance(run_id, str) or not run_id:
            raise ContentRecordError("run_id must be a non-empty string")
        expected = {"complete": set(LIVE_EVIDENCE_FILES_COMPLETE),
                    "incomplete": set(LIVE_EVIDENCE_FILES_INCOMPLETE)}.get(pack_kind)
        if expected is None:
            raise ContentRecordError("pack_kind must be 'complete' or 'incomplete'")
        if not isinstance(evidence_file_hashes, dict) or \
                set(evidence_file_hashes) != expected:
            raise ContentRecordError(
                f"evidence_file_hashes must bind exactly the {pack_kind} live "
                f"evidence files {sorted(expected)}")
        for h in evidence_file_hashes.values():
            if not isinstance(h, str) or len(h) != 64 or \
                    any(c not in "0123456789abcdef" for c in h):
                raise ContentRecordError("each hash must be 64 lowercase hex chars")
        super().__init__({"run_id": run_id, "pack_kind": pack_kind,
                          "evidence_file_hashes": dict(evidence_file_hashes)})


# --- the pilot runner + replay ----------------------------------------------

def execute_live_persona_pilot(persona, seed=SEED, out_root=None, fact=True):
    """Run the live pilot: society_seed_v1 world UNCHANGED, ada driven by
    ``persona``, bo/cy scripted CONTROLS. Writes the spatial six + persona.jsonl
    + persona_latency.jsonl, the society layer (complete runs), the live binding,
    and the live_report.json departure report. Returns a result dict."""
    if out_root is None:
        out_root = os.path.join("logs", "live-persona-runs")
    registry = SpatialSpecRegistry()
    base_sc = build_scenario(SEED_SCENARIO, registry, seed)
    intents = _society_seed_intents(fact)
    control_intents = {"bo": intents["bo"], "cy": intents["cy"]}
    drive = _drive(persona, base_sc, registry, control_intents)

    live_run = SchedulerRun(base_sc["world_line"].id,
                            base_sc["world_line_genesis"].id,
                            action_script_commitment(drive["script"]),
                            explicit_stop_position=drive["stop_position"])
    registry.register(live_run)
    live_sc = dict(base_sc)
    live_sc.update({"run": live_run, "script": drive["script"],
                    "explicit_stop_position": drive["stop_position"],
                    "fork_position": None, "fork_state_hash": None})
    # the spatial run.json carries the true world/scenario identity
    # (society_seed_v1) so the substrate derivations accept it unchanged; the LIVE
    # distinction is carried by persona.jsonl + the live binding + live_report.json.
    summary, run_dir, manifest = _write_spatial_evidence(
        live_sc, registry, SEED_SCENARIO, seed, out_root)
    _write_jsonl(run_dir, "persona.jsonl", drive["persona_rows"])
    _write_jsonl(run_dir, "persona_latency.jsonl", drive["latency_rows"])

    society_manifest_id = society_run_dir_ok = None
    derived = None
    if drive["complete"]:
        assert_script_rule_clean(run_dir)
        derived = derive_society(run_dir)
        society_bytes, smanifest = _society_jsonl_bytes(
            run_dir, derived, summary["manifest_id"])
        with open(os.path.join(run_dir, "society.jsonl"), "wb") as fh:
            fh.write(society_bytes)
        society_manifest_id = smanifest.id

    pack_kind = "complete" if drive["complete"] else "incomplete"
    bound_files = (LIVE_EVIDENCE_FILES_COMPLETE if drive["complete"]
                   else LIVE_EVIDENCE_FILES_INCOMPLETE)
    binding = LiveSourceEvidenceBinding(
        run_id=summary["run_id"], pack_kind=pack_kind,
        evidence_file_hashes={n: _sha256_file(os.path.join(run_dir, n))
                              for n in bound_files})
    report = build_departure_report(run_dir, drive, derived, seed, fact, persona)
    _write_line(run_dir, "live_report.json",
                canonical_json({"id": config_hash(report), "content": report}))
    return {"run_id": summary["run_id"], "run_dir": run_dir, "spatial": summary,
            "complete": drive["complete"], "terminated": drive["terminated"],
            "society_run_manifest_id": society_manifest_id,
            "live_source_evidence_id": binding.id,
            "persona_row_count": len(drive["persona_rows"]),
            "report": report}


def replay_live_persona_pilot(run_dir, out_root=None, scratch_root=None):
    """Zero-model replay (§6): re-derive the run from the captured persona.jsonl
    (via ReplayPersona) + the scripted controls and byte-compare every bound file
    (+ society.jsonl when complete). NEVER invokes a model. Returns (ok, detail)."""
    import tempfile
    persona_rows = [json.loads(l) for l in
                    open(os.path.join(run_dir, "persona.jsonl"), encoding="utf-8")
                    if l.strip()]
    # authenticate the closed persona-row schema BEFORE re-derivation: a malformed
    # or tampered source row (a non-response outcome carrying response fields, a
    # responded row with a non-string completion) cannot be admitted to replay.
    for row in persona_rows:
        _validate_persona_row(row)
    run_json = json.loads(open(os.path.join(run_dir, "run.json"), encoding="utf-8").read())
    seed = run_json["seed"]
    scratch = scratch_root or tempfile.mkdtemp(prefix="live-replay-")
    replay = ReplayPersona(persona_rows)
    fresh = execute_live_persona_pilot(replay, seed, out_root=scratch)
    if fresh["run_id"] != run_json["run_id"]:
        return False, f"run_id differs: {fresh['run_id']} != {run_json['run_id']}"
    # the canonical pack shape comes from the RE-DERIVATION, never from what the
    # (possibly-tampered) source dir happens to contain: a complete re-derivation
    # REQUIRES society.jsonl in the source (dropping it must not silently pass as
    # an incomplete pack); an incomplete re-derivation must NOT carry society.jsonl.
    compare = list(LIVE_EVIDENCE_FILES_COMPLETE if fresh["complete"]
                   else LIVE_EVIDENCE_FILES_INCOMPLETE)
    src_has_society = os.path.isfile(os.path.join(run_dir, "society.jsonl"))
    if fresh["complete"] and not src_has_society:
        return False, ("source pack is missing society.jsonl but re-derives as a "
                       "COMPLETE pack — the bound society layer was dropped")
    if not fresh["complete"] and src_has_society:
        return False, ("source pack carries society.jsonl but re-derives as an "
                       "INCOMPLETE pack — inconsistent pack shape")
    for name in compare:
        a = open(os.path.join(run_dir, name), "rb").read()
        b = open(os.path.join(fresh["run_dir"], name), "rb").read()
        if a != b:
            return False, f"replay byte mismatch in {name}"
    return True, f"replayed byte-identically ({len(compare)} files, zero model calls)"


# --- the live-vs-scripted-baseline departure report (§7) --------------------

def _scripted_baseline_ada_effects(seed, fact):
    """The pinned scripted-baseline ada committed effects, per ada activation, from
    a fresh society_seed_v1 build (the deterministic reference trajectory)."""
    registry = SpatialSpecRegistry()
    base_sc = build_scenario(SEED_SCENARIO, registry, seed)
    intents = _society_seed_intents(fact)
    follower = ScriptFollowingPersona(intents["ada"], base_sc["ids"])
    control = {"bo": intents["bo"], "cy": intents["cy"]}
    drive = _drive(follower, base_sc, registry, control)
    # ada's committed effects, in order, tagged by tick/position
    out = []
    for r in drive["persona_rows"]:
        out.append({"tick": r["tick"], "scheduler_position": r["scheduler_position"],
                    "action_id": r["parsed_menu_id"]})
    return out, drive


def build_departure_report(run_dir, live_drive, derived, seed, fact, persona):
    """Per-tick live-vs-scripted-baseline departure (§7). Divergences at a tick
    whose baseline action was not in ada's actor-safe menu are coded
    `observability_restricted` and EXCLUDED from the behavioral-departure count;
    only divergences where both actions were actor-safe count as behavioral."""
    baseline, base_drive = _scripted_baseline_ada_effects(seed, fact)
    base_by_tick = {b["tick"]: b for b in baseline}
    live_actions = [{"tick": r["tick"], "scheduler_position": r["scheduler_position"],
                     "action_id": r["parsed_menu_id"], "call_outcome": r["call_outcome"],
                     "parse_status": r["parse_status"]}
                    for r in live_drive["persona_rows"]]

    # the actor-safe menu ids per tick in the LIVE run (to classify observability)
    live_menu_ids = _ada_menu_ids_by_tick(seed, fact, live_drive)

    per_tick = []
    behavioral = 0
    observability_restricted = 0
    first_divergence = None
    for la in live_actions:
        tick = la["tick"]
        base = base_by_tick.get(tick)
        base_id = base["action_id"] if base else None
        diverged = (la["action_id"] != base_id)
        classification = "match"
        if diverged:
            baseline_actor_safe = (base_id in live_menu_ids.get(tick, set()))
            if baseline_actor_safe:
                classification = "behavioral_departure"
                behavioral += 1
            else:
                classification = "observability_restricted"
                observability_restricted += 1
            if first_divergence is None:
                first_divergence = tick
        per_tick.append({
            "tick": tick, "scheduler_position": la["scheduler_position"],
            "live_action_id": la["action_id"], "baseline_action_id": base_id,
            "diverged": diverged, "classification": classification})

    requested = len(live_drive["persona_rows"])
    parsed_ok = sum(1 for r in live_drive["persona_rows"]
                    if r["parse_status"] == "ok")
    per_code = _per_code_counts(live_drive)
    effective_n = parsed_ok
    status = "complete"
    if not live_drive["complete"]:
        status = "incomplete"
    elif effective_n < EFFECTIVE_N_FLOOR:
        status = "underpowered"

    behavioral_claimable = (status == "complete"
                            and effective_n >= EFFECTIVE_N_FLOOR)
    trust_delta = enforcement_delta = token_terminal_delta = None
    privileged = None
    actor_safe = None
    if derived is not None:
        base_derived, base_run_dir = base_drive_society(base_drive, seed)
        trust_delta = {k: derived["trust"][k] - base_derived["trust"][k]
                       for k in derived["trust"]}
        enforcement_delta = (len(derived["enforcement"])
                             - len(base_derived["enforcement"]))
        live_tok = _terminal_token_location(run_dir)
        base_tok = _terminal_token_location(base_run_dir)
        token_terminal_delta = {"live": live_tok, "baseline": base_tok,
                                "differs": live_tok != base_tok}
        privileged = _live_privileged_report(run_dir, derived)
        actor_safe = {a: _live_actor_safe_report(run_dir, derived, a)
                      for a in AGENTS}

    # the run REGIME (§2): the actual persona's model + decoding + resolved
    # backend_version + probed seed support + the frozen prompt/parser/actor
    # versions, hashed into a regime identity. For the mock it records
    # backend_version 'mock'/seed_supported null; the governed Ollama run records
    # the authenticated live values (resolved before this hash).
    regime = {"model_id": persona.model_id, "model_digest": persona.model_digest,
              "decoding": persona.decoding,
              "backend_version": getattr(persona, "backend_version", None),
              "seed_supported": getattr(persona, "seed_supported", None),
              "prompt_version": PROMPT_VERSION,
              "parser_version": PERSONA_PARSER_VERSION,
              "persona_actor_version": PERSONA_ACTOR_VERSION}

    return {
        "live_scenario": LIVE_SCENARIO, "baseline_scenario": SEED_SCENARIO,
        "seed": seed, "fact": fact, "live_agent": LIVE_AGENT_KEY,
        "status": status, "complete": live_drive["complete"],
        "terminated": live_drive["terminated"],
        "decisions_requested": requested, "decisions_parsed_ok": parsed_ok,
        "per_code_counts": per_code, "effective_n": effective_n,
        "effective_n_floor": EFFECTIVE_N_FLOOR,
        "behavioral_departure_claimable": behavioral_claimable,
        "per_tick": per_tick,
        "first_divergence_tick": first_divergence,
        "behavioral_departure_count": behavioral,
        "observability_restricted_count": observability_restricted,
        "trust_matrix_delta": trust_delta,
        "enforcement_count_delta": enforcement_delta,
        "token_terminal_delta": token_terminal_delta,
        "privileged_report": privileged,
        "actor_safe_reports": actor_safe,
        "prompt_version": PROMPT_VERSION,
        "parser_version": PERSONA_PARSER_VERSION,
        "preregistered_model_id": PILOT_MODEL_ID,
        "preregistered_model_digest": PILOT_MODEL_DIGEST,
        "regime": regime, "regime_id": config_hash(regime),
        "claim_ceiling": LIVE_CLAIM_CEILING,
    }


def classify_from_row(row):
    """Re-derive the §5 code from a persona.jsonl row ALONE — no re-stepping, no N.
    The captured `parse_status` already fixes the parser branch at the true menu
    length, so the fixed precedence is a pure function of the stored fields."""
    co = row["call_outcome"]
    if co == "deadline_exceeded":
        return "deadline_exceeded"
    if co == "backend_exception":
        return "backend_failure_midrun"
    if row["parse_status"] == "ok":
        return "ok"
    if _truncated(row["completion_reason"], row["eval_count"]):
        return "budget_exhausted"
    return row["parse_status"]            # parse_failure or illegal_selection


def _per_code_counts(live_drive):
    counts = {}
    for r in live_drive["persona_rows"]:
        code = classify_from_row(r)
        counts[code] = counts.get(code, 0) + 1
    return counts


def base_drive_society(base_drive, seed):
    """Society derivation for the scripted-baseline live-shaped run (for deltas).
    The baseline is complete by construction, so derive_society applies."""
    import tempfile
    scratch = tempfile.mkdtemp(prefix="live-baseline-")
    registry = SpatialSpecRegistry()
    base_sc = build_scenario(SEED_SCENARIO, registry, seed)
    live_run = SchedulerRun(base_sc["world_line"].id,
                            base_sc["world_line_genesis"].id,
                            action_script_commitment(base_drive["script"]),
                            explicit_stop_position=base_drive["stop_position"])
    registry.register(live_run)
    live_sc = dict(base_sc)
    live_sc.update({"run": live_run, "script": base_drive["script"],
                    "explicit_stop_position": base_drive["stop_position"],
                    "fork_position": None, "fork_state_hash": None})
    _summary, run_dir, _m = _write_spatial_evidence(
        live_sc, registry, SEED_SCENARIO, seed, scratch)
    return derive_society(run_dir), run_dir


def _live_actor_safe_report(run_dir, derived, agent):
    """The per-agent ACTOR-SAFE report (§7, 'as in the seed'): built ONLY from
    that agent's own recorded actor observations + its own outgoing trust; the
    closed seed schema validates it (no other agent's trust, no private facts)."""
    body = derived["run_json"]["observers"][agent]
    observed, counts = [], {}
    for r in (json.loads(l) for l in
              open(os.path.join(run_dir, "observations.jsonl"), encoding="utf-8")):
        if r["observer_body_id"] != body:
            continue
        observed.append(r["scheduler_position"])
        counts[str(r["scheduler_position"])] = len(
            r["actor_content"]["content"]["visible_entity_identities"])
    report = {"agent": agent, "observed_positions": sorted(observed),
              "visible_entity_counts": counts,
              "outgoing_trust": {_pair_key(agent, j): derived["trust"][_pair_key(agent, j)]
                                 for j in AGENTS if j != agent},
              "claim_ceiling": SEED_CLAIM_CEILING}
    assert_actor_report_schema(report)
    return report


def _live_privileged_report(run_dir, derived):
    """The PRIVILEGED report (§7): the full trust matrix, enforcement trace, the
    private fact, tick-state ids, and the terminal token location — built from the
    already-derived society layer (no fork)."""
    return {"scenario": SEED_SCENARIO, "trust_matrix": derived["trust"],
            "trust_updates": derived["trust_updates"],
            "private_facts": {PRIVATE_FACT_HOLDER: {PRIVATE_FACT: True}},
            "enforcement_trace": derived["enforcement"],
            "enforcement_trace_commitment": derived["enforcement_commitment"],
            "tick_state_ids": [t.id for t in derived["tick_states"]],
            "token_terminal_location": _terminal_token_location(run_dir),
            "claim_ceiling": SEED_CLAIM_CEILING}


def _ada_menu_ids_by_tick(seed, fact, live_drive):
    """Re-derive ada's actor-safe menu ids at each of its activations in the LIVE
    run (deterministic re-step), for observability classification."""
    registry = SpatialSpecRegistry()
    base_sc = build_scenario(SEED_SCENARIO, registry, seed)
    intents = _society_seed_intents(fact)
    control = {"bo": intents["bo"], "cy": intents["cy"]}
    replay = ReplayPersona(live_drive["persona_rows"])
    genesis, closure, ids = base_sc["genesis"], base_sc["closure"], base_sc["ids"]
    key_of = {ids[k]: k for k in AGENTS}
    probe = SchedulerRun(base_sc["world_line"].id, base_sc["world_line_genesis"].id,
                         action_script_commitment([]), explicit_stop_position=None)
    registry.register(probe)
    cursor = initial_scheduler_state(probe, genesis, registry)
    state = genesis
    pending = {k: list(v) for k, v in control.items()}
    ada_used = 0
    menu_ids = {}
    while ada_used < TICKS:
        step = next_step(cursor, state, closure, registry)
        if step == QUIESCENT:
            break
        if step == ADVANCE:
            t = _mk_transition(state, {"action": "advance_step"}, registry)
            cursor, state = consume(cursor, state, t, closure, registry)
            continue
        if step.content["outcome_kind"] == "pass":
            cursor, state = consume(cursor, state, None, closure, registry)
            continue
        body = step.content["agent_body_id"]
        key = key_of[body]
        pos = step.content["scheduler_position"]
        tick = step.content["round_index"]
        if key == LIVE_AGENT_KEY:
            menu = actor_safe_menu(body, state, closure, registry, ids)
            menu_ids[tick] = {canonical_effect_id(e) for e in menu}
            if not menu:
                break
            actor, _priv = render_observation_pair(state, body, closure, registry)
            prompt = assemble_prompt(actor.content["content"], menu)
            n = len(menu)
            d = replay.decide(prompt, menu, {"scheduler_position": pos, "tick": tick})
            code, parsed, _t = classify_decision(
                d["call_outcome"], d["raw_completion"], d["completion_reason"],
                d["eval_count"], n)
            ada_used += 1
            if code != "ok":
                break
            eff = menu[parsed - 1]
            t = _mk_transition(state, eff, registry, actor=body)
            cursor, state = consume(cursor, state, t, closure, registry)
        else:
            if not pending.get(key):
                break
            intent = pending[key].pop(0)
            cands = candidate_effects(body, state, closure, registry)
            cands, _b = institutional_filter(cands, state, ids)
            try:
                eff = _select_effect(cands, intent, ids)
            except ContentRecordError:
                break
            t = _mk_transition(state, eff, registry, actor=body)
            cursor, state = consume(cursor, state, t, closure, registry)
    return menu_ids


# --- convenience entry points + CLI -----------------------------------------

def run_governed_ollama_pack(out_root=None, host=None):
    """The SINGLE governed live invocation (§9): construct the pinned
    OllamaPersona (served digest verified against the preregistered pin; a
    mismatch raises BackendUnavailable — the pre-run, no-evidence abort) and run
    the pilot exactly ONCE. STOP after this pack; a second live run needs new
    owner authorization."""
    persona = OllamaPersona(host=host)
    return execute_live_persona_pilot(persona, SEED, out_root=out_root)


def run_mock_pilot(out_root=None, fact=True):
    """A CI-shaped mock pilot: ada follows the scripted-baseline intents via the
    deterministic ScriptFollowingPersona (zero live calls). Produces a complete,
    zero-departure evidence pack — the substrate anchor."""
    registry = SpatialSpecRegistry()
    base = build_scenario(SEED_SCENARIO, registry, SEED)
    intents = _society_seed_intents(fact)
    persona = ScriptFollowingPersona(intents["ada"], base["ids"])
    return execute_live_persona_pilot(persona, SEED, out_root=out_root, fact=fact)


def main(argv=None):
    import argparse
    p = argparse.ArgumentParser(prog="society-live-pilot")
    sub = p.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("mock", help="deterministic mock pilot (zero live calls)")
    m.add_argument("--out-root", default=None)
    g = sub.add_parser("ollama", help="the SINGLE governed live Ollama pack")
    g.add_argument("--out-root", default=None)
    g.add_argument("--host", default=None)
    r = sub.add_parser("replay", help="zero-model replay of a run dir")
    r.add_argument("run_dir")
    args = p.parse_args(argv)
    if args.cmd == "mock":
        res = run_mock_pilot(out_root=args.out_root)
        print(canonical_json({"run_id": res["run_id"], "complete": res["complete"],
                              "status": res["report"]["status"]}))
    elif args.cmd == "ollama":
        res = run_governed_ollama_pack(out_root=args.out_root, host=args.host)
        print(canonical_json({"run_id": res["run_id"], "complete": res["complete"],
                              "status": res["report"]["status"],
                              "live_source_evidence_id": res["live_source_evidence_id"]}))
    elif args.cmd == "replay":
        ok, detail = replay_live_persona_pilot(args.run_dir)
        print(canonical_json({"replay_ok": ok, "detail": detail}))
    return 0


if __name__ == "__main__":       # pragma: no cover
    raise SystemExit(main())
