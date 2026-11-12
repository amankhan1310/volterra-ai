"""VOLTERRA AI analytics.

Phase 2 contains the **v1** algorithms: a faithful, standard-library-only port of the legacy
JavaScript prototype, verified against the golden fixtures in ``backend/tests/golden/``.
v1 reproduces the prototype exactly, including known defects F1–F8
(ARCHITECTURE_PLAN.md §3.6). Corrected behaviour will be added as separate v2 implementations;
v1 is never changed.

Floating-point note: results depend on operation order. Modules here deliberately mirror the
JavaScript expression order and never use ``sum()`` (compensated in Python 3.12+), ``fsum``,
``statistics`` or numpy. See ``jsmath`` for JavaScript number semantics.
"""
