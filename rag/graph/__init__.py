"""Knowledge-graph layer for AgroAdvisor-ET (Phase P6a).

Pure-Python package built on ``networkx``. It joins three things that were
previously only implicitly related:

* the **evidence** the ML model was trained on (``CSA_practices``,
  ``practice_family``, studies, indicators — the dataset's own numbers),
* the **Tier-1/Tier-2 corpus** (``era_code`` -> chunks, DOIs, guidance docs),
* the **WOCAT SLM vocabulary** (SLM groups/measures, degradation types,
  context classes, on-site impact variables) and, from P6b, real WOCAT
  practice records.

The graph never generates numbers. Every ``REPORTS_EFFECT`` aggregate is a
plain aggregation of dataset rows, and every edge carries a ``source``
provenance tag (see :mod:`rag.graph.schema`).
"""
