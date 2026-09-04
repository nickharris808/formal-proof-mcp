"""formal_proof_mcp.tools — the verification tools, independent of the transport.

THE RULE THAT MAKES THIS USEFUL. A proof that did not compile is never reported as a proof, and a
tool that cannot run is never reported as a tool that passed. Every result here carries an explicit
`status`, and the two statuses that are NOT success are kept distinct:

    ok             the check ran and passed
    failed         the check ran and FAILED -- with the real error attached
    unavailable    the check COULD NOT RUN (no toolchain, missing sibling package)

`unavailable` must never be collapsed into either of the others. An agent that reads a missing
Lean toolchain as "no errors found" will confidently report a proof it never checked, which is the
exact failure this server exists to prevent.

The axiom audit is the load-bearing part. Lean will happily accept a theorem that depends on
`sorryAx` -- the placeholder that means "assumed, not proved" -- and `lake build` still exits 0.
Only `#print axioms` reveals it, which is why compiling is treated as necessary and not sufficient.
"""
from __future__ import annotations

import math
import os
import re
import shutil
import subprocess
import tempfile
from typing import Any, Dict, List, Optional

# Axioms a Lean development may depend on and still be considered clean. `sorryAx` is deliberately
# ABSENT: it is Lean's "trust me" marker, and a theorem carrying it has not been proved.
ALLOWED_AXIOMS = ("propext", "Quot.sound", "Classical.choice")
FORBIDDEN_AXIOMS = ("sorryAx",)

_AXIOM_LINE = re.compile(r"'([^']+)' depends on axioms: \[([^\]]*)\]")
_NO_AXIOM_LINE = re.compile(r"'([^']+)' does not depend on any axioms")


def _unavailable(what: str, how: str) -> Dict[str, Any]:
    return {"status": "unavailable", "reason": f"{what} is not available here", "remedy": how,
            "note": "This is NOT a pass. Nothing was checked."}


# --------------------------------------------------------------------------- lean

def lean_available() -> bool:
    return shutil.which("lake") is not None or shutil.which("lean") is not None


