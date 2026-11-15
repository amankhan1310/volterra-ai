"""Phase 6 M1: acquisition and provenance of the real battery datasets.

``sources`` is the registry (publisher, citation, licence, pinned checksums), ``fetch`` downloads
with resume and verification, ``manifest`` writes and verifies ``MANIFEST.json``, ``safety``
refuses destinations Git could track, and ``cli`` ties them together
(``python -m volterra_ml.acquisition``). Parsing the files is M2; nothing here reads their content.
"""
