# Governance Classification Charter — A/B/C/D decision authority

> **Status:** design source (doc-only). This charter SPECIFIES a governance model; it grants no new
> authority by being integrated. The A/B/C/D envelope becomes operative only when the owner ratifies the
> corresponding code-defined policy version with a single S/KEY token (a Class-D constitutional act). Until
> then the active policy is delegation v3 (Class-A structural-`source` auto; everything else → owner token).
> Integrating this document is inert, exactly as the Delegated-Authority Charter was inert until Step C.

## 1. Purpose and the problem it fixes

Owner-directed (2026-07-12): *"'Not routine' should not mean 'owner required.'"* The v3 delegation envelope
auto-satisfies only Class-A conditions and routes **everything else** to the owner's passphrase. That makes
the owner the routine approval mechanism for work that is significant but rule-governable — scientific
acceptance, architectural choices, ambiguity resolution — none of which actually require the owner's
subjective judgment when a **frozen protocol** can decide them on recorded evidence.

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
| **B** | Significant but rule-governed work | Claude **+ Codex audit** | a codex terminal verdict (`AUDIT_GO` / all-Class-A conditional) |
| **C** | Scientific or architectural judgment | the **autonomous council** under a frozen protocol | a `COUNCIL_RESOLVED` verdict meeting every frozen gate, with dissent recorded |
| **D** | Truly owner-reserved action | the **owner** | a human S/KEY token |

The classification of a matter is **auditor-emitted and hash-bound** (as Class-A/B/C already are in the v3
verdict `condition_classes`), extended with class `D`. Claude cannot author or forge the class; the class
travels inside the codex verdict payload covered by `verdict_payload_hash`. A **missing or ambiguous class
fails closed to the next-higher authority** (unclassified → D).

### 2.1 Class A — routine, bounded, reversible
Structural source work inside the ratified envelope (the v3 definition): no new authority, no protected paths
(enforced against the audited commit's real diff), no weights/labels/external systems, within the compute and
delegation budgets, on a clean tree at the exact audited commit. Claude integrates on a plain `AUDIT_GO`, and
auto-satisfies an all-Class-A conditional via `CONDITIONS_AUTO_SATISFIED`. **Unchanged from v3.**

### 2.2 Class B — significant but rule-governed
Work whose correctness is decidable by the existing build→audit contract but that goes beyond the smallest
Class-A envelope: e.g. new non-normative modules, registry-*consistent* additions that touch no frozen
artifact, refactors within `coliseum/textlab/*`, evidence tooling, expanded (still non-normative) datasets.
Governed by Claude **plus a Codex audit** exactly as source requests are today; a codex `AUDIT_GO` (or all-B
conditional whose corrections stay in-envelope) integrates without the owner. Class B **never** silently
crosses into C or D — any condition an auditor classes C or D routes onward.

### 2.3 Class C — scientific / architectural judgment, resolved by the autonomous council
The heart of this charter. Matters that are **not** owner-reserved but require judgment beyond a single
auditor's GO — accepting or rejecting a scientific **claim**, choosing between materially different but
rule-permitted architectures, freezing a *new* metric/label **within** the pre-registered protocol, resolving
genuine ambiguity. These are decided by the council through a **frozen resolution protocol** (§3), never by
the owner's subjective "yes." The protocol's gates are code-defined and versioned; a matter advances **iff
every gate passes**, and remains unresolved (fails closed) otherwise.

### 2.4 Class D — truly owner-reserved (the ONLY owner gate)
Exactly six actions, and nothing else, interrupt the owner:
1. **External publication under the owner's identity** (any outward-facing artifact attributed to the owner).
2. **Expenditure beyond the authorized budget** (real money past a preset ceiling).
3. **Irreversible destruction of evidence or infrastructure** (deleting irreplaceable chain/evidence/runs).
4. **Legal, financial, privacy, or personal-risk acceptance.**
5. **Alteration of the project's fundamental mission** (the Coliseum's constitutional purpose).
6. **Suspension or weakening of constitutional safety controls** (identity, append-only history, independent
   audit, protected paths, emergency stop, the amendment monotonicity, THIS classification itself).

Ratifying this charter, and any later change to it, is itself **Class D item 6** — a constitutional act
requiring the owner's token. That is the single unavoidable owner interaction this charter introduces.

## 3. The frozen Class-C resolution protocol

A Class-C matter is routed to the council and resolved **only** through frozen policy, recorded evidence,
explicit dissent handling, and an auditable verdict. The gates (code-defined, versioned, all required):

1. **Preregistration.** The question, decision criteria, and the evidence that would settle it are recorded
   **before** the resolving evidence is examined (a preregistration event, hash-bound). A matter with no prior
   preregistration cannot be resolved — only preregistered-then-later.
2. **Evidence adequacy.** For empirical claims: an adequate, pre-declared sample size / power; for
   architectural choices: the enumerated options with their pre-declared trade-off criteria.
3. **Independent replication.** The deciding result reproduces (byte-replay for deterministic evidence; an
   independent re-run for stochastic evidence) — never a single unreplicated observation.
4. **Metric validity.** The metric is METRICS-v1-frozen (or a *newly* frozen metric that itself passed a
   Class-C freeze); no post-hoc metric selection; the leakage/held-out and §8 partition disciplines hold.
5. **Independent auditor approval.** A codex result-audit (and, when a Fable backend exists, a second
   independent auditor — §5) approves the evidence binding and the reasoning; **no auditor approves its own
   work.**
