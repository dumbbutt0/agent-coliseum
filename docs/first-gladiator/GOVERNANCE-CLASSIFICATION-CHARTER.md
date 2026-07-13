# Governance Classification Charter — A/B/C/D decision authority (Rev. 3)

> **Status:** design source (doc-only). This charter SPECIFIES a governance model; it grants no new
> authority by being integrated. The A/B/C/D envelope becomes operative only when the owner ratifies the
> corresponding code-defined policy version with a single S/KEY token (a Class-D constitutional act). Until
> then the active policy is delegation v3 (Class-A structural-`source` auto; everything else → owner token).
> Integrating this document is inert, exactly as the Delegated-Authority Charter was inert until Step C.
>
> **Rev. 2** resolved the five HIGH + one MEDIUM design findings of audit `governance-charter-001`
> (AUDIT_BLOCKED 000646): a distinct hash-bound **matter_class** (F1); classification-is-not-satisfaction for
> Class B (F2); replay-vs-independent-replication (F3); enforceable preregistration + evidence-freshness (F4);
> the owner-gate contradiction (F5); and the actual claim-ladder states (F6).
>
> **Rev. 3** resolves the two remaining HIGH findings of `governance-charter-002` (AUDIT_BLOCKED 000652):
> the F4 sealed-inventory paradox (refusal now keys on **exposure/observation**, not mere creation — a
> held-out set legitimately predates preregistration provided it was sealed and never exposed until
> resolution); and the §7↔§8 sequencing contradiction (machinery is built **inert BEFORE** ratification, and
> the single owner token **activates** it — §7 now matches §8).

## 1. Purpose and the problem it fixes

Owner-directed (2026-07-12): *"'Not routine' should not mean 'owner required.'"* The v3 delegation envelope
auto-satisfies only Class-A conditions and routes **everything else** to the owner's passphrase. That makes
the owner the routine approval mechanism for work that is significant but rule-governable — scientific
acceptance, architectural choices, ambiguity resolution — none of which require the owner's subjective
judgment when a **frozen protocol** decides them on recorded evidence.

This charter replaces the binary (auto | owner) with a four-tier model in which only a small, enumerated set
of **truly owner-reserved** actions interrupt the owner. Everything else is governed automatically — Class A
by Claude, Class B by Claude under Codex audit, Class C by the **autonomous council under frozen rules**.

**Non-negotiable invariant (unchanged):** no agent may expand its own authority. This charter is enforced by
the *same* mechanisms that enforce v3 — code-defined policy versions, the owner-only monotonic amendment
walk, append-only hash-chained history, independent audit, identity binding, the commit-derived protected-path
guard, and the emergency stop. This document changes *what is auto-governable*, never *who can widen the
envelope*. Widening it remains a Class-D owner act.

## 2. The four classes

| Class | Meaning | Decision-maker | Recorded authority |
|---|---|---|---|
| **A** | Routine, bounded, reversible work | Claude, automatically | a re-validated `evaluate_delegation` pass (v3) |
| **B** | Significant but rule-governed work | Claude **+ Codex audit** | a codex terminal verdict bound to the exact integrated commit |
| **C** | Scientific or architectural judgment | the **autonomous council** under a frozen protocol | a `COUNCIL_RESOLVED` verdict meeting every frozen gate, dissent recorded |
| **D** | Truly owner-reserved action | the **owner** | a human S/KEY token |

### 2.0 The `matter_class` field (F1 — the routing primitive, distinct from `condition_classes`)

Classification of a **whole matter** is a NEW, mandatory, auditor-emitted, hash-bound field — **`matter_class`
∈ {A,B,C,D}** — carried on **every governed verdict**: source verdicts (`AUDIT_GO`, `AUDIT_GO_WITH_CONDITIONS`,
`AUDIT_BLOCKED`), result verdicts, and the new `COUNCIL_RESOLVED`. It is **separate from** v3's per-condition
`condition_classes` (which stays a 1:1 list over `conditions` and governs only the Class-A auto-satisfy path);
a plain `AUDIT_GO` has a `matter_class` even though it has no conditions. Properties:

- **Auditor authority.** Only an auditor (codex; later a second independent auditor) may emit or change
  `matter_class`; it lives in the verdict payload covered by `verdict_payload_hash`. **Claude cannot emit,
  forge, or alter it** — verdict-hash substitution fails the existing bindings.
