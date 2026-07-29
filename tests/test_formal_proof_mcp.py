"""Test suite for formal-proof-mcp. Every test plants a defect and asserts the tool fires."""
from __future__ import annotations

import io
import json
from math import comb

import pytest

from formal_proof_mcp import (
    axiom_audit,
    bound,
    clopper_pearson_upper,
    gridlock_check,
    lean_available,
    lean_check,
)
from formal_proof_mcp.server import TOOLS, dispatch, handle, selftest, serve


# ---------------------------------------------------------------- the core invariant

def test_unavailable_is_never_ok_and_never_failed():
    """The whole point: an agent must not read 'could not check' as 'checked and fine'."""
    from formal_proof_mcp.tools import _unavailable
    r = _unavailable("a thing", "install it")
    assert r["status"] == "unavailable"
    assert r["status"] not in ("ok", "failed")
    assert "NOT a pass" in r["note"]


def test_a_missing_sibling_reports_unavailable_not_success(monkeypatch):
    import formal_proof_mcp.tools as t
    real_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __import__

    def blocked(name, *a, **k):
        if name == "signoff_cert":
            raise ImportError("blocked for the test")
        return real_import(name, *a, **k)

    monkeypatch.setattr("builtins.__import__", blocked)
    r = t.cert_verify({"schema": "signoff-cert/v1"})
    assert r["status"] == "unavailable"
    assert "pip install" in r["remedy"]


# ---------------------------------------------------------------- axiom audit

def test_clean_axioms_pass():
    r = axiom_audit("'Foo.bar' depends on axioms: [propext, Quot.sound]")
    assert r["status"] == "ok" and r["axiom_clean"] and r["n_theorems"] == 1


def test_axiom_free_theorem_is_parsed():
    r = axiom_audit("'Foo.bar' does not depend on any axioms")
    assert r["status"] == "ok"
    assert r["theorems"][0]["axioms"] == []


def test_sorry_ax_is_caught():
    """A development carrying `sorry` still COMPILES and still exits 0. Only this catches it."""
    r = axiom_audit("'Foo.bar' depends on axioms: [propext, sorryAx]")
    assert r["status"] == "failed"
    assert r["sorry_carrying"][0]["axiom"] == "sorryAx"
    assert "ASSUMED, not proved" in r["reason"]


def test_axiom_outside_the_allowlist_is_caught():
    r = axiom_audit("'Foo.bar' depends on axioms: [propext, Wildcard.axiom]",
                    allowed=["propext", "Quot.sound"])
    assert r["status"] == "failed"
    assert r["disallowed"][0]["axiom"] == "Wildcard.axiom"


def test_empty_audit_fails_rather_than_passing_quietly():
    """A coverage tool that cannot cover anything must FAIL. This is the 'check that cannot
    fail' class -- a silent pass here is how a whole corpus goes unaudited."""
    assert axiom_audit("")["status"] == "failed"
    assert axiom_audit("no axiom lines at all, just prose")["status"] == "failed"


def test_multiple_theorems_are_all_reported():
    r = axiom_audit("'A.x' depends on axioms: [propext]\n"
                    "'B.y' depends on axioms: [Quot.sound]\n"
                    "'C.z' does not depend on any axioms")
    assert r["n_theorems"] == 3 and r["status"] == "ok"


# ---------------------------------------------------------------- the bound

def test_clopper_pearson_matches_the_closed_form_at_k_zero():
    for n in (10, 100, 250, 1000):
        assert clopper_pearson_upper(0, n, 0.95) == pytest.approx(1 - 0.05 ** (1.0 / n), abs=1e-12)


@pytest.mark.parametrize("k,n", [(0, 100), (1, 100), (5, 100), (3, 250)])
def test_clopper_pearson_inverts_the_binomial_cdf(k, n):
    """Guards the continued-fraction branch: omitting the argument swap past the crossover
    gives a plausible but WRONG number, which is worse than an error."""
    p = clopper_pearson_upper(k, n, 0.95)
    cdf = sum(comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(k + 1))
    assert cdf == pytest.approx(0.05, abs=1e-9)


def test_bound_reports_what_a_clean_record_supports():
    r = bound(0, 250)
    assert r["status"] == "ok"
    assert 0.011 < r["upper_bound"] < 0.013
    assert "NO tighter rate" in r["note"]


def test_bound_rejects_an_impossible_record():
    assert bound(10, 5)["status"] == "failed"


# ---------------------------------------------------------------- deadlock

def test_acyclic_graph_is_certified():
    r = gridlock_check([["a", "b"], ["b", "c"]])
    assert r["status"] == "ok" and r["acyclic"] and not r["wedged"]


