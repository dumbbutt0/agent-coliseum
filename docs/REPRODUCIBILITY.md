# Reproducibility checklist

What turns this from a cool demo into an experiment other researchers can trust. Adapted from the
vault blueprint `agent-coliseum-emergent-multiagent` (and grounded in Henderson et al. 2018,
*Deep RL That Matters*).

## Pillars (build them in, don't bolt them on)
1. **Determinism** — seed env + policy init + numpy/torch (`coliseum/seeding.py`). Report results
   across **≥3–5 seeds** with error bars. Self-play is non-transitive + seed-sensitive, so cross-seed
   reporting + released checkpoints matter *more*, not less.
2. **Source-of-truth logs** — every run is an append-only JSONL event log (`logs/`). Graphs, ratings,
   and the live view are **derived** from it (`coliseum/derive_graph.py`) and regenerable. Never let a
   rendered view be the store.
3. **Frozen, versioned env** — the env *is* the experiment. Pin it; expose it via the **PettingZoo**
   API so others can drop in their own agents; consider **Melting Pot** protocols for comparable
   social metrics.
4. **Frozen config** — one YAML per experiment (`configs/`), logged with the run. Change one variable
   at a time.
5. **Baselines + ablations** — does the LLM-mind layer change behavior vs RL-only? Do per-agent
   identities beat shared weights on strategy diversity? A/B each mechanism.
6. **Release** — code + pinned deps + seeds + checkpoints + logs (W&B/TensorBoard) + a one-command
   replay from logs.

## Metrics to pre-declare (operational definitions, not vibes)
- **Skill:** Elo / TrueSkill trajectory (the maturity curve).
- **Robustness:** exploitability = best-response gap against a frozen agent.
- **Diversity:** technique diversity (entropy of the action distribution; distance between gladiators').
- **Sociality:** alliance / betrayal frequency (needs N≥3 + mixed-motive payoffs).
- **The grudge test:** does opponent-identity conditioning measurably shift play vs. an identity-hidden
  control? (The clean test of "do they form rivalries" vs. "we told a story after the fact.")

## Precedents to read
Bansal 2017 (emergent multi-agent competition) · Baker 2019 (emergent tool use) · AlphaStar League ·
Melting Pot + Leibo 2017 (social dilemmas) · Park 2023 (Generative Agents) · Wang 2023 (Voyager) ·
Henderson 2018 (Deep RL That Matters) · PettingZoo · TrueSkill.