- **A mechanical consumer.** A new **self-authenticating** policy gate
  `governance_route(root, cfg, request_id)` — it re-reads and hash-verifies the chain from root and obtains the
  request through `publish.verified_request` (bound to the publication event's pinned `request_payload_hash`),
  trusting no caller argument — reads the codex-authored, hash-bound `matter_class` from the verified chain and
  dispatches: A → `evaluate_delegation` (v3); B → the Codex build→audit lifecycle (§2.2); C → the Class-C
  evaluator (§3); D → refuse all agent authority, route to the owner token. Any unreadable/unverifiable chain
  or request fails closed to D.
- **Fail closed to D.** An **absent, malformed, or enum-invalid** `matter_class` yields **no A/B/C authority**
  — the matter is treated as D (owner). Deflation is inert: a D-touching change carrying a non-D label is
  still refused by the commit-derived protected-path guard and the reserved-capability declaration guards,
  regardless of the label.

### 2.1 Class A — routine, bounded, reversible
The v3 envelope, unchanged: structural `source` work, no new authority, no protected paths (enforced against
the audited commit's real diff), no weights/labels/external systems, within budgets, clean tree at the exact
audited commit. Claude integrates a plain `AUDIT_GO` and auto-satisfies an **all-Class-A** conditional via
`CONDITIONS_AUTO_SATISFIED`, bound to the audited commit.

### 2.2 Class B — significant but rule-governed (F2 — classification is not satisfaction)
Work whose correctness is decidable by the build→audit contract but beyond the smallest Class-A envelope
(new non-normative modules, refactors within `coliseum/textlab/*`, evidence tooling, expanded non-normative
datasets). Governed by Claude **plus a Codex audit**. Critically:

- A Class-B matter integrates **only on a clean codex `AUDIT_GO` bound to the exact integrated commit**.
  There is **no** "auto-satisfy an outstanding Class-B condition" path: **classification is not satisfaction.**
- A Class-B verdict that requires a **technical correction** is `AUDIT_BLOCKED` (or a conditional treated as
  blocking): the correction is `FIX_STARTED → new commit → independent re-audit`, and integration binds the
  **corrected** commit. Changing bytes to perform a correction **invalidates** any prior verdict binding, so a
  stale verdict can never unlock `CHANGE_INTEGRATED`, and a builder-authored "satisfaction" of a B condition
  is refused. (Only Class A keeps the hash-bound all-A `CONDITIONS_AUTO_SATISFIED` path.)
- Class B **never** silently crosses into C or D — any condition/finding an auditor classes C or D routes on.

### 2.3 Class C — scientific / architectural judgment, resolved by the autonomous council
Matters that are **not** owner-reserved but require judgment beyond a single auditor's GO — accepting or
rejecting a scientific **claim**, choosing between materially different but rule-permitted architectures,
freezing a *new* metric/label **within** the pre-registered protocol, resolving genuine ambiguity. Decided by
the council through the **frozen resolution protocol** (§3), never by the owner's subjective "yes." A matter
advances **iff every gate passes**, and otherwise stays **unresolved** (fails closed) — it is never escalated
to the owner merely for being Class C.

### 2.4 Class D — truly owner-reserved (the ONLY owner gate)
Exactly six actions, and nothing else, interrupt the owner:
1. **External publication under the owner's identity.**
2. **Expenditure beyond the authorized budget.**
3. **Irreversible destruction of evidence or infrastructure.**
4. **Legal, financial, privacy, or personal-risk acceptance.**
5. **Alteration of the project's fundamental mission.**
6. **Suspension or weakening of constitutional safety controls** (identity, append-only history, independent
   audit, protected paths, emergency stop, amendment monotonicity, THIS classification).

Ratifying this charter, and any later change to it, is **Class-D item 6** — the single unavoidable owner
interaction. **Auditor unavailability is NOT on this list** (see §5): a matter that cannot be safely resolved
for lack of quorum stays *unresolved*, it does not become an owner action.

## 3. The frozen Class-C resolution protocol

A Class-C matter is resolved **only** through frozen policy, recorded evidence, explicit dissent handling, and
an auditable verdict. The gates (code-defined, versioned, all required):

1. **Preregistration + evidence freshness (F4 — refusal keys on EXPOSURE, not creation).** Before the
   resolving evidence is examined, a hash-bound **preregistration** event records the question, the decision
   criteria, the **precommitted eligible evidence sources and metrics**, and ONE of two freshness bindings:
   - **(a) Sealed hidden inventory.** A pre-existing inventory that was **created, content-hash sealed, and
     placed under a non-exposure commitment**; its sealed identity (content hash) is recorded in the
     preregistration and its contents are revealed only at resolution. Such an inventory **MAY predate the
     preregistration** — that is exactly what a held-out set is — because what makes it valid is that it was
     **never exposed or examined** before resolution, proven by a clean **access/exposure ledger**; the
     sealed hash recorded at preregistration must match the inventory opened at resolution.
   - **(b) Post-preregistration generation.** The resolving evidence is generated fresh under a **new
     execution identity** (`execution_instance_id`) created *after* the preregistration event.
   Acceptance **refuses**: evidence that was **exposed, observed, or examined before preregistration** (mere
   prior *creation* under an unbroken seal is permitted — the ledger, not the creation timestamp, is
   authoritative); an inventory whose opened contents do not match its sealed hash, or a swapped/backfilled
   inventory; a post-hoc-selected metric; and a **previously-spent (already-revealed/consumed) held-out
   suite** — unless a frozen protocol *explicitly permits and records* the reuse. Chain order alone is
   insufficient; the binding is to the **sealed identity** or the **post-preregistration execution identity**
   plus the **access/exposure ledger**, never to append order.
2. **Evidence adequacy.** A pre-declared sample size / power for empirical claims; the enumerated options with
   pre-declared trade-off criteria for architectural choices.
3. **Reproducibility (integrity) — SEPARATE from replication (F3).** Deterministic evidence must **byte-replay**
   (`verify_run_replay`). This proves *integrity/reproducibility of one result*; it is **not** replication.
4. **Independent replication (F3).** Empirical acceptance requires **≥2 distinct citable experiments /
   evidence inventories** with independence criteria frozen by matter type — preserving the existing claim
   ladder's two-citable-experiment minimum (`registry.py`), which states a provenance link cannot substitute
   for evidence. **One result plus any number of byte replays remains unreplicated and unaccepted.**
5. **Metric validity.** A METRICS-v1-frozen metric (or a newly frozen metric that itself passed a Class-C
   freeze); no post-hoc metric selection; the leakage/held-out and §8 partition disciplines hold.
6. **Independent auditor approval.** A codex result-audit (and, when a Fable backend exists, a second
   independent auditor — §5) approves the evidence binding and reasoning; **no auditor approves its own work.**
7. **Council consensus with recorded, blocking dissent.** The required quorum concurs; any dissent is
   **recorded, never averaged, never overridden by Claude**; unreconciled dissent within the bounded
   reconciliation budget **blocks** advancement (fail closed) and is surfaced in the verdict.
8. **Auditable verdict.** A `COUNCIL_RESOLVED` event binds the preregistration, the evidence inventory, each
   auditor verdict, the consensus/dissent record, and the resolution — append-only and replayable.

### 3.1 Scientific acceptance (F6 — the real claim ladder)
The claim ladder's actual states are **speculation · observation · replicated · generalized · accepted ·
refuted · demoted** (`registry.py`; there is no "proposed" state). Acceptance automation performs **only the
transition into `accepted`**, after every gate above passes and after validating the existing ladder
(preserving the `replicated`/`generalized` prerequisites and the `refuted`/`demoted` semantics). It **invents
no new state**; any change to the ladder itself is a **separately audited, versioned migration**, not part of
acceptance automation. A claim advances to `accepted` iff gates 1–8 pass, and otherwise remains at its current
state. The owner does not approve or veto an individual claim; the owner can only change the *protocol*
(Class-D item 6).

## 4. Ambiguity is not an owner gate
Genuine ambiguity is a **Class-C matter, not a Class-D interrupt**. The system: (a) investigates; (b) proposes
the **lowest-risk, most reversible** interpretation; (c) obtains **adversarial review** (an auditor argues the
opposing interpretation); and (d) **continues** when frozen policy provides a defensible resolution, recording
the interpretation and its reversibility. Ambiguity that cannot be resolved under any frozen policy stays
**unresolved/deferred** — it escalates to the owner **only** if its resolution independently matches an
enumerated Class-D predicate, and then only for that Class-D part.

## 5. Multi-agent council, quorum & dissent (F5 — one consistent fail-closed destination)
- **Roles** are additive (only `human` is crypto-bound). Class-C resolution requires ≥1 independent auditor
  (codex today); a second independent auditor (Fable) is **scaffolded but inactive** until a Fable backend
  exists. **When a matter's frozen policy requires a quorum the active auditors cannot supply, the matter
  remains `UNRESOLVED` and the evaluator emits NO owner-required transition** — insufficient quorum defers,
  it never escalates to the owner (that would contradict the exactly-six/one-interaction rule). The only way
  such a matter reaches the owner is if it *independently* matches an enumerated Class-D predicate.
- **Dissent** is never averaged, never silently dropped, never resolved by the builder (Claude). Unreconciled
  recorded dissent **blocks** the resolution.
- **Quorum, reconciliation budget, and the auditor allowlist** are code-defined policy fields, owner-amendable
  (Class D), never agent-writable.

## 6. Threat model

| Threat | Control |
|---|---|
| **Agent self-expansion** | `matter_class` is auditor-emitted + hash-bound (Claude cannot author it); policy versions are code-defined; the pin advances only by the owner-token monotonic walk; the protected-path guard checks the audited commit's real diff. Widening = Class-D. |
| **Class inflation/deflation** | Class is codex-authored; absent/invalid/deflated → fail closed to D; a D-touching change with a non-D label is still refused by the real-diff + reserved-capability guards. |
| **Classification-as-satisfaction (F2)** | Class B integrates only on a clean verdict bound to the corrected commit; corrections are new-commit + re-audit; stale verdicts and builder-authored satisfactions fail closed. |
| **Unreplicated / p-hacked wins (F3,F4)** | Replay is integrity only; acceptance needs ≥2 independent citable experiments; preregistration binds precommitted sources/metrics + sealed inventory / post-prereg execution identity + exposure ledger; pre-seen/backfilled/post-hoc/spent-held-out evidence refused. |
| **Council capture / dissent suppression** | No self-audit; ≥1 independent auditor; recorded dissent blocks; Claude may not resolve dissent; insufficient quorum → unresolved (never owner). |
| **Mission drift / irreversibility** | Altering the mission or the safety controls, destroying evidence, external publication, and spending are Class-D. |

## 7. Mapping to existing machinery (reused vs new)
- **Reused unchanged:** the source/result build→audit lifecycle; the claim ladder
  (speculation…accepted/refuted/demoted); the evidence-manifest + `verify_run_replay` gates; METRICS-v1;
  the §8 partition + held-out disciplines; identity / append-only chain / emergency stop / checkpoint;
  the code-defined policy-version + owner-token amendment walk; v3 `condition_classes` + `evaluate_delegation`.
- **New (specified here; built as bounded, Codex-audited slices that integrate INERT *before* ratification,
  then are switched on by the single owner token — the exact sequence of §8, matching how delegation v3 was
  built inert and then activated at Step C):**
  1. a mandatory **`matter_class` ∈ {A,B,C,D}** on every governed verdict (schema + hash-binding + auditor
     authority), plus the `governance_route` policy consumer that fail-closes absent/invalid → D;
  2. a code-defined `governance_v1` policy version (class definitions, the Class-D reserved list, the Class-C
     gates, quorum + reconciliation budget) as a new `POLICY_VERSIONS[…]`;
  3. a `COUNCIL_RESOLVED` verdict event + the frozen Class-C evaluator (gates 1–8), with **preregistration,
     sealed-inventory, exposure-ledger, and dissent** events, and the **replication (≥2 citable) separated
     from replay (integrity)**;
  4. scientific-acceptance automation performing **only the `accepted` transition** on the existing claim
     ladder (no new state; ladder changes are a separate audited migration).

## 8. Ratification path (the one owner action)
1. Route this charter (Rev. 2) as a design source → Codex audit → integrate (inert design).
2. Build the machinery (§7 new items) as bounded Codex-audited slices; each integrates in-envelope but stays
   INERT.
3. The owner ratifies the `governance_v1` policy version with **one S/KEY `POLICY_AMENDED`** (Class-D item 6).
   Only this owner token makes A/B/C/D operative and moves Class-C resolution from the owner to the council.
4. Revocation/adjustment is the forward-only owner-tokened amendment (never a rollback): the ladder is
   **v3 = delegation → v4 = governance activation (delegation retained) → v5 = delegation revocation**; each is
   a monotonic forward `POLICY_AMENDED`.

## 9. Explicit non-goals
- Does **not** authorize weights/training (still gated behind the `weight_training` interpretation + M14/SC-8),
  external systems, live spending, or publication — Class D or separately gated.
- Does **not** remove any safety control; it re-routes *judgment*, not *authority to weaken controls*.
- Does **not** let Claude self-classify, resolve dissent, accept its own claims, or treat classification as
  satisfaction.
- Activation is **owner-gated**; nothing here is operative until the Class-D ratification token.
