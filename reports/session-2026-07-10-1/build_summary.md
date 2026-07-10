# Build summary — session 2026-07-10-1 (Day 1: textlab substrate)

**Author:** Claude (Fable), builder role per the 2026-07-10 role flip (Codex = milestone reviewer).

## What got built

The Coliseum MVP's Day-1 substrate in `coliseum/textlab/`: schema (all 8 record types),
scenario loader with contamination lint, two-pass agent interface with 4 deterministic scripted
personas, the runner with deferred-consequence plumbing, the `corrupt_king` scenario + its two
control twins, a CLI entry script, and a 26-test pytest suite including the byte-identity
determinism gate.

## What works (verified)

- `python3 -m pytest tests/ -q` → **26 passed**.
- **Determinism gate PASSED:** `run_scenario.py --scenario corrupt_king --agent scripted:obedient
  --seed 42` run twice → `decisions.jsonl` byte-identical (`diff` clean). Same run_id
  (`corrupt_king.v0_province.scripted-obedient.s42.1967cfa3`) — lineage is a pure function of inputs.
- **Designed reflex/planner divergence observed:** obedient persona path is
  `execute → verify → execute`; its reflex at d2 was `execute` while its planner chose `verify`
  (logged on the DecisionNode — the flinch prerequisite works).
- **Control twin demonstrates the de-confound already:** `scripted:merciful` on `corrupt_king`
  refuses the verified-harm step (`execute → verify → refuse`) but complies fully on
  `corrupt_king_harmless` (`execute → execute → execute`). Obedience-to-harm vs obedience-to-form,
  separated by design.

## See it

```bash
make textlab-smoke
python3 scripts/run_scenario.py --scenario corrupt_king --agent scripted:defiant --seed 7
cat logs/runs/corrupt_king.v1_harbor.scripted-defiant.s7.*/decisions.jsonl | head -3
```

Docs: `docs/TEXTLAB.md`.
