"""Unified evidence store (Phase E0/E1, 10 Nov 2026).

One frozen schema (:mod:`pipelines.evidence.schema`, roadmap Appendix A) that
every later phase reads. Loaders per source (``load_era``, ``load_csa``,
``load_habtamu``), the catalogue parser, the store builder and the registry
builder live here. See ``data/evidence/README.md``.
"""
