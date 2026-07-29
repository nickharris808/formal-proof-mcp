# Contributing to formal-proof-mcp

## The one rule

**Never return a result that was not checked as a result that passed.**

Three statuses, kept strictly apart: `ok`, `failed`, `unavailable`. A PR that collapses
`unavailable` into either of the others will be declined — that collapse is the entire failure
mode this server exists to prevent. If a toolchain is missing, a dependency is absent, or an input
is empty, say so; do not return an empty success.

The corollary: **a check that cannot check anything must FAIL.** `axiom_audit("")` returns
`failed`, not `ok`. A coverage tool that passes quietly on empty input is how a whole corpus goes
unaudited while CI stays green.

## The second rule

**This server reports. It never gates.** A PR that makes it block a deploy, withhold an artifact,
or gate an operation changes the artifact's licence classification — see
[`CLAIMS-MAP.md`](CLAIMS-MAP.md). CI enforces this via `check_measure_only.py`.

## Adding a tool

1. Add it to `tools.py` returning a dict with an explicit `status`.
2. Register it in `TOOLS` with a real `inputSchema` — an agent picks tools by their schema, so a
   vague one is a broken one.
3. Route it in `dispatch()`. Unknown tools must fail loudly and list the real ones.
4. Add a positive control to `selftest()` and both cases to the test suite: the defect present and
   the defect absent. One without the other proves nothing.
5. If it delegates to a sibling package, import it **inside** the function and return
   `_unavailable(...)` on `ImportError`. Never let a missing dependency become a silent pass.

## Keep the dependency count at zero

MCP is JSON-RPC 2.0 over stdio. The transport is one short, auditable file, and that is deliberate
for a tool whose whole value is that its answers can be trusted. Do not add an SDK.

## Tests

```bash
pip install -e ".[dev]"
python -m pytest -q            # 34 tests
formal-proof-mcp --selftest    # positive controls, no agent required
```
