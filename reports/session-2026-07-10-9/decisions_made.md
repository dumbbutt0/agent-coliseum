# Decisions made — session 2026-07-10-9

1. **Two interaction modes, hashed and never pooled** (owner ruling from the audit
   directive): independent_vignettes preserved byte-frozen as the cheap isolation mode;
   sequential_history is the long-term design. Mode + history schema/policy/template live
   inside behavioral_config (schema v2); admission refuses the other mode even in
   diagnostics; legacy evidence is labeled independent, never reinterpreted.
2. **Version-dispatched parser semantics** (implementation keystone, not in the directive):
   replay re-parses stored captures, so parser v3's new rules would have broken
   byte-identical replay of exp-1/exp-2. `parse_llm_response` dispatches on the run's
   RECORDED parser_version; v2 is frozen for legacy evidence. Verified against real
   exp-1/exp-2 runs offline.
3. **Effective think mode + backend version resolve BEFORE hashing**: the existing warmup
   call doubles as the think probe (a 400 flips think_param pre-hash), so the regime names
   what the backend actually did. The sweep's probe agent resolves the same way before
   computing resume regimes.
4. **history entries are narrative-only by allowlist** (observation policy v1): dp_id,
   action_id, action_label, outcome_narrative. No numeric state, no visibility-annotation
   system yet — that complexity is deferred to multi-act scenarios and versioned
   (OBSERVATION_POLICY_VERSION bump = new regime by construction).
5. **Terminology ruling applied everywhere**: immediate-response condition /
   deliberation-instructed condition / reflex-prompt call / planner-prompt call; withdrawn:
   remembered confession, cover maintenance, cognitive layers, temporal dissociation, true
   motives. "Flinch" survives only as a design metaphor, flagged as such in docs.
6. **Sweep-v2 demotion wording is evidence-based**: verified CONFIG DRIFT (not merely
   "at risk") — it has no stored behavioral_config, so replay identity has been
   unreconstructable since Day-5's identity change. Demoted, preserved, never deleted.
7. **Amendment banners, never rewrites**: both exp reports and wiki pages amended with
   dated audit banners; raw results and tables untouched (matching the exp-1 precedent).
