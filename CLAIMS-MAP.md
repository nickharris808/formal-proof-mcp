# CLAIMS-MAP — formal-proof-mcp

**Tag: CLEAN. Licence: Apache-2.0.**

This file exists so the CLEAN tag is *auditable* rather than asserted.

## The line

Every method independent in the filed set terminates in a **physical actuation** step. The two
families nearest this server recite:

> *"…recording the recomputed root value … and **refusing to admit a gate decision** in reliance
> on the evidence set."*

> *"…**admitting a subject implementation into an executing path** of a computing system, and
> binding both recorded counts into a durable record accompanying the admitted subject."*

`formal-proof-mcp` **answers questions**. It compiles a snippet, parses an axiom listing, computes
a bound, walks a graph. It admits nothing into an executing path and refuses no gate decision.

## Claims approached, and the step not performed

| Filed claim family | What it recites | What formal-proof-mcp does instead |
|---|---|---|
| Evidence-backed admission gating | maintaining an evidence set backing an admission gate, recomputing over it, and **refusing to admit a gate decision** in reliance on it | Recomputes and returns JSON. `isError` is an MCP reporting field; nothing is admitted or refused. |
| Acceptance-procedure qualification | recording false-acceptance counts and **admitting a subject implementation into an executing path** using a qualified procedure | `bound` reports what a k-of-n record supports. No subject, no executing path. |
| Deadlock-free admission | certifying acyclicity plus a decreasing rank, then **admitting or refusing an operation upon a physical resource and granting or withholding it** | `gridlock_check` certifies the graph. It does not sit at an admission point and grants nothing. |
| Certificate issuance | computing a bound, binding it into a record, and **writing attested bytes into the relying party's environment** | `cert_verify` performs the verification duals — recompute, compare — and writes nothing anywhere. |

## The distinction, stated plainly

An agent that *reads* `status: failed` and decides to stop is making that decision itself. A
deployment wired so this server's output **blocks** a release supplies the terminal step the
claims recite — and that wiring, not this package, is what practises them.

This is a property of how the tool is wired rather than of anyone's intentions, which is why it is
enforced mechanically: `oss/tools/check_measure_only.py` fails the build if a CLEAN-tagged artifact
grows an actuation path.

## Non-claims

- A `status: ok` from `lean_check` attests that the Lean compiler accepted the source. It attests
  nothing about whether the theorem says what its author intended it to say.
- An axiom audit is only as good as the `#print axioms` output handed to it. This package parses;
  it does not go and run the audit against your whole corpus.
- `unavailable` is not a soft pass and must never be counted as one.
