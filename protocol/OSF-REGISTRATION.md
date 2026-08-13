# OSF Registration Package

Everything needed to register `gec-conformance v1.1.0` on OSF Registries.
Nothing here requires further drafting — the fields below are copy-paste.

---

## Decision: register now, not after Stage B

**Register now.** The thing preregistration protects is the *predictions*, and those
are already locked in the protocol text: 24 declared cases, each with a predicted
decision and a predicted failing predicate, plus the falsification table in §7.
Timestamping those before any execution is the entire point.

Stage B fixture digests are artifacts, not predictions. They record which bytes were
submitted; they do not constrain what the substrate is expected to do. Wiring the
collected session-1 parent afterward changes those digests and changes nothing about
what was predicted.

Waiting has a real cost and no benefit: every day unregistered is a day where the
predictions exist only in a private repository, which is exactly the standing a DOI is
supposed to replace.

Declare the sequence explicitly in the registration (text provided in §4 below), then
log the Stage B freeze as a dated entry under protocol §9 when the parent lands. That
is what the deviation log is for.

---

## 1. Where to register

**OSF Registries** → *New registration* → **Preregistration** template.

Not OSF Preprints — a preprint is a paper, and this is a protocol. Not
Open-Ended Registration — that template exists for work whose design is not yet fixed,
which is the opposite of what is being claimed here.

Registrations on OSF are **immutable once submitted**. There is a 48-hour withdrawal
window; after that a registration can be withdrawn but not edited, and the withdrawal
itself remains public. Read §5 before submitting.

---

## 2. Metadata

**Title**

    A Preregistered Conformance Protocol for Governed-Execution Claims,
    with SCQOS as First Subject

**Contributors**

    Billy R. Davis Jr. — Hudson Forge Technologies LLC — sole author

**Category:** Project
**License:** choose one and apply it to the repository at the same time, so the two agree
**Tags**

    conformance testing, preregistration, canonicalization, RFC 8785,
    governed execution, admission control, quantum error correction,
    reproducibility, clean-room implementation

**Subjects:** Computer Science; Physical Sciences and Mathematics

---

## 3. Description / abstract

> Systems that claim to govern execution — admitting or holding state transitions
> against declared invariants — are difficult to evaluate, because the evaluator and
> the system's authors both have an interest in the result and both can reason
> post hoc about whether a decision was made "for the right reason."
>
> This protocol removes that degree of freedom. An independently authored capability
> is executed through the substrate under a contract frozen and hashed in advance.
> Benign perturbations and deliberate violations are injected. The substrate's
> decision **and its stated reason** are compared against predictions locked before
> execution.
>
> The primary outcome is predicate-level agreement rather than decision-level: a
> system can reach the correct decision by the wrong route, and decision agreement
> cannot distinguish the two. False-positive rate on negative controls is reported
> unconditionally alongside true-positive rate, because a gate that holds on
> everything scores perfectly on violations and is worthless.
>
> The subject system is SCQOS (SC-Engineering). The governing invariant under test
> belongs to the capability, not the substrate: a minimum temporal separation between
> experimental collection sessions, drawn from a quantum error-correction protocol.
> The substrate is therefore asked to carry a rule it did not author, across
> executions it does not own. The decisive case is a matched pair separated by two
> minutes of declared time, where one member must be held and the other admitted.
>
> Two specification-boundary findings are already recorded (CANON-01, CANON-02) and
> accepted by the subject system's author. The protocol is intended to be reusable
> against any system making governed-execution claims; its value does not depend on
> the outcome of this first application.

---

## 4. Registration fields

The OSF Preregistration template asks a fixed set of questions. Answers below; the
protocol document is the normative source, and each answer points into it.

**Hypotheses**

> Six, stated in protocol §3 with falsification criteria in §7. In brief: (H1)
> continuity is carried across executions, not evaluated per-execution; (H2)
> enforcement is mediating rather than advisory; (H3) invariants I2, I4 and I7 are
> operationally distinct rather than one predicate under three names; (H4) receipts
> are independently verifiable; (H5) the gate discriminates rather than holding
> broadly; (H6) an externally authored contract is accepted without manual bridging.
>
> H4 carries a recorded interpretation limit: agreement against a named published
> standard is weak evidence, and no rebuild after the first round is clean-room in
> the original sense.

**Design plan**

> Controlled-corruption conformance test. A capability authored outside the subject
> organization is executed through the substrate under a frozen contract; each case
> perturbs exactly one property. 24 cases declared, 11 executed in phase 1, the
> remainder declared and deferred so the executed subset cannot be read as post hoc
> selection. Five cases are negative controls that must be admitted.

**Sampling plan**

> Not a sampling design. The case set is enumerated and fixed in advance; every
> declared case is reported whether or not it is executed. No case is re-run to
> obtain a different result, and all runs including infrastructure failures are
> recorded.

**Variables**

> Independent: the perturbation applied per case (temporal separation, ancestry
> resolvability, declared digest, encoding, stratification value). Dependent:
> the substrate's decision, its per-predicate results with evaluated inputs and
> evidence, the resulting receipt, and any consequence produced.

**Analysis plan**

> Primary: predicate-level agreement against locked predictions. Secondary:
> decision-level confusion matrix; false-positive rate on negative controls,
> reported unconditionally; the I2/I4/I7 co-fire and evidence matrix; a bridging
> ledger itemizing every manual intervention; byte-level agreement between the
> clean-room and subject canonicalizers. Falsification criteria are per-case and
> fixed in §7 — no aggregate score rescues a failed criterion.

**Other**

> Registered before execution and before Stage B of the freeze. Stage A of the
> freeze — capability implementation, decode table, contract, and this protocol —
> is complete, and its digests appear in FREEZE-MANIFEST.json. Stage B, the fixture
> digests, depends on a collected experimental artifact not yet wired in; those
> digests are artifacts rather than predictions and constrain no expectation stated
> here. The Stage B freeze will be logged as a dated entry under protocol §9. The
> pin table recording the subject system's build, policy version, adapter and
> receipt-schema versions is frozen immediately before first execution, per §1.

---

## 5. Before submitting — checks

Registration is irreversible after 48 hours. Confirm each:

- [ ] The repository is public and its URL appears in the registration. Protocol §10
      promises the protocol, harness, canonicalizer and verifier in the author's
      repository; a registration pointing at a private repo makes that promise
      unverifiable.
- [ ] Commit author email is real, not the placeholder. The commit *timestamps* back
      the clean-room claim in §2.2 and must survive any rewrite.
- [ ] `FREEZE-MANIFEST.json` is committed, and the `preregistration_digest` in it
      matches the document being registered. If the protocol text is edited after the
      manifest is written, re-run the freeze first — otherwise the registered
      document and the hashed one differ.
- [ ] Protocol §9 (deviations) reads `(none at registration)`.
- [ ] The license is applied in the repository and matches the one declared on OSF.
- [ ] The registration links the two findings documents, or the repository containing
      them.

---

## 6. After registration

1. Record the DOI in the protocol document header and in `FREEZE-MANIFEST.json`,
   then commit. This is the one edit that is expected after registration — it points
   the repository at the registration, not the reverse.
2. Send the DOI to SC-Engineering.
3. Wire the collected session-1 artifact into `fixtures/session-1.json`, re-run
   `python3 protocol/freeze.py --write`, and log the Stage B freeze under §9 with its
   date and the resulting `fixture_set_digest`.
4. Pin table at execution freeze, per §1 — not before.