def test_cycle_is_caught_and_the_path_is_returned():
    """Returning the actual cycle is what makes the answer actionable."""
    r = gridlock_check([["a", "b"], ["b", "c"], ["c", "a"]])
    assert r["status"] == "failed" and r["wedged"]
    assert set(r["cycle"]) >= {"a", "b", "c"}


def test_self_loop_is_a_cycle():
    assert gridlock_check([["a", "a"]])["status"] == "failed"


def test_strictly_decreasing_rank_passes():
    r = gridlock_check([["a", "b"], ["b", "c"]], {"a": 3, "b": 2, "c": 1})
    assert r["status"] == "ok" and r["rank_strictly_decreasing"]


def test_non_decreasing_rank_is_caught():
    """Acyclicity forbids a cycle; only a decreasing rank bounds progress."""
    r = gridlock_check([["a", "b"]], {"a": 1, "b": 5})
    assert r["status"] == "failed"
    assert "strictly decrease" in r["reason"]


def test_malformed_edges_fail_rather_than_crash():
    assert gridlock_check("not a list")["status"] == "failed"
    assert gridlock_check([["a"]])["status"] == "failed"


# ---------------------------------------------------------------- lean

def test_lean_check_on_empty_source_fails():
    assert lean_check("")["status"] == "failed"


def test_lean_check_status_is_honest_about_the_toolchain():
    r = lean_check("theorem t : 1 = 1 := rfl")
    if lean_available():
        assert r["status"] in ("ok", "failed")
        if r["status"] == "failed":
            assert r["error"]          # the real compiler error, for the repair loop
    else:
        assert r["status"] == "unavailable"
        assert "NOT a pass" in r["note"]


# ---------------------------------------------------------------- MCP protocol

def test_initialize_returns_protocol_and_server_info():
    r = handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert r["result"]["protocolVersion"] == "2024-11-05"
    assert r["result"]["serverInfo"]["name"] == "formal-proof-mcp"


def test_tools_list_exposes_every_tool_each_with_a_schema():
    """Derived from TOOLS, not written down.

    This assertion used to read `== 6`. Four tools were then added and it kept passing at 6 --
    no, it kept FAILING at 6, which is the lucky case. A hand-written count in a test is a test
    that either goes stale silently or breaks for the wrong reason; either way it stops checking
    what it claims. It now checks the invariant that actually matters: everything advertised has
    a usable schema.
    """
    from formal_proof_mcp.server import TOOLS
    r = handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    tools = r["result"]["tools"]
    assert len(tools) == len(TOOLS) >= 10
    assert len({t["name"] for t in tools}) == len(tools), "duplicate tool name"
    for t in tools:
        assert t["name"] and t["description"]
        assert t["inputSchema"]["type"] == "object"


def test_notification_gets_no_reply():
    """A JSON-RPC notification has no id and must not be answered."""
    assert handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None


def test_unknown_method_returns_a_jsonrpc_error():
    r = handle({"jsonrpc": "2.0", "id": 9, "method": "nope"})
    assert r["error"]["code"] == -32601


def test_tool_call_marks_a_failure_as_iserror():
    """isError is how the agent learns the check FAILED rather than merely returned."""
    r = handle({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                "params": {"name": "axiom_audit",
                           "arguments": {"output": "'X.y' depends on axioms: [sorryAx]"}}})
    assert r["result"]["isError"] is True
    payload = json.loads(r["result"]["content"][0]["text"])
    assert payload["status"] == "failed"


