"""VOLTERRA AI analytics.

Phase 2 contains the **v1** algorithms: a faithful, standard-library-only port of the legacy
JavaScript prototype, verified against the golden fixtures in ``backend/tests/golden/``.
v1 reproduces the prototype exactly, including known defects F1–F8
(ARCHITECTURE_PLAN.md §3.6). v1 is never changed. Phase 5 added the corrected behaviour as
separate v2 modules (``*_v2.py``, composed by ``analysis_v2.analyze_v2()``); see CHANGELOG.md.

Floating-point note: results depend on operation order. Modules here deliberately mirror the
JavaScript expression order and never use ``sum()`` (compensated in Python 3.12+), ``fsum``,
``statistics`` or numpy. See ``jsmath`` for JavaScript number semantics.
"""
