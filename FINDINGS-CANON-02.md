# Finding CANON-02 — the specification names no signature algorithm or key format

**protocol:** `gec-conformance v1.1.0`, hypothesis H4
**subject:** SCQOS canonicalization and receipt specifications as supplied
**status:** blocking — one of the four verification steps in contract §8.3 cannot be implemented
**severity:** medium; narrow, and closed by one paragraph

---

## The gap

Contract §8.3 defines independent verification as four steps: reconstruct the
canonical bytes, recompute the digests, **validate the signer and authority**, and
confirm the decision follows from the frozen contract.

Steps 1, 2 and 4 are implemented and tested. Step 3 cannot be, because the supplied
specification covers canonicalization and digest but stops short of signing.
`external_signature` appears in the universal packet schema as a nullable field with
no algorithm attached, and the receipt requirement names a `proof_digest`/signature
without saying what produces or checks it.

Concretely, the following are unstated:

- signature algorithm and parameters (Ed25519, ECDSA P-256, RSA-PSS, HMAC, other)
- key format and encoding (raw, JWK, PEM, DER)
- what exactly is signed — the canonical bytes of the whole receipt, or a subset
  with the signature field removed or set to a placeholder
- key identification and rotation: how a verifier resolves which key applies
- the relationship between `proof_digest` and `external_signature`

The third item is easy to underestimate. A signature over "the receipt" is
ambiguous, since the receipt contains the signature. RFC 8785 Appendix F describes
the usual convention — remove the signature property, serialize, canonicalize, then
sign — but that is a convention, not something a verifier may assume.

---

## Current handling in the clean-room verifier

Signature validation reports `UNVERIFIABLE`, not `PASS`. A receipt that clears every
other check still reports as `INCOMPLETE` rather than `VERIFIED`, and there is a test
asserting exactly that.

This is deliberate. A verifier that returns success on an unchecked signature is
worse than one that refuses: it converts a specification gap into a green result and
the gap disappears from the record. The distinction between "checked and passed" and
"could not be checked" has to survive all the way to the report.

---

## Consequence for the study

H4 asks whether the receipt is independently verifiable. As things stand the answer
is *partially* — three of four steps. That is a defensible phase 1 result if it is
reported precisely, and it will be reported precisely. But authenticity is the step
that makes the other three matter: recomputing digests over an unauthenticated
document proves internal consistency, not provenance.

Every affected phase 1 case will carry the `UNVERIFIABLE` marker on the signature
line until this is closed.

---

## What would close it

One paragraph naming the algorithm, the key format, the exact byte range signed, and
the key-resolution rule. If SC-Engineering's live signer path does not yet satisfy
its own receipt specification — a possibility already raised — then that is a
separate finding to record rather than a reason to defer this one, since the
specification can be pinned before the implementation catches up.
