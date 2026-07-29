"""formal-proof-mcp — give your coding agent a proof kernel, and an honest "I could not check that".

Six verification tools over the Model Context Protocol, dependency-free. The invariant that makes
it worth wiring in: **a result that was not checked is never returned as a result that passed.**
Every response carries `status` in {ok, failed, unavailable}, and `unavailable` is kept distinct
from both — an agent that reads a missing toolchain as "no errors found" will assert a proof it
never checked.

CLEAN: exposes a toolchain and reports. Implements no filed apparatus.
"""
from __future__ import annotations

__version__ = "0.1.0"

from .tools import (
    ALLOWED_AXIOMS,
    FORBIDDEN_AXIOMS,
    axiom_audit,
    bound,
    cert_verify,
    clopper_pearson_upper,
    gridlock_check,
    lean_available,
    lean_check,
    residency_check,
)

__all__ = [
    "lean_check", "lean_available", "axiom_audit", "bound", "clopper_pearson_upper",
    "gridlock_check", "cert_verify", "residency_check",
    "ALLOWED_AXIOMS", "FORBIDDEN_AXIOMS", "__version__",
]
