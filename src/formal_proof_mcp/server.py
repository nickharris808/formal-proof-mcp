"""formal_proof_mcp.server — a Model Context Protocol server over stdio, dependency-free.

WHY NO SDK. An MCP server is a JSON-RPC 2.0 loop over stdin/stdout. Implementing it directly keeps
this package installable with zero dependencies and keeps the whole transport auditable in one
short file — which matters for a tool whose entire purpose is that an agent can trust its answers.

WHAT AN AGENT GETS. Six tools, and one invariant that runs through all of them:

    a result that was not checked is never returned as a result that passed.

Every response carries `status` ∈ {ok, failed, unavailable}, and `unavailable` is kept distinct
from both. An agent that reads "no Lean toolchain installed" as "no errors found" will assert a
proof it never checked — so this server makes that specific confusion impossible to express.

Run it:  `formal-proof-mcp`   (stdio; wire it into Claude Desktop or Cursor)
Try it:  `formal-proof-mcp --selftest`
"""
from __future__ import annotations

import json
import sys
from typing import Any, Dict, List, Optional

from . import __version__
from .tools import (axiom_audit, bound, cert_verify, count_check_removal, evidence_audit,
                    gridlock_check, lean_available, lean_check, prereg_check, residency_check,
                    state_floor)

PROTOCOL_VERSION = "2024-11-05"

TOOLS: List[Dict[str, Any]] = [
    {
        "name": "lean_check",
        "description": ("Compile a Lean 4 snippet and return the compiler's verdict. On failure "
                        "the real error is returned so the agent can repair its own proof. If no "
                        "Lean toolchain is installed the result is `unavailable` — never a pass."),
        "inputSchema": {
            "type": "object",
            "properties": {"source": {"type": "string", "description": "Lean 4 source"},
                           "timeout": {"type": "integer", "default": 120}},
            "required": ["source"]},
    },
    {
        "name": "axiom_audit",
        "description": ("Audit `#print axioms` output against an allowlist. This is the check that "
                        "catches `sorryAx` — a development can compile cleanly and still be full "
                        "of holes, because Lean accepts `sorry` and exits 0."),
        "inputSchema": {
            "type": "object",
            "properties": {"output": {"type": "string",
                                      "description": "raw `#print axioms` output"},
                           "allowed": {"type": "array", "items": {"type": "string"}}},
            "required": ["output"]},
    },
    {
        "name": "bound",
        "description": ("What a k-of-n record actually supports, as an exact one-sided "
                        "Clopper-Pearson bound. 'It passed every time' is not a bound."),
        "inputSchema": {
            "type": "object",
            "properties": {"k": {"type": "integer", "description": "observed failures"},
                           "n": {"type": "integer", "description": "trials"},
                           "confidence": {"type": "number", "default": 0.95}},
            "required": ["n"]},
    },
    {
        "name": "gridlock_check",
        "description": ("Certify that a wait-for relation cannot wedge. Returns the actual cycle "
                        "when one exists. Supply ranks to also check strict decrease, which is "
                        "what bounds progress — acyclicity alone only forbids a cycle."),
        "inputSchema": {
            "type": "object",
            "properties": {"edges": {"type": "array", "description": "[[waiter, holder], ...]",
                                     "items": {"type": "array", "items": {"type": "string"}}},
                           "ranks": {"type": "object"}},
            "required": ["edges"]},
    },
    {
        "name": "cert_verify",
        "description": ("Verify a signoff-cert/v1 certificate: digests, gate consistency, and the "
                        "false-pass bound RECOMPUTED from the evidence. Requires `signoff-cert`."),
        "inputSchema": {
            "type": "object",
            "properties": {"certificate": {"type": "object"},
                           "hmac_key": {"type": "string"},
                           "allow_unauthenticated": {"type": "boolean", "default": False}},
            "required": ["certificate"]},
    },
    {
        "name": "residency_check",
        "description": ("Can a cross-tenant cache probe on this model even be interpreted? Returns "
                        "`failed` when the victim's state could not have stayed resident, because "
                        "a null from an evicted cache is not an all-clear. Requires `kvleak`."),
        "inputSchema": {
            "type": "object",
            "properties": {"model": {"type": "string"},
                           "n_prefixes": {"type": "integer", "default": 30},
                           "tokens_each": {"type": "integer", "default": 1800},
                           "kv_budget_gib": {"type": "number"}},
            "required": ["model", "kv_budget_gib"]},
    },
    {
        "name": "prereg_check",
        "description": ("Before running an experiment, check that its decision rule CAN come out "
                        "both ways. Returns UNFALSIFIABLE when the finding -- or the null -- can "
                        "never fire over the declared metric supports. Requires `preregister`."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "decision_rule": {"type": "string",
                                  "description": "e.g. `auc > 0.7 and n_probes >= 30`"},
                "metrics": {"type": "object",
                            "description": "each metric to its support: a list of values, or "
                                           "{lo, hi} (add \"type\": \"integer\" for integers)"},
            },
            "required": ["decision_rule", "metrics"],
        },
    },
    {
        "name": "state_floor",
        "description": ("How many states must a system distinguish to answer a question about "
                        "its past? An exact count over an enumerated situation space. Optionally "
                        "proves a state budget cannot meet it. Requires `floorgen`."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "variables": {"type": "object",
                              "description": "each variable to its finite domain (a list)"},
                "answers": {"type": "array",
                            "description": "rows of {when: {...}, answer: ...}"},
                "default": {"description": "answer for unmatched situations"},
                "has_default": {"type": "boolean"},
                "budget_states": {"type": "integer",
                                  "description": "if given, also test this budget for "
                                                 "impossibility"},
            },
            "required": ["variables", "answers"],
        },
    },
    {
        "name": "gate_count",
        "description": ("Exactly how many states does removing a check admit? Replaces 'we found "
                        "no escapes' with a count. Zero means the check is REDUNDANT, which is a "
                        "finding. Requires `gatecount`."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "domain": {"type": "object",
                           "description": "each variable to a list of values or {lo, hi[, step]}"},
                "policy": {"type": "string", "description": "the full policy, with the check"},
                "weakened": {"type": "string", "description": "the policy with the check removed"},
            },
            "required": ["domain", "policy", "weakened"],
        },
    },
    {
        "name": "evidence_audit",
        "description": ("Run every applicable verifier over a directory and aggregate to ONE "
                        "verdict -- the weakest leg, never the mean. Requires `evidence`."),
        "inputSchema": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "directory to audit"}},
            "required": [],
        },
    },
]


