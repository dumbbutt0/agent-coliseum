# Decisions made — session 2026-07-10-3

1. **One shared parse pipeline** (`parse_llm_response`) and one prompt builder for mock and real
   agents — the mock is the real code path minus the network, so fixture tests certify the
   production path.
2. **Reflex/planner budgets live in `spec_dict()`** (hashed into lineage): changing the reflex
   budget is a config change and produces a new run lineage. Latency and host do NOT (ruling 2;
   host is infrastructure).
3. **Capture keys are `dp_id/pass/call-counter`** for real agents (exact call sequence) and
   `dp_id/pass` for fixtures (readable); replay raises `SchemaError` on a missing key rather
   than silently falling through to the backend — during replay the backend is unreachable by
   construction (tested with a backend that throws).
4. **Cold-load warmup** (`num_predict=1`, generous timeout, before the first measured call) so
   `latency_ms` measures generation behavior, not model loading. Warmup is not captured.
5. **`$OLLAMA_HOST` for the networked split** — sim on the Dell/WSL box, minds served by the
   Mac M3 over LAN (found at 10.0.0.8), exactly per the vault compute plan. Non-standard port
   handling: bare `host:port` is auto-prefixed with `http://`.
6. **`temperature: 0` always** — determinism-leaning even though live-API determinism is never
   claimed; the replay tier is the guarantee, temperature 0 just narrows drift between reruns.
7. **`state_before` now carries `dp_id`** — the LLM capture keys and future per-dp metrics need
   it; scripted bytes changed shape (same-version gates unaffected).
8. **Fallback target = first available action** — deterministic and scenario-authored (the YAML
   ordering is the author's implicit priority), rather than a random or "safest" heuristic that
   would smuggle judgment into the harness.