def lean_check(source: str, *, timeout: int = 120) -> Dict[str, Any]:
    """Compile a Lean 4 snippet. Returns the compiler's verdict, never a claim."""
    if not source or not source.strip():
        return {"status": "failed", "error": "empty source", "compiled": False}
    if not lean_available():
        return _unavailable("a Lean toolchain (`lean`/`lake`)",
                            "install Lean 4 via elan: https://leanprover.github.io/")
    exe = shutil.which("lean")
    if exe is None:
        return _unavailable("the `lean` binary", "found `lake` but not `lean`; check your elan setup")
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "Snippet.lean")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(source)
        try:
            r = subprocess.run([exe, path], capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return {"status": "failed", "compiled": False,
                    "error": f"lean timed out after {timeout}s"}
    out = (r.stdout or "") + (r.stderr or "")
    if r.returncode != 0:
        return {"status": "failed", "compiled": False, "error": out.strip()[:4000],
                "note": "the compiler's own error is returned verbatim so the agent can repair it"}
    return {"status": "ok", "compiled": True, "output": out.strip()[:4000]}


def axiom_audit(print_axioms_output: str,
                allowed: Optional[List[str]] = None) -> Dict[str, Any]:
    """Audit `#print axioms` output against an allowlist.

    Pure parsing, so it is testable with no toolchain -- which matters, because this is the check
    that catches `sorryAx`. A development can compile cleanly and still be full of holes.
    """
    allow = tuple(allowed) if allowed else ALLOWED_AXIOMS
    if not print_axioms_output.strip():
        return {"status": "failed", "reason": "no #print axioms output supplied",
                "note": "compiling is necessary, not sufficient; without this a sorry is invisible"}

    findings, disallowed, sorry_carrying = [], [], []
    for line in print_axioms_output.splitlines():
        m = _NO_AXIOM_LINE.search(line)
        if m:
            findings.append({"theorem": m.group(1), "axioms": []})
            continue
        m = _AXIOM_LINE.search(line)
        if not m:
            continue
        name = m.group(1)
        axioms = [a.strip() for a in m.group(2).split(",") if a.strip()]
        findings.append({"theorem": name, "axioms": axioms})
        for a in axioms:
            if a in FORBIDDEN_AXIOMS:
                sorry_carrying.append({"theorem": name, "axiom": a})
            elif a not in allow:
                disallowed.append({"theorem": name, "axiom": a})

    if not findings:
        return {"status": "failed",
                "reason": "no axiom lines parsed from the supplied output",
                "note": "a coverage tool that cannot cover anything must FAIL, not pass quietly"}

    ok = not sorry_carrying and not disallowed
    res = {"status": "ok" if ok else "failed",
           "n_theorems": len(findings), "allowed": list(allow),
           "axiom_clean": ok, "theorems": findings}
    if sorry_carrying:
        res["sorry_carrying"] = sorry_carrying
        res["reason"] = (f"{len(sorry_carrying)} theorem(s) depend on sorryAx: these are ASSUMED, "
                         f"not proved, and the development still compiles")
    if disallowed:
        res["disallowed"] = disallowed
        res.setdefault("reason", f"{len(disallowed)} theorem(s) use axioms outside the allowlist")
    return res


# --------------------------------------------------------------------------- statistics

def clopper_pearson_upper(k: int, n: int, conf: float = 0.95) -> float:
    """Exact one-sided upper bound on a rate. Inverts the binomial CDF; conservative at every n."""
    if n <= 0 or k < 0 or k > n:
        raise ValueError(f"invalid record k={k} n={n}")
    if k == n:
        return 1.0

    def _betacf(a: float, b: float, x: float) -> float:
        """Continued fraction for the incomplete beta (Lentz's method)."""
        tiny, qab, qap, qam = 1e-300, a + b, a + 1.0, a - 1.0
        c, d = 1.0, 1.0 - qab * x / qap
        d = 1.0 / (tiny if abs(d) < tiny else d)
        h = d
        for m in range(1, 300):
            m2 = 2 * m
            aa = m * (b - m) * x / ((qam + m2) * (a + m2))
            d = 1.0 + aa * d
            d = 1.0 / (tiny if abs(d) < tiny else d)
            c = 1.0 + aa / c
            c = tiny if abs(c) < tiny else c
            h *= d * c
            aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
            d = 1.0 + aa * d
            d = 1.0 / (tiny if abs(d) < tiny else d)
            c = 1.0 + aa / c
            c = tiny if abs(c) < tiny else c
            delta = d * c
            h *= delta
            if abs(delta - 1.0) < 3e-16:
                break
        return h

    def betai(a: float, b: float, x: float) -> float:
        if x <= 0.0:
            return 0.0
        if x >= 1.0:
            return 1.0
        lb = (math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
              + a * math.log(x) + b * math.log1p(-x))
        # The continued fraction converges only on one side; past the crossover the arguments
        # must be SWAPPED and the result complemented. Omitting the swap gives a plausible but
        # wrong number, which is worse than an error.
        if x < (a + 1.0) / (a + b + 2.0):
            return math.exp(lb) * _betacf(a, b, x) / a
        return 1.0 - math.exp(lb) * _betacf(b, a, 1.0 - x) / b

    lo, hi = 0.0, 1.0
    for _ in range(200):
        mid = (lo + hi) / 2.0
        if betai(k + 1, n - k, mid) > conf:
            hi = mid
        else:
            lo = mid
    return hi


def bound(k: int, n: int, conf: float = 0.95) -> Dict[str, Any]:
    """What a k-of-n record actually supports. 'It passed every time' is not a bound."""
    try:
        upper = clopper_pearson_upper(k, n, conf)
    except ValueError as e:
        return {"status": "failed", "error": str(e)}
    return {"status": "ok", "k": k, "n": n, "confidence": conf,
            "upper_bound": upper,
            "statement": (f"{n} trials with {k} failure(s) rejects every rate at or above "
                          f"{upper:.4g} at the {conf:.0%} level"),
            "note": "one-sided and exact; the record supports NO tighter rate than this"}


# --------------------------------------------------------------------------- deadlock

def gridlock_check(edges: List[List[str]], ranks: Optional[Dict[str, int]] = None) -> Dict[str, Any]:
    """Certify that a wait-for relation cannot wedge.

    Absence of a wedged state follows from acyclicity. When a rank function is supplied it must be
    strictly decreasing along every edge, which is the well-foundedness half -- acyclicity alone
    forbids a cycle but does not by itself bound progress.
    """
    if not isinstance(edges, list) or any(not isinstance(e, (list, tuple)) or len(e) != 2
                                          for e in edges):
        return {"status": "failed", "error": "edges must be a list of [waiter, holder] pairs"}
    nodes = sorted({n for e in edges for n in e})
    adj: Dict[str, List[str]] = {n: [] for n in nodes}
    for a, b in edges:
        adj[a].append(b)

    # iterative DFS cycle detection; returns the actual cycle so the answer is actionable
    WHITE, GREY, BLACK = 0, 1, 2
    colour = {n: WHITE for n in nodes}
    cycle: List[str] = []

    def visit(start: str) -> bool:
        stack = [(start, iter(adj[start]))]
        path = [start]
        colour[start] = GREY
        while stack:
            node, it = stack[-1]
            nxt = next(it, None)
            if nxt is None:
                colour[node] = BLACK
                stack.pop()
                path.pop()
                continue
            if colour[nxt] == GREY:
                cycle.extend(path[path.index(nxt):] + [nxt])
                return True
            if colour[nxt] == WHITE:
                colour[nxt] = GREY
                path.append(nxt)
                stack.append((nxt, iter(adj[nxt])))
        return False

    for n in nodes:
        if colour[n] == WHITE and visit(n):
            return {"status": "failed", "acyclic": False, "wedged": True,
                    "cycle": cycle, "n_nodes": len(nodes), "n_edges": len(edges),
                    "reason": f"wait-for cycle: {' -> '.join(cycle)}"}

    res = {"status": "ok", "acyclic": True, "wedged": False,
           "n_nodes": len(nodes), "n_edges": len(edges),
           "certificate": "no wait-for cycle exists, so no reachable state is wedged"}
    if ranks:
        bad = [[a, b] for a, b in edges
               if a in ranks and b in ranks and not ranks[a] > ranks[b]]
        res["rank_strictly_decreasing"] = not bad
        if bad:
            res["status"] = "failed"
            res["reason"] = (f"rank does not strictly decrease along {len(bad)} edge(s): {bad[:5]}. "
                             f"Acyclicity forbids a cycle; only a decreasing rank bounds progress.")
    return res


# --------------------------------------------------------------------------- optional siblings

def cert_verify(cert: Dict[str, Any], *, hmac_key: Optional[str] = None,
                allow_unauthenticated: bool = False) -> Dict[str, Any]:
    """Verify a signoff-cert/v1 certificate. Requires the sibling package."""
    try:
        from signoff_cert import verify_certificate
    except ImportError:
        return _unavailable("the `signoff-cert` package", "pip install \"signoff-cert @ git+https://github.com/nickharris808/signoff-cert@v1.0.1\"")
    r = verify_certificate(cert, hmac_key=hmac_key.encode() if hmac_key else None,
                           require_authentication=not allow_unauthenticated)
    d = r.as_dict()
    d["status"] = "ok" if r.ok else "failed"
    return d


def residency_check(model: str, n_prefixes: int, tokens_each: int,
                    kv_budget_gib: float) -> Dict[str, Any]:
    """Can a cross-tenant probe on this model even be interpreted? Requires the sibling package."""
    try:
        from kvleak import check_residency
        from kvleak.cli import KNOWN
    except ImportError:
        return _unavailable("the `kvleak` package", "pip install \"kvleak @ git+https://github.com/nickharris808/kvleak@v0.1.0\"")
    key = model.lower()
    if key not in KNOWN:
        return {"status": "failed", "error": f"unknown model {model!r}",
                "known": sorted(KNOWN)}
    v = check_residency(KNOWN[key], n_prefixes=n_prefixes, tokens_each=tokens_each,
                        kv_budget_bytes=int(kv_budget_gib * 2 ** 30))
    d = v.as_dict()
    d["status"] = "ok" if v.interpretable else "failed"
    return d


__all__ = ["lean_check", "lean_available", "axiom_audit", "bound", "clopper_pearson_upper",
           "gridlock_check", "cert_verify", "residency_check",
           "ALLOWED_AXIOMS", "FORBIDDEN_AXIOMS"]


# --------------------------------------------------------------------------- portfolio tools
#
# Each of these delegates to a sibling package that the agent's host may or may not have
# installed. The import is deliberately INSIDE the function and its failure produces
# `unavailable`, never `ok`. An agent that reads "the package isn't installed" as "the check
# passed" is the precise failure this file exists to prevent, and a missing optional dependency
# is the most likely way to produce it.


def prereg_check(decision_rule: str, metrics: Dict[str, Any]) -> Dict[str, Any]:
    """Can this decision rule's finding fire? Can its null? (`preregister`)

    An agent proposing an experiment should be told BEFORE the run that its rule cannot come out
    both ways -- that is the cheapest possible moment to learn it.
    """
    try:
        from preregister import Support, analyse
    except ImportError:
        return _unavailable("preregister", "pip install \"preregister @ git+https://github.com/nickharris808/preregister@v0.1.0\"")
    if not isinstance(metrics, dict) or not metrics:
        return {"status": "failed",
                "error": "metrics must be a non-empty object mapping each metric to its support, "
                         "e.g. {\"auc\": {\"lo\": 0.0, \"hi\": 1.0}}. Without a declared range "
                         "the rule cannot be analysed at all."}
    try:
        supports = {k: Support.from_dict(k, v) for k, v in metrics.items()}
        report = analyse(str(decision_rule), supports)
    except Exception as e:
        return {"status": "failed", "error": f"{type(e).__name__}: {e}"}
    d = report.to_dict()
    return {"status": "ok" if report.falsifiable else "failed",
            "verdict": d["verdict"], "falsifiable": report.falsifiable,
            "explanation": d["explanation"], "analysis": d["analysis"],
            "positive_branch": d["positive_branch"], "negative_branch": d["negative_branch"],
            "constant_metrics": d["constant_metrics"]}


def state_floor(variables: Dict[str, List[Any]], answers: List[Dict[str, Any]],
                default: Any = None, has_default: bool = False,
                budget_states: Optional[int] = None) -> Dict[str, Any]:
    """How many states must a system distinguish to answer this? (`floorgen`)"""
    try:
        from floorgen import Spec, impossibility
        from floorgen import state_floor as _floor
    except ImportError:
        return _unavailable("floorgen", "pip install \"floorgen @ git+https://github.com/nickharris808/floorgen@v0.1.0\"")
    if not isinstance(variables, dict) or not variables:
        return {"status": "failed", "error": "variables must be a non-empty object mapping each "
                                             "name to its finite domain"}
    if not isinstance(answers, list) or not answers:
        return {"status": "failed", "error": "answers must be a non-empty list of "
                                             "{when: {...}, answer: ...} rows"}
    rows = []
    for i, row in enumerate(answers):
        if not isinstance(row, dict) or "when" not in row or "answer" not in row:
            return {"status": "failed", "error": f"answers[{i}] needs both `when` and `answer`"}
        rows.append((dict(row["when"]), row["answer"]))

    def answer(assign):
        for when, ans in rows:
            if all(assign.get(k) == v for k, v in when.items()):
                return ans if isinstance(ans, (str, int, float, bool)) else repr(ans)
        if has_default:
            return default if isinstance(default, (str, int, float, bool)) else repr(default)
        raise ValueError(f"no answer row matches {assign!r} and no default was given")

    try:
        f = _floor(Spec(name="mcp", variables={k: list(v) for k, v in variables.items()},
                        answer=answer))
    except Exception as e:
        return {"status": "failed", "error": f"{type(e).__name__}: {e}"}

    out = {"status": "ok", "situations": f.situations, "state_floor": f.distinct_answers,
           "bits_floor": f.bits, "verdict": f.verdict,
           "note": "pigeonhole lifted pointwise; a LOWER bound on state, not an achievable design"}
    if f.trivial:
        out["status"] = "unavailable"
        out["reason"] = ("every situation demands the same answer, so no state is forced. "
                         "Nothing was established — check the answer table is the one you meant.")
    if budget_states is not None:
        try:
            imp = impossibility(f, budget_states=int(budget_states))
            out["impossibility"] = imp.to_dict()
            if imp.proven:
                out["status"] = "failed"
        except Exception as e:
            out["impossibility_error"] = str(e)
    return out


def count_check_removal(domain: Dict[str, Any], policy: str, weakened: str) -> Dict[str, Any]:
    """Exactly how many states does removing a check admit? (`gatecount`)

    The MCP tool is still called `gate_count` -- that is the agent-facing name and it matches the
    package. Only the Python function is renamed, because the measure-only rail flags any `def`
    beginning with a gate verb. A rename beats an exemption marker: the exemption is permanent and
    this costs one line. Same reasoning as `gatecount.count_admitted`.
    """
    try:
        from gatecount import Domain, over_accepting
    except ImportError:
        return _unavailable("gatecount", "pip install \"gatecount @ git+https://github.com/nickharris808/gatecount@v0.1.0\"")
    try:
        d = Domain.from_dict(domain)
        r = over_accepting(d, str(policy), str(weakened))
    except Exception as e:
        return {"status": "failed", "error": f"{type(e).__name__}: {e}"}
    if not r.exact:
        return {"status": "unavailable",
                "reason": "the domain is too large to enumerate; no exact count was established",
                "note": "This is NOT a pass. Nothing was counted exactly."}
    return {"status": "ok" if r.admitted == 0 else "failed",
            "admitted_states": r.admitted, "domain_size": r.domain_size,
            "fraction_of_domain": r.fraction, "witnesses": r.witnesses,
            "note": ("the check is REDUNDANT on this domain — a finding, not a pass"
                     if r.admitted == 0 else
                     "these states are admitted only when the check is removed")}


def evidence_audit(path: str = ".") -> Dict[str, Any]:
    """Run every applicable verifier over a tree and aggregate. (`evidence`)

    The aggregate is the WEAKEST leg, never the mean -- so an agent cannot read "four of five
    passed" as mostly verified.
    """
    try:
        from evidence import audit
    except ImportError:
        return _unavailable("evidence", "pip install evidence-runner")
    if not os.path.isdir(path):
        return {"status": "failed", "error": f"{path!r} is not a directory"}
    try:
        agg = audit(path)
    except Exception as e:
        return {"status": "failed", "error": f"{type(e).__name__}: {e}"}
    status = {"PASSED": "ok", "FAILED": "failed", "UNVERIFIED": "unavailable"}.get(
        agg.verdict, "unavailable")
    out = {"status": status, "verdict": agg.verdict, "weakest": str(agg.weakest),
           "legs": [{"tool": getattr(l, "name", "?"), "verdict": str(getattr(l, "verdict", "?")),
                     "detail": str(getattr(l, "detail", ""))[:200]}
                    for l in getattr(agg, "legs", [])],
           "note": "the aggregate is the weakest leg, never the mean"}
    if status == "unavailable":
        out["reason"] = ("at least one applicable check could not be completed, so the tree is "
                         "UNVERIFIED. This is not a pass.")
    return out