def test_tool_call_success_is_not_iserror():
    r = handle({"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                "params": {"name": "bound", "arguments": {"k": 0, "n": 250}}})
    assert r["result"]["isError"] is False


def test_a_crashing_tool_does_not_kill_the_server():
    r = handle({"jsonrpc": "2.0", "id": 5, "method": "tools/call",
                "params": {"name": "gridlock_check", "arguments": {"edges": [[1, 2, 3]]}}})
    assert r["result"]["isError"] is True


def test_unknown_tool_fails_loudly_and_lists_the_real_ones():
    from formal_proof_mcp.server import TOOLS
    r = dispatch("no_such_tool", {})
    assert r["status"] == "failed"
    assert set(r["known"]) == {t["name"] for t in TOOLS}


def test_every_advertised_tool_is_actually_routed():
    """An advertised tool that dispatch does not know is a schema an agent will call and get
    `unknown tool` from. The two lists must not be able to drift apart."""
    from formal_proof_mcp.server import TOOLS
    for t in TOOLS:
        r = dispatch(t["name"], {})
        assert "unknown tool" not in str(r.get("error", "")), t["name"]


# ------------------------------------------------------------------ the portfolio tools

def test_prereg_check_catches_a_rule_that_can_never_fire():
    pytest.importorskip("preregister")
    from formal_proof_mcp.tools import prereg_check
    r = prereg_check("argmax_flips > 0", {"argmax_flips": {"type": "integer", "lo": 0, "hi": 0}})
    assert r["status"] == "failed" and r["verdict"] == "UNFALSIFIABLE"
    assert r["falsifiable"] is False


def test_prereg_check_accepts_a_rule_that_can_go_either_way():
    pytest.importorskip("preregister")
    from formal_proof_mcp.tools import prereg_check
    r = prereg_check("auc > 0.7", {"auc": {"lo": 0.0, "hi": 1.0}})
    assert r["status"] == "ok" and r["falsifiable"]


def test_state_floor_counts_and_proves_impossibility():
    pytest.importorskip("floorgen")
    from formal_proof_mcp.tools import state_floor
    r = state_floor({"owner": ["a", "b", "c"], "caller": ["a", "b", "c"]},
                    [{"when": {"owner": x, "caller": x}, "answer": "ADMIT"} for x in "abc"],
                    default="REFUSE", has_default=True, budget_states=1)
    assert r["state_floor"] == 2
    assert r["impossibility"]["verdict"] == "IMPOSSIBLE"
    assert r["status"] == "failed"


def test_state_floor_reports_unavailable_when_nothing_is_demanded():
    """A floor of 1 establishes nothing, so it must not come back `ok`."""
    pytest.importorskip("floorgen")
    from formal_proof_mcp.tools import state_floor
    r = state_floor({"a": [1, 2, 3]}, [{"when": {}, "answer": "same"}])
    assert r["status"] == "unavailable"


def test_gate_count_returns_an_exact_count():
    pytest.importorskip("gatecount")
    from formal_proof_mcp.tools import count_check_removal
    r = count_check_removal({"x": {"lo": 0, "hi": 255}, "y": {"lo": 0, "hi": 255}},
                   "x < 128 and y < 128", "x < 128")
    assert r["admitted_states"] == 16384 and r["status"] == "failed"


def test_gate_count_calls_a_redundant_check_what_it_is():
    pytest.importorskip("gatecount")
    from formal_proof_mcp.tools import count_check_removal
    r = count_check_removal({"x": {"lo": 0, "hi": 255}}, "x < 128 and x < 200", "x < 128")
    assert r["status"] == "ok" and r["admitted_states"] == 0
    assert "REDUNDANT" in r["note"]


def test_gate_count_refuses_an_unenumerable_domain_rather_than_estimating():
    pytest.importorskip("gatecount")
    from formal_proof_mcp.tools import count_check_removal
    r = count_check_removal({f"v{i}": {"lo": 0, "hi": 99} for i in range(6)}, "v0 < 50", "v0 < 90")
    assert r["status"] == "failed"          # GateError surfaces as a failure, never as ok
    assert r["status"] != "ok"


@pytest.mark.parametrize("fn_name,args", [
    ("prereg_check", ("a > 0", {"a": {"lo": 0, "hi": 1}})),
    ("count_check_removal", ({"x": [1, 2]}, "x > 0", "x > -1")),
    ("evidence_audit", (".",)),
])
def test_a_missing_sibling_package_is_unavailable_never_ok(fn_name, args, monkeypatch):
    """THE failure this server exists to prevent: an agent reading 'not installed' as 'passed'."""
    import builtins
    import formal_proof_mcp.tools as T
    real_import = builtins.__import__
    blocked = {"preregister", "floorgen", "gatecount", "evidence"}

    def fake(name, *a, **kw):
        if name.split(".")[0] in blocked:
            raise ImportError(f"blocked for the test: {name}")
        return real_import(name, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", fake)
    r = getattr(T, fn_name)(*args)
    assert r["status"] == "unavailable", r
    assert "NOT a pass" in r["note"]


def test_stdio_loop_answers_a_request():
    out = io.StringIO()
    serve(io.StringIO('{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}\n'), out)
    assert json.loads(out.getvalue())["result"]["serverInfo"]["name"] == "formal-proof-mcp"


def test_stdio_loop_survives_malformed_json():
    """A hostile or truncated line must not take the server down."""
    out = io.StringIO()
    serve(io.StringIO('{not json\n{"jsonrpc":"2.0","id":2,"method":"ping"}\n'), out)
    lines = [json.loads(x) for x in out.getvalue().strip().splitlines()]
    assert lines[0]["error"]["code"] == -32700
    assert lines[1]["id"] == 2


def test_selftest_passes():
    assert selftest() == 0