6. **Council consensus with explicit dissent.** The required quorum concurs; any dissent is **recorded, not
   averaged and not overridden by Claude** — an unresolved dissent blocks advancement (fail closed) and is
   surfaced in the verdict.
7. **Auditable verdict.** A `COUNCIL_RESOLVED` event binds the preregistration, the evidence inventory, each
   auditor verdict, the consensus/dissent record, and the resolution — append-only and replayable.

**Scientific acceptance** is the canonical Class-C case: a claim advances from *proposed* to *accepted*
**automatically** iff gates 1–7 pass, and stays unaccepted otherwise. The owner's subjective approval is not a
gate; the owner's role is constitutional (they can change the *protocol* — a Class-D act — but not veto an
individual claim that the frozen protocol accepts, nor accept one it rejects).

## 4. Ambiguity is not an owner gate

Genuine ambiguity (materially different choices that would change the research meaning) is a **Class-C matter,
not a Class-D interrupt**. The system must: (a) investigate; (b) propose the **lowest-risk, most reversible**
interpretation; (c) obtain **adversarial review** (an auditor argues the opposing interpretation); and (d)
**continue** when existing frozen policy provides a defensible resolution, recording the interpretation and its
reversibility. Only ambiguity that *cannot* be resolved under any frozen policy **and** whose resolution would
implicate a Class-D action escalates to the owner — and then only for the Class-D part.

## 5. Multi-agent council & dissent

- **Roles** are additive (only `human` is crypto-bound). Class-C resolution requires ≥1 independent auditor
  (codex today); a second independent auditor (Fable) is **scaffolded but inactive** until a Fable backend
  exists, and any resolution that a single-auditor quorum cannot safely decide fails closed to the owner until
  the second auditor is provisioned. Neither auditor approves its own work.
- **Dissent** is never averaged, never silently dropped, never resolved by the builder (Claude). Recorded
  dissent that is not reconciled within the bounded reconciliation budget **blocks** the resolution.
- **Quorum, reconciliation budget, and the auditor allowlist** are code-defined policy fields, owner-amendable
  (Class D), never agent-writable.

## 6. Threat model

| Threat | Control |
|---|---|
| **Agent self-expansion** (Claude widens its own envelope) | The class is auditor-emitted + hash-bound; policy versions are code-defined; the pin advances only by the owner-token monotonic walk; the protected-path guard checks the audited commit's real diff. Widening = Class-D owner act. **Unchanged and load-bearing.** |
| **Class inflation/deflation** (mislabeling C as B, or D as C) | Class is codex-authored, not Claude's; a missing/ambiguous class fails closed upward (→ D). A D-touching change with a non-D class is refused by the protected-path / reserved-capability guards regardless of the label. |
| **Council capture** (one agent drives the verdict) | No self-audit; ≥1 independent auditor; recorded dissent blocks; quorum is code-defined. |
| **Dissent suppression** | Dissent is a first-class recorded field; unreconciled dissent fails closed; Claude may not resolve dissent. |
| **Acceptance-protocol gaming** (p-hacking, metric shopping, unreplicated wins) | Preregistration-before-evidence; frozen metrics; independent replication; leakage/§8 discipline; auditor approval — all required, all recorded. |
| **Mission drift** (incremental redefinition of purpose) | Altering the fundamental mission or these controls is Class-D item 5/6 — owner token only. |
| **Irreversibility** | Destruction of evidence/infrastructure and external publication are Class-D; the lowest-risk-reversible rule (§4) governs ambiguous cases. |

## 7. Mapping to existing machinery (what is reused vs new)

- **Reused unchanged:** the source/result build→audit lifecycle; the claim ladder (proposed→…→accepted); the
  evidence-manifest + replay gates; METRICS-v1 freeze; the §8 partition + held-out disciplines; identity /
  append-only chain / emergency stop / checkpoint anchoring; the code-defined policy-version + owner-token
  amendment walk; the v3 `condition_classes` hash-binding and `evaluate_delegation`.
- **New (specified here, to be built as bounded, Codex-audited slices AFTER ratification):**
  1. class `D` added to the auditor classification; `evaluate_delegation` extended to route B/C/D per this
     charter (fail-closed unclassified → D);
  2. a code-defined `governance_v1` policy block (the class definitions, the Class-D reserved list, the
     Class-C protocol gates, quorum + reconciliation budget) as a new `POLICY_VERSIONS[…]`;
  3. a `COUNCIL_RESOLVED` verdict event + the frozen Class-C resolution evaluator (gates 1–7), with
     preregistration and dissent events;
  4. the scientific-acceptance automation wired onto the existing claim ladder.

## 8. Ratification path (the one owner action)

1. Route **this charter** as a design source → Codex audit → integrate (inert design, plain-GO auto-integrate).
2. Build the machinery (§7 new items) as bounded Codex-audited slices; each integrates in-envelope but stays
   INERT.
3. The owner ratifies the `governance_v1` policy version with **one S/KEY `POLICY_AMENDED`** (Class-D item 6).
   Only this owner token makes the A/B/C/D envelope operative and moves Class-C resolution from the owner to
   the council.
4. Revocation/adjustment is the forward-only owner-tokened amendment (never a rollback), exactly as v3→v4.

## 9. Explicit non-goals

- This charter does **not** authorize weights/training (still gated behind the `weight_training` interpretation
  + M14/SC-8), external systems, live spending, or publication — those are Class D or remain separately gated.
- It does **not** remove any safety control; it re-routes *judgment*, not *authority to weaken controls*.
- It does **not** let Claude resolve dissent, accept its own claims, or self-classify.
- Activation is **owner-gated**; nothing here is operative until the Class-D ratification token.
