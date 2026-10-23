"""WOCAT practice-record ingestion (Phase P6a scaffolding, P6b data).

``schema.py`` defines the normalized record shape; ``normalize_wocat.py``
adapts whatever export format arrives into it. Both are data-independent:
in P6a they are exercised only by the fixtures in ``fixtures/``.

**Access policy (decision record, 23 Oct 2026):** the WOCAT data arrive as a
research data export requested through the Alliance Bioversity-CIAT / WOCAT
partnership. Bulk or automated fetching of wocat.net is forbidden, and
nothing in this package fetches anything.
"""
