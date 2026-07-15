# Society Live-Persona Pilot — First Governed Result Evidence

## Disposition

This is the single governed live-persona pack authorized by the integrated
preregistration. It is an authenticated, capture-replayable **incomplete** run,
not a behavioral finding.

- run: `society_seed_v1--seed42--b63d84694594b499`
- integrated design: `e792a1981bdfd76b404a85deefcf933646901a78`
  (`CHANGE_INTEGRATED` 001315, plain `AUDIT_GO` 001314)
- integrated implementation: `06d3afab15ecbff14723338fd5418751f77a288b`
  (`CHANGE_INTEGRATED` 001341, plain `AUDIT_GO` 001340)
- live-source evidence binding:
  `7037594c102e5c19ace51a248fd25e315d3685029b4e0b385f1e41a09968c0d5`
- departure report:
  `b91a808ef43fc896edb3c2644b1bcfb8baa17931734ea8a288b2f4c7aece2e59`
- council evidence inventory:
  `3906af0c0fd56562df284690c9634c796ee048271c3ca06098814c95efca4af7`

## Observed result

The pinned `huihui_ai/qwen2.5-abliterate:7b-instruct` model, served by Ollama
0.22.0 at the preregistered digest, returned the raw completion `1` for each of
four requested decisions. All four parsed to legal actor-safe menu choices.

The live action matched the scripted baseline at tick 0. At tick 1 it selected a
different available movement, the first same-menu behavioral departure. At
ticks 2 and 3 the scripted baseline's `take` and `give` actions were unavailable
in the live agent's actor-safe menu and are therefore coded
`observability_restricted`, not behavioral departures. The scripted control
`bo` then could not drop a token it had never received, producing the
preregistered `control_desync` termination at tick 3 / scheduler position 15.

The result is consequently:

- status: `incomplete`
- decisions requested / parsed: `4 / 4`
- effective-N / preregistered floor: `4 / 6`
- behavioral-departure count: `1`
- observability-restricted count: `2`
- behavioral-departure claimable: `false`

No trust-matrix, enforcement, terminal-token, privileged-report, or actor-safe
report delta is available because the eight-tick society layer was not derived.
The absence of `society.jsonl` is the canonical incomplete-pack shape, not
missing evidence.

## Provenance and replay

The nine-file council inventory authenticates every file in the preserved run
directory, including the non-identity latency metadata and derived report. The
domain-separated `LiveSourceEvidenceBinding` authenticates exactly the seven
identity files allowed for an incomplete pack: the spatial six plus
`persona.jsonl`. `persona_latency.jsonl` is deliberately excluded from live
identity; `live_report.json` is derived evidence.

An offline replay from `persona.jsonl` and the scripted controls re-derived all
seven bound files byte-identically and made zero model/backend calls. Replay
does not establish deterministic live generation; it establishes deterministic
reconstruction from the authenticated captures.

## Claim boundary

Because the run is incomplete and effective-N is below the preregistered floor,
the fixed eight-tick claim ceiling is not asserted. This pack supports only the
bounded factual description above. It supports no claim of emergence,
realistic social behavior, alignment, human fidelity, general live-model
reliability, training readiness, or scientific generalization.

No further live-persona invocation is authorized by this evidence pack.
