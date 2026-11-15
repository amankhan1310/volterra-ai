"""Canonical battery-data schema (Phase 6 M2): column contract, validation, Parquet bundles.

``columns`` is the dependency-free contract shared with the backend importer, ``validate`` holds
the deterministic quality rules, and ``bundle`` writes and verifies Parquet bundles.
"""
