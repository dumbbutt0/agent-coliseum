# Agent Coliseum

A watchable, **reproducible** sandbox for emergent social strategy in small competitive agents.
Two+ "gladiator" agents fight, learn from every win/loss, carry a persistent identity, and — given
the right (N≥3, mixed-motive) structure — develop tendencies, techniques, and rivalries you can watch.

> Design + research framing lives in the vault: `05_blueprints/agent-coliseum-emergent-multiagent.md`
> (linked to `research-roadmap-lab-engineer`). This repo is the implementation.

## The core discipline: `raw → derived → render`
The **source of truth is an append-only event log** (`logs/*.jsonl`). *Everything else* — the social
graph, the technique catalog, the Elo ladder, the live view — is **derived from those logs and
regenerable**. That's what makes results reproducible and inspectable. Never let the pretty layer
become the store. (Same pattern as the wiki's immutable-raw → `graph-local.json` → Eye.)

## Quickstart — runs TODAY, zero ML dependencies
```bash
cd ~/agent-coliseum
python scripts/smoke_match.py          # seed → a season of duels → logs → derived graph → Elo table
make graph                             # regenerate derived/ views from logs
make seeds                             # same run across 3 seeds (a reproducibility sanity check)
```
The smoke test uses **random-policy gladiators in a toy duel env** — no torch/gym needed. When you
later swap the random *body* for a trained RL policy, **none of the logging/derive/rating scaffolding
changes.** That's the point: build the reproducible substrate first, drop intelligence in after.

## Where this is headed (see the blueprint)
1. **Now:** substrate proven (this smoke test).
2. **RL body:** replace random policies with self-play PPO (`gymnasium` + `pettingzoo` +
   `stable-baselines3`). Start with `slimevolleygym`. RL here is **CPU-bound** — your 8 threads carry it.
3. **LLM mind:** per-gladiator memory/reflection/negotiation via an **API** (don't run a local LLM on
   a 2 GB GPU). The `Gladiator.memory` list is already the substrate for it.
4. **League + seasons:** Elo/TrueSkill roster, exploiters, past-selves.
5. **Paper + release:** metrics (Elo, exploitability, technique diversity, alliance/betrayal, the
   grudge test) + released code/seeds/checkpoints/logs. See `docs/REPRODUCIBILITY.md`.

## Hardware notes
- Foundations + this MVP run on the current machine (i7-6700, 8 GB→12 GB WSL) for **$0**.
- GPU-heavy bits (GPT-2 repro, big training) → **free Google Colab / Kaggle**.
- Scaled seeded runs → **rent** a cloud GPU/CPU box briefly; don't buy.
- Keep this repo on the **native WSL filesystem** (`~/`, ext4) — not `/mnt/c` — for fast training I/O.

## Layout
```
coliseum/          the package
  seeding.py         deterministic seeding (reproducibility pillar #1)
  logging_substrate.py  append-only JSONL event log (the source of truth)
  envs/duel.py       a tiny, seedable combat env (placeholder for the RL env)
  agents.py          Gladiator = identity + append-only memory + policy(body)
  arena.py           run a match / a round-robin season, logging every step
  ratings.py         Elo ladder (dependency-free)
  derive_graph.py    logs → derived social graph + technique catalog
scripts/smoke_match.py   the zero-dep end-to-end proof
configs/default.yaml     the frozen experiment config
docs/REPRODUCIBILITY.md  the checklist that makes this a real experiment
logs/ derived/ checkpoints/   run outputs (regenerable; git-ignored)
```

_Add a LICENSE before publishing (MIT is a fine default for a research repo)._
