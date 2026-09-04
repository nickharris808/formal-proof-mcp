# formal-proof-mcp

**Your agent says it proved the theorem. Did anything actually check?**

[![tests](https://github.com/nickharris808/formal-proof-mcp/actions/workflows/tests.yml/badge.svg)](https://github.com/nickharris808/formal-proof-mcp/actions/workflows/tests.yml)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)
[![Dependencies](https://img.shields.io/badge/dependencies-none-brightgreen.svg)](pyproject.toml)
[![MCP](https://img.shields.io/badge/MCP-2024--11--05-blueviolet.svg)](https://modelcontextprotocol.io)

Six verification tools over the Model Context Protocol, with one invariant running through all of
them:

> **A result that was not checked is never returned as a result that passed.**

**Not yet on PyPI.** The command below is the one that works today. It installs from this repository, pinned to a tag.

```bash
pip install "git+https://github.com/nickharris808/formal-proof-mcp@v0.1.0"
```

`pip install formal-proof-mcp` is the intended command once the name is published. **It 404s today**, which is why it is not the first step above. The tag is pinned rather than `@main` so a reader installs the exact code this README documents.

## Why this exists

Coding agents are fluent about correctness. They will tell you a proof went through, a bound holds,
a graph is deadlock-free — and the failure mode is not that they lie, it is that **nothing on the
other end ever ran**. A missing Lean toolchain, an uninstalled dependency, an empty input: each
returns *something*, and "something" reads as success.

So every response here carries `status`, and the three values are kept strictly apart:

| status | meaning |
|---|---|
| `ok` | the check ran and passed |
| `failed` | the check ran and **failed** — with the real error attached, for the repair loop |
| `unavailable` | the check **could not run**. Explicitly not a pass. |

An agent that reads *"no Lean toolchain installed"* as *"no errors found"* will confidently assert
a proof it never checked. This server makes that confusion impossible to express.

## The check that matters most

`lake build` exits 0 on a development riddled with `sorry`. Lean accepts the placeholder, compiles
happily, and reports success. **Compiling is necessary and nowhere near sufficient** — only
`#print axioms` reveals what a theorem actually rests on:

```console
$ formal-proof-mcp --selftest
  ok    clean axioms accepted
  ok    sorryAx caught
  ok    empty audit FAILS rather than passing quietly
  ok    0-of-250 bounded at ~1.2%
  ok    acyclic graph certified
  ok    cycle caught with its path
  ok    non-decreasing rank caught
  ok    unknown tool fails loudly
  ok    tools/list returns all six

  lean toolchain: present

selftest passed.
```

Note line 3. An axiom audit over *empty input* **fails**. A coverage tool that cannot cover
anything must never pass quietly — that is how an entire corpus goes unaudited while CI stays green.

## Install

> **Not yet on PyPI.** `pip install formal-proof-mcp` is the intended install once published;
> until then install from the repository — it works exactly the same:
>
> ```
> pip install git+https://github.com/nickharris808/formal-proof-mcp@main
> ```

```bash
pip install formal-proof-mcp                 # zero dependencies
```

`cert_verify` and `residency_check` delegate to `signoff-cert` and `kvleak`. Neither is on PyPI, so
neither can be an extra: pip **ignores an undeclared extra with a warning and exits 0**, which
would leave you believing those two tools were enabled when they are not. Install them explicitly
instead, and only if you want them:

```bash
pip install "signoff-cert @ git+https://github.com/nickharris808/signoff-cert@v1.0.1"
pip install "kvleak @ git+https://github.com/nickharris808/kvleak@v0.1.0"
```

Without them the server runs fine and both tools report `unavailable` — never a pass.

## 30-second quickstart

```bash
formal-proof-mcp --selftest      # prove each tool actually fires
formal-proof-mcp --list-tools    # the ten tools
formal-proof-mcp                 # serve MCP over stdio
```

Wire it into Claude Desktop or Cursor:

```json
{
  "mcpServers": {
    "formal-proof": { "command": "formal-proof-mcp" }
  }
}
```

## The ten tools

| tool | what it answers |
|---|---|
| `lean_check` | Does this Lean 4 source compile? On failure, returns the **compiler's own error** so the agent repairs its proof instead of asserting one. |
| `axiom_audit` | What does the theorem actually rest on? Catches `sorryAx` and anything outside the allowlist. |
| `bound` | What does a k-of-n record *support*? Exact one-sided Clopper–Pearson. "It passed every time" is not a bound. |
| `gridlock_check` | Can this wait-for relation wedge? Returns the **actual cycle**, and optionally checks a strictly decreasing rank. |
| `cert_verify` | Is this `signoff-cert/v1` certificate real, with its false-pass bound **recomputed** from the evidence? |
| `residency_check` | Could a cross-tenant cache probe on this model even be *interpreted*? |

### Added in 0.2 — the rest of the portfolio

Each of these delegates to a sibling package. **If that package is not installed the result is
`unavailable`, never `ok`** — an agent reading "not installed" as "checked and fine" is the exact
failure this server exists to prevent, and a missing optional dependency is the likeliest way to
produce it. There is a test that blocks the import and asserts the status.

| tool | question | needs |
|---|---|---|
| `prereg_check` | can this experiment's decision rule come out both ways? | `preregister` |
| `state_floor` | how many states must the system distinguish? | `floorgen` |
| `gate_count` | exactly how many states does removing this check admit? | `gatecount` |
| `evidence_audit` | run every applicable verifier over a tree, aggregate to one verdict | `evidence` |

> **Not yet on PyPI.** `pip install formal-proof-mcp` is the intended install once published;
> until then install from the repository — it works exactly the same:
>
> ```
> pip install git+https://github.com/nickharris808/formal-proof-mcp@main
> ```

```bash
pip install "formal-proof-mcp[portfolio]"     # the server plus evidence-runner
```

`evidence-runner` is the one of these four that is on PyPI, so it is the only one an extra can
honestly promise. The other three install from a pinned tag:

```bash
pip install "preregister @ git+https://github.com/nickharris808/preregister@v0.1.0"
pip install "floorgen    @ git+https://github.com/nickharris808/floorgen@v0.1.0"
pip install "gatecount   @ git+https://github.com/nickharris808/gatecount@v0.1.0"
```

**`prereg_check` is the one to reach for first.** An agent about to run an experiment can be told,
before it burns a GPU hour, that its rule cannot fail:

```json
{"decision_rule": "argmax_flips > 0",
 "metrics": {"argmax_flips": {"type": "integer", "lo": 0, "hi": 0}}}
```
```json
{"status": "failed", "verdict": "UNFALSIFIABLE",
 "explanation": "THE FINDING CAN NEVER BE REPORTED. ... The run is guaranteed to return the null
                 before any data is collected."}
```

## Worked example — driving it the way a client does

Pipe JSON-RPC in, read JSON-RPC out:

```console
$ printf '%s\n' \
  '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' \
  '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"gridlock_check",
    "arguments":{"edges":[["a","b"],["b","c"],["c","a"]]}}}' \
  | formal-proof-mcp
```

```
initialize -> {'name': 'formal-proof-mcp', 'version': '0.1.0'} 2024-11-05
id=2 isError=True status=failed  wait-for cycle: a -> b -> c -> a
```

And the audit that catches an assumed theorem:

```
id=2 isError=True status=failed
  1 theorem(s) depend on sorryAx: these are ASSUMED, not proved, and the development
  still compiles
```

`isError` is how the agent learns a check *failed* rather than merely *returned*, and the cycle
comes back as a path so the answer is actionable rather than a bare boolean.

## Honest limits

- **`lean_check` needs a Lean toolchain.** Without one it returns `unavailable`, never a pass.
  Install via [elan](https://leanprover.github.io/).
- **`cert_verify` and `residency_check` delegate** to `signoff-cert` and `kvleak`. Absent, they
  report `unavailable` with the `pip install` line — they never fake a verdict.
- **The axiom allowlist is a policy choice**, not a law. `Classical.choice` is permitted by default;
  tighten it with the `allowed` argument if your development is constructive.
- **`gridlock_check` reasons about the graph you hand it.** It cannot know whether that graph
  faithfully models your system, which is the part only you can supply.
- **No auto-repair loop is included.** The server returns the compiler error; the *retry* is the
  agent's to run. An earlier draft of this README promised a bounded repair loop, which the code
  does not implement — the error trace is what ships.
- **No SDK, by design.** MCP is JSON-RPC 2.0 over stdio; implementing it directly keeps the
  dependency count at zero and the whole transport auditable in one short file.

## The commercial edition

This server **verifies and reports**. It does not gate.

The gate corpus, the automated repair mechanisms, and the certificate-**issuing** faucet are the
licensed offering — an operator who wants a failed check to *block a deploy* is performing the
step this package deliberately does not. See [`CLAIMS-MAP.md`](CLAIMS-MAP.md) for exactly where
that line sits.

**Reading is free. Enforcing is licensed.**

## Licence

Apache-2.0 · **CLEAN** — exposes a toolchain and reports; implements no filed apparatus.

<!-- HONEST-SCOPE -->
## Honest scope — what a passing run proves, and what it does not

The two halves are inseparable. A tool that states only the first half is marketing.

**It proves:**

- whether Lean source compiles, and what axioms a theorem actually rests on (including `sorryAx`)
- whether a wait-for graph can wedge, and an exact k-of-n bound
- explicitly, when a check COULD NOT RUN — `unavailable` is never merged into `ok`

**It does NOT prove:**

- that a theorem says what its name or docstring suggests. `#print axioms` proves the dependency set is clean, never that the statement is the one you wanted
- that a passing `lake build` means anything — a development full of `sorry` compiles and exits 0
- anything when the toolchain is absent; it reports `unavailable` and stops

Full CLI reference, generated from `--help`: [`docs/CLI.md`](docs/CLI.md)
<!-- /HONEST-SCOPE -->

## Contributing

Bug reports and pull requests welcome — see [CONTRIBUTING.md](CONTRIBUTING.md).

**A false accusation is a defect of equal severity to a missed detection.** If this tool flags something correct, open an issue with the input and the verdict you expected: over-refusal trains people to bypass refusals, which destroys the tool.

Citation metadata is in [CITATION.cff](CITATION.cff).

<!-- PORTFOLIO -->
---

## The rest of the portfolio

24 artifacts, one idea: **a measurement you cannot check is a press release.** Every tool
here reports; none of them gates.

**Tools**

| | |
|---|---|
| [`abstain-bench`](https://github.com/nickharris808/abstain-bench) | how often does a verifier pass input it could not check? |
| [`evidence`](https://github.com/nickharris808/evidence) | run the whole portfolio over your repo — the weakest leg, never the mean |
| [`floorgen`](https://github.com/nickharris808/floorgen) | what must your system remember? an exact lower bound |
| [`formal-proof-mcp`](https://github.com/nickharris808/formal-proof-mcp) | a proof kernel for your coding agent ← you are here |
| [`gatecount`](https://github.com/nickharris808/gatecount) | exactly how many states does removing this check admit? |
| [`gridlock`](https://github.com/nickharris808/gridlock) | certify a wait-for relation cannot wedge |
| [`honestbench`](https://github.com/nickharris808/honestbench) | measure your CI's escape rate |
| [`kvleak`](https://github.com/nickharris808/kvleak) | cross-tenant leak scanner |
| [`kvprobe`](https://github.com/nickharris808/kvprobe) | model-substitution detector with a measured FPR |
| [`preregister`](https://github.com/nickharris808/preregister) | refuses to seal a plan whose conclusion is already fixed |
| [`proof-carrying-ci`](https://github.com/nickharris808/proof-carrying-ci) | the whole portfolio as one CI check, with SARIF |
| [`proof-to-code-drift`](https://github.com/nickharris808/proof-to-code-drift) | fail the build when the proof stops matching |
| [`sf-verify`](https://github.com/nickharris808/sf-verify) | re-derive admission decisions offline |
| [`signoff-cert`](https://github.com/nickharris808/signoff-cert) | certificates that carry their own false-pass bound |
| [`tokencount`](https://github.com/nickharris808/tokencount) | a token count both parties can recompute |

**Benchmarks** — each recomputes one of our own published numbers from its certificate

| | |
|---|---|
| [`illusion-bench`](https://github.com/nickharris808/illusion-bench) | how many broken kernels does your oracle admit? |
| [`kv-reuse-econ-bench`](https://github.com/nickharris808/kv-reuse-econ-bench) | recompute our economics headline |
| [`llm-tenant-isolation-bench`](https://github.com/nickharris808/llm-tenant-isolation-bench) | recompute our isolation figures |

**Datasets**

| | |
|---|---|
| [`abstain-corpus`](https://huggingface.co/datasets/nickh007/abstain-corpus) | 32 inputs a verifier must NOT pass |
| [`kv-reuse-econ-traces`](https://huggingface.co/datasets/nickh007/kv-reuse-econ-traces) | per-workload reuse accounting + the closed form |
| [`kv-tenant-isolation-bench`](https://huggingface.co/datasets/nickh007/kv-tenant-isolation-bench) | isolation observations, uninterpretable rows included |
| [`llm-precision-fingerprints`](https://huggingface.co/datasets/nickh007/llm-precision-fingerprints) | precision-labelled logprobs with a negative control |

**Try it in a browser** — no install, no GPU

| | |
|---|---|
| [`tenant-leak-demo`](https://huggingface.co/spaces/nickh007/tenant-leak-demo) | the residency calculator |
| [`wait-for-visualiser`](https://huggingface.co/spaces/nickh007/wait-for-visualiser) | paste a wait-for graph, see the cycle |

### Documentation

Everything above, explained in one place: **<https://nickharris808.github.io/evidence-docs/>** —
the [tutorial](https://nickharris808.github.io/evidence-docs/start/tutorial/),
[what this proves and what it does not](https://nickharris808.github.io/evidence-docs/concepts/what-this-proves/),
and a [CLI reference](https://nickharris808.github.io/evidence-docs/reference/cli/) generated by
running `--help` on every published command.

### The commercial edition

Everything above is **measure-only** and Apache-2.0: it tells you what is true and never acts on
it. The **enforcement** side — binding a partition key at the admission decision, the compiled gate
corpus, and the certificate-*issuing* faucet — is covered by filed patents and licensed separately.

**Reading is free. Enforcing is licensed.**
<!-- /PORTFOLIO -->

<!-- BEGIN VERIFY-IN-TEN-MINUTES (generated by oss/tools/gen_readme_standard.py) -->

## Verify this in ten minutes

### 1. Install the version that exists today

```bash
pip install "git+https://github.com/nickharris808/formal-proof-mcp@v0.1.0"
```

*not on PyPI; the git tag is pinned so a reader installs the exact code this README documents.*

### 2. Run one command

```bash
formal-proof-mcp --selftest
```

Prints the proof kernel answering, and the axiom audit catching a claim that proves nothing.

### 3. Where the numbers come from

Numbers in this README carry paths like `results/data/...`. **Those receipts live in a private research monorepo and you cannot open them** — they are cited so you can see exactly what was measured and where, not because the link resolves. What is public, and what you can check yourself, is: this package's own tests and `--selftest`; the benchmarks, which recompute the headline numbers from published inputs; and the Hugging Face datasets, whose every row names the certificate it came from. If a number here matters to you and none of those covers it, treat it as unverified.

### 4. What a proof here does and does not buy you

**A machine-checked proof is not evidence that the thing proved means anything.** This lane's own theorem-transfer engine emits an instance describing a domain that does not exist, and the Lean kernel accepts it clean; a sibling lane reached the same conclusion from the other side with `theorem t : True := trivial`, which is axiom-clean and proves nothing. Kernel-checking tells you a derivation is sound. Whether the statement models your system is a question no kernel answers, and it is the question worth asking.

---

Version 0.1.0 in the source tree · Apache-2.0 · cite via `CITATION.cff` in this repository · this block is generated by `oss/tools/gen_readme_standard.py` from a measurement of PyPI, the git tags and this tree, and `--check` fails if anyone edits it by hand.

<!-- END VERIFY-IN-TEN-MINUTES -->