def dispatch(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """Route a tool call. Unknown tools fail loudly rather than returning an empty success."""
    if name == "lean_check":
        return lean_check(args.get("source", ""), timeout=int(args.get("timeout", 120)))
    if name == "axiom_audit":
        return axiom_audit(args.get("output", ""), args.get("allowed"))
    if name == "bound":
        return bound(int(args.get("k", 0)), int(args.get("n", 0)),
                     float(args.get("confidence", 0.95)))
    if name == "gridlock_check":
        return gridlock_check(args.get("edges", []), args.get("ranks"))
    if name == "cert_verify":
        return cert_verify(args.get("certificate", {}), hmac_key=args.get("hmac_key"),
                           allow_unauthenticated=bool(args.get("allow_unauthenticated", False)))
    if name == "residency_check":
        return residency_check(args.get("model", ""), int(args.get("n_prefixes", 30)),
                               int(args.get("tokens_each", 1800)),
                               float(args.get("kv_budget_gib", 0)))
    if name == "prereg_check":
        return prereg_check(args.get("decision_rule", ""), args.get("metrics", {}))
    if name == "state_floor":
        return state_floor(args.get("variables", {}), args.get("answers", []),
                           args.get("default"), "default" in args,
                           args.get("budget_states"))
    if name == "gate_count":
        return count_check_removal(args.get("domain", {}), args.get("policy", ""),
                          args.get("weakened", ""))
    if name == "evidence_audit":
        return evidence_audit(str(args.get("path", ".")))
    return {"status": "failed", "error": f"unknown tool {name!r}",
            "known": [t["name"] for t in TOOLS]}


def handle(request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Handle one JSON-RPC message. Returns None for notifications (which take no reply)."""
    rid = request.get("id")
    method = request.get("method")

    if method == "initialize":
        return {"jsonrpc": "2.0", "id": rid, "result": {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "formal-proof-mcp", "version": __version__}}}

    if method == "notifications/initialized":
        return None

    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": rid, "result": {"tools": TOOLS}}

    if method == "tools/call":
        params = request.get("params") or {}
        name = params.get("name", "")
        args = params.get("arguments") or {}
        try:
            result = dispatch(name, args)
        except Exception as e:                       # a crashing tool must not kill the server
            result = {"status": "failed", "error": f"{type(e).__name__}: {e}"}
        # MCP content blocks; isError marks a genuine failure so the agent does not read a
        # failed check as a successful one.
        return {"jsonrpc": "2.0", "id": rid, "result": {
            "content": [{"type": "text", "text": json.dumps(result, indent=2)}],
            "isError": result.get("status") == "failed"}}

    if method == "ping":
        return {"jsonrpc": "2.0", "id": rid, "result": {}}

    if rid is None:
        return None
    return {"jsonrpc": "2.0", "id": rid,
            "error": {"code": -32601, "message": f"method not found: {method}"}}


def serve(stdin=None, stdout=None) -> int:
    """The stdio loop. One JSON object per line, per the MCP stdio transport."""
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError as e:
            stdout.write(json.dumps({"jsonrpc": "2.0", "id": None,
                                     "error": {"code": -32700,
                                               "message": f"parse error: {e}"}}) + "\n")
            stdout.flush()
            continue
        response = handle(request)
        if response is not None:
            stdout.write(json.dumps(response) + "\n")
            stdout.flush()
    return 0


def selftest() -> int:
    """Prove each tool actually fires, without needing an agent attached."""
    checks: List[tuple] = []

    r = axiom_audit("'Foo.bar' depends on axioms: [propext, Quot.sound]")
    checks.append(("clean axioms accepted", r["status"] == "ok"))

    r = axiom_audit("'Foo.bar' depends on axioms: [propext, sorryAx]")
    checks.append(("sorryAx caught", r["status"] == "failed" and r.get("sorry_carrying")))

    r = axiom_audit("")
    checks.append(("empty audit FAILS rather than passing quietly", r["status"] == "failed"))

    r = bound(0, 250)
    checks.append(("0-of-250 bounded at ~1.2%", 0.011 < r["upper_bound"] < 0.013))

    r = gridlock_check([["a", "b"], ["b", "c"]])
    checks.append(("acyclic graph certified", r["status"] == "ok" and r["acyclic"]))

    r = gridlock_check([["a", "b"], ["b", "a"]])
    checks.append(("cycle caught with its path", r["status"] == "failed" and r.get("cycle")))

    r = gridlock_check([["a", "b"]], {"a": 1, "b": 5})
    checks.append(("non-decreasing rank caught", r["status"] == "failed"))

    r = dispatch("no_such_tool", {})
    checks.append(("unknown tool fails loudly", r["status"] == "failed"))

    r = handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    # Derived, not written down. This assertion said `== 6` and stayed at 6 while four tools were
    # added -- a hand-written count in a self-test is a self-test that stops testing.
    checks.append((f"tools/list returns all {len(TOOLS)}",
                   len(r["result"]["tools"]) == len(TOOLS)))
    advertised = {x["name"] for x in TOOLS}
    routed = {n for n in advertised if dispatch(n, {}).get("error", "").find("unknown tool") < 0}
    checks.append(("every advertised tool is routed", advertised == routed))

    r = prereg_check("argmax_flips > 0", {"argmax_flips": {"type": "integer", "lo": 0, "hi": 0}})
    checks.append(("prereg_check catches a rule that can never fire",
                   r["status"] in ("failed", "unavailable")))
    r = count_check_removal({"x": {"lo": 0, "hi": 15}}, "x < 8 and x > 2", "x < 8")
    checks.append(("gate_count counts or reports unavailable, never a bare ok",
                   r["status"] in ("failed", "unavailable")
                   or (r["status"] == "ok" and r.get("admitted_states") == 0)))
    # The "sibling package missing" path is NOT checked here: this process cannot un-import a
    # package it already has, so any check written for it would either pass vacuously or assert
    # something false. It is covered properly in the test suite, which blocks the import.
    r = state_floor({"a": [1, 2, 3]}, [{"when": {}, "answer": "same"}])
    checks.append(("state_floor reports unavailable when nothing is demanded",
                   r["status"] == "unavailable"))

    bad = 0
    for label, passed in checks:
        print(f"  {'ok  ' if passed else 'FAIL'}  {label}")
        bad += (not passed)
    print(f"\n  lean toolchain: {'present' if lean_available() else 'ABSENT — lean_check will report `unavailable`, not a pass'}")
    if bad:
        print(f"\n{bad} check(s) failed.")
        return 1
    print("\nselftest passed.")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--version" in argv:
        print(f"formal-proof-mcp {__version__}")
        return 0
    if "--selftest" in argv:
        return selftest()
    if "--list-tools" in argv:
        for t in TOOLS:
            print(f"  {t['name']:<18} {t['description'][:88]}")
        return 0
    if "--help" in argv or "-h" in argv:
        print(__doc__)
        print("  --selftest     prove each tool fires")
        print(f"  --list-tools   the {len(TOOLS)} tools this server exposes")
        print("  --version")
        print("\n  With no flags: serve MCP over stdio.")
        return 0
    return serve()


if __name__ == "__main__":
    sys.exit(main())
