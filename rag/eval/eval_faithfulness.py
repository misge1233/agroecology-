"""Faithfulness audit of the live /explain path (Phase P3, step 3).

For ~30 evaluation scenarios this script runs the FULL production stack —
the canonical engine (``app.services.recommender_service.recommend``, which
wraps ``recommend.py``) to get a real recommendation, then
``explain_service.explain()`` with the live LLM — and audits every numeric
sentence of the generated explanation against the cited chunk text:

- records grounded / llm_used rates and numeric-guardrail trips (captured
  from the explain_service log);
- digit tokens are re-checked with the service's own ``allowed_numbers``
  whitelist (recommendation JSON + all retrieved chunks) AND against the
  sentence's own cited passages only (a stricter citation-support check);
- word-form numbers (one/two/…/half/third/twice/…) are detected and checked
  too — the production guardrail only sees digits, so this MEASURES the
  known word-form gap rather than assuming it away.
- two-tier aware (P5a): Tier-2 guidance chunks retrieved by explain() are
  recorded too; [Gn] markers are stripped like [n] and guidance-quoted
  numbers count as grounded — exactly the production rules.

Outputs (rag/eval/results/):
- ``faithfulness_audit.csv``  — one row per numeric claim sentence: text,
  cited studies, auto-verdict, blank human-audit columns.
- ``faithfulness_summary.json`` — rates and counts.
- ``explanations.jsonl`` — per scenario: recommendation, model+RAG
  explanation (condition B) and deterministic model-only text (condition A),
  consumed by ``expert_study/make_packets.py``.

Needs the full stack: rasters (LAYERS_DIR), csa_model.joblib, the Chroma
index, and OPENAI_API_KEY (one gpt-4o-mini call + ~1 embedding call per
scenario). Owner executes:  python rag/eval/eval_faithfulness.py [--n 30]
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

EVAL_DIR = Path(__file__).resolve().parent
REPO_ROOT = EVAL_DIR.parents[1]
BACKEND_DIR = REPO_ROOT / "app" / "backend"
for p in (str(REPO_ROOT), str(BACKEND_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

logger = logging.getLogger(__name__)

QUERIES_PATH = EVAL_DIR / "queries.jsonl"
RESULTS_DIR = EVAL_DIR / "results"
AUDIT_CSV = RESULTS_DIR / "faithfulness_audit.csv"
SUMMARY_JSON = RESULTS_DIR / "faithfulness_summary.json"
EXPLANATIONS_JSONL = RESULTS_DIR / "explanations.jsonl"

# Word-form numbers the digit-only production guardrail cannot see.
_WORD_VALUES: dict[str, float] = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
    "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
    "seventy": 70, "eighty": 80, "ninety": 90, "hundred": 100,
    "thousand": 1000, "half": 0.5, "halves": 0.5, "third": 1 / 3,
    "thirds": 1 / 3, "quarter": 0.25, "quarters": 0.25, "twice": 2,
    "thrice": 3, "double": 2, "doubled": 2, "triple": 3, "tripled": 3,
    "dozen": 12,
}
WORD_NUM_RE = re.compile(
    r"\b(" + "|".join(sorted(_WORD_VALUES, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)
CITE_MARKER_RE = re.compile(r"\[(\d+)\]")
GUIDANCE_MARKER_RE = re.compile(r"\[G(\d+)\]")
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?;])\s+|\n+")


# ------------------------------------------------------------- pure functions
def split_sentences(text: str) -> list[str]:
    """Rough sentence/bullet split — good enough for a claim-level audit.

    Markdown heading/bullet markup and list-enumeration prefixes ("#### 1.",
    "- ", "**") are stripped per line first, so "1." in a numbered list is
    never audited as a numeric claim.
    """
    lines = []
    for line in text.splitlines():
        line = re.sub(r"^\s*[#>*•\-]+\s*", "", line)
        line = re.sub(r"^\s*\d{1,2}[.)]\s+", "", line)
        lines.append(line.replace("**", ""))
    parts = [p.strip(" -*•\t") for p in SENTENCE_SPLIT_RE.split("\n".join(lines))]
    return [p for p in parts if p]


def digit_tokens(sentence: str, num_re: re.Pattern[str]) -> list[str]:
    """Numeric digit tokens, with [n] and [Gn] citation markers stripped."""
    stripped = GUIDANCE_MARKER_RE.sub(" ", sentence)
    return num_re.findall(CITE_MARKER_RE.sub(" ", stripped))


def word_tokens(sentence: str) -> list[str]:
    return [m.lower() for m in WORD_NUM_RE.findall(sentence)]


def cited_chunk_indices(sentence: str, n_chunks: int) -> list[int]:
    """0-based chunk indices for the sentence's [n] markers (1-based, valid)."""
    return [
        int(m) - 1
        for m in CITE_MARKER_RE.findall(sentence)
        if 1 <= int(m) <= n_chunks
    ]


def cited_guidance_indices(sentence: str, n_chunks: int) -> list[int]:
    """0-based guidance-chunk indices for the sentence's [Gn] markers."""
    return [
        int(m) - 1
        for m in GUIDANCE_MARKER_RE.findall(sentence)
        if 1 <= int(m) <= n_chunks
    ]


def audit_sentence(
    sentence: str,
    recommendation: dict[str, Any],
    chunks: list[dict[str, Any]],
    es: Any,
    guidance_chunks: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """Audit one sentence; None when it contains no numeric content.

    ``es`` is the imported ``explain_service`` module — its ``_NUM_RE`` /
    ``allowed_numbers`` / ``_number_variants`` are reused verbatim so the
    audit measures the production rules, not a reimplementation.
    """
    guidance_chunks = guidance_chunks or []
    digits = digit_tokens(sentence, es._NUM_RE)
    words = word_tokens(sentence)
    if not digits and not words:
        return None

    all_chunks = list(chunks) + list(guidance_chunks)
    allowed_all = es.allowed_numbers(recommendation, all_chunks)
    cited_idx = cited_chunk_indices(sentence, len(chunks))
    cited_g_idx = cited_guidance_indices(sentence, len(guidance_chunks))
    cited_chunks = [chunks[i] for i in cited_idx] + [
        guidance_chunks[i] for i in cited_g_idx
    ]
    allowed_cited = (
        es.allowed_numbers(recommendation, cited_chunks) if cited_chunks else None
    )
    cited_text = " ".join((c.get("text") or "").lower() for c in cited_chunks)
    all_text = " ".join((c.get("text") or "").lower() for c in all_chunks)

    def _digit_ok(tok: str, allowed: set[float]) -> bool:
        value = float(tok)
        if value.is_integer() and 0 <= value <= 10:  # production small-int rule
            return True
        return bool(es._number_variants(value) & allowed)

    def _word_ok(word: str, allowed: set[float], text: str) -> bool:
        # Grounded if the same word appears in the cited text or its numeric
        # value is whitelisted; small counts (<=10) mirror the digit rule.
        value = _WORD_VALUES[word]
        if re.search(rf"\b{re.escape(word)}\b", text):
            return True
        if float(value).is_integer() and 0 <= value <= 10:
            return True
        return bool(es._number_variants(float(value)) & allowed)

    digit_bad = [t for t in digits if not _digit_ok(t, allowed_all)]
    word_bad = [w for w in words if not _word_ok(w, allowed_all, all_text)]
    if digit_bad and word_bad:
        verdict = "fail_both"
    elif digit_bad:
        verdict = "fail_digits"
    elif word_bad:
        verdict = "fail_wordform"
    else:
        verdict = "pass"

    if allowed_cited is None:
        cited_support = "no_marker"
    else:
        ok = all(_digit_ok(t, allowed_cited) for t in digits) and all(
            _word_ok(w, allowed_cited, cited_text) for w in words
        )
        cited_support = "yes" if ok else "no"

    return {
        "sentence": sentence,
        "cite_markers": ",".join(
            [str(i + 1) for i in cited_idx]
            + [f"G{i + 1}" for i in cited_g_idx]
        ),
        "cited_era_codes": ",".join(
            str(c.get("era_code") or c.get("chunk_id")) for c in cited_chunks
        ),
        "digit_tokens": ",".join(digits),
        "ungrounded_digits": ",".join(digit_bad),
        "word_tokens": ",".join(words),
        "ungrounded_words": ",".join(word_bad),
        "auto_verdict": verdict,
        "cited_support": cited_support,
    }


class RecordingRetriever:
    """Delegates to the real retriever and records the last chunk list,

    so the audit checks sentences against the EXACT chunks ``explain()``
    saw (no second retrieval, no drift).
    """

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.last_chunks: list[dict[str, Any]] = []

    def retrieve_for_recommendation(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        self.last_chunks = self._inner.retrieve_for_recommendation(*args, **kwargs)
        return self.last_chunks


class GuardrailTripCounter(logging.Handler):
    """Counts explain_service's guardrail-trip / rejection log records."""

    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self.trips = 0
        self.rejections = 0

    def emit(self, record: logging.LogRecord) -> None:
        msg = record.getMessage()
        if "Numeric guardrail tripped" in msg:
            self.trips += 1
        if "rejected by numeric guardrail" in msg:
            self.rejections += 1


# --------------------------------------------------------------------- main
def pick_scenarios(scenarios: list[dict[str, Any]], n: int) -> list[dict[str, Any]]:
    """~n scenarios, round-robin over (family, indicator) cells — stratified."""
    cells: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for s in scenarios:
        cells[(s["practice_family"], s["indicator"])].append(s)
    picked: list[dict[str, Any]] = []
    queues = [list(v) for _, v in sorted(cells.items())]
    while len(picked) < n and any(queues):
        for q in queues:
            if q and len(picked) < n:
                picked.append(q.pop(0))
    return picked


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--queries", type=Path, default=QUERIES_PATH)
    parser.add_argument("--n", type=int, default=30)
    parser.add_argument("--k", type=int, default=8,
                        help="retrieval depth passed to explain()")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    # Full production stack — canonical engine wrapper + explain service.
    from app.services import explain_service as es
    from app.services import recommender_service as rs

    rs.warmup()
    if not es.is_ready():
        raise SystemExit(
            "RAG index/chunks not found — build the index first "
            "(rag/ingest/build_index.py)."
        )
    retriever = RecordingRetriever(es.get_retriever())
    g_inner = es.get_guidance_retriever()  # None when Tier-2 is not built
    guidance_retriever = RecordingRetriever(g_inner) if g_inner else None
    if guidance_retriever is None:
        logger.info("Guidance corpus not available — auditing evidence tier only.")

    trip_counter = GuardrailTripCounter()
    logging.getLogger(es.__name__).addHandler(trip_counter)

    with open(args.queries, encoding="utf-8") as fh:
        all_scenarios = [json.loads(line) for line in fh if line.strip()]
    scenarios = pick_scenarios(all_scenarios, args.n)

    audit_rows: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    n_engine_errors = 0

    for s in scenarios:
        sid = s["scenario_id"]
        try:
            recommendation = rs.recommend(
                lat=s["lat"],
                lon=s["lon"],
                practice_family=s["practice_family"],
                indicator=s["indicator"],
                crop_type=s.get("crop_type"),
            )
        except Exception as exc:  # no evidence / outside rasters — skip, count
            logger.warning("%s: engine error (%s) — skipped.", sid, exc)
            n_engine_errors += 1
            continue

        trips_before = trip_counter.trips
        rejections_before = trip_counter.rejections
        retriever.last_chunks = []
        if guidance_retriever is not None:
            guidance_retriever.last_chunks = []  # not stale from prior scenario
        result = es.explain(recommendation, k=args.k, retriever=retriever,
                            guidance_retriever=guidance_retriever)
        chunks = retriever.last_chunks
        guidance_chunks = (
            guidance_retriever.last_chunks if guidance_retriever else []
        )
        guardrail_tripped = trip_counter.rejections > rejections_before

        for i, sentence in enumerate(split_sentences(result["explanation"])):
            row = audit_sentence(sentence, recommendation, chunks, es,
                                 guidance_chunks=guidance_chunks)
            if row is None:
                continue
            audit_rows.append(
                {
                    "scenario_id": sid,
                    "practice_family": s["practice_family"],
                    "indicator": s["indicator"],
                    "llm_used": result["llm_used"],
                    "sentence_idx": i,
                    **row,
                    "human_verdict": "",
                    "human_notes": "",
                }
            )

        records.append(
            {
                "scenario_id": sid,
                "practice_family": s["practice_family"],
                "indicator": s["indicator"],
                "aez_belt": s.get("aez_belt"),
                "crop_type": s.get("crop_type"),
                "lat": s["lat"],
                "lon": s["lon"],
                "recommendation": recommendation,
                "model_only_text": es.build_fallback_text(recommendation, []),
                "explanation": result["explanation"],
                "citations": result["citations"],
                "grounded": result["grounded"],
                "llm_used": result["llm_used"],
                "guardrail_tripped": guardrail_tripped,
                "n_guardrail_token_trips": trip_counter.trips - trips_before,
            }
        )
        logger.info(
            "%s: llm_used=%s grounded=%s guardrail_tripped=%s",
            sid, result["llm_used"], result["grounded"], guardrail_tripped,
        )

    n = len(records)
    verdicts = defaultdict(int)
    for row in audit_rows:
        verdicts[row["auto_verdict"]] += 1
    summary = {
        "n_scenarios_requested": len(scenarios),
        "n_scenarios_completed": n,
        "n_engine_errors": n_engine_errors,
        "llm_used_rate": round(sum(r["llm_used"] for r in records) / n, 3) if n else None,
        "grounded_rate": round(sum(r["grounded"] for r in records) / n, 3) if n else None,
        "n_guardrail_rejections": sum(r["guardrail_tripped"] for r in records),
        "n_guardrail_token_trips": trip_counter.trips,
        "n_claim_sentences": len(audit_rows),
        "auto_verdicts": dict(sorted(verdicts.items())),
        "n_wordform_sentences": sum(1 for r in audit_rows if r["word_tokens"]),
        "n_cited_support_no": sum(
            1 for r in audit_rows if r["cited_support"] == "no"
        ),
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "scenario_id", "practice_family", "indicator", "llm_used",
        "sentence_idx", "sentence", "cite_markers", "cited_era_codes",
        "digit_tokens", "ungrounded_digits", "word_tokens",
        "ungrounded_words", "auto_verdict", "cited_support",
        "human_verdict", "human_notes",
    ]
    with open(AUDIT_CSV, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(audit_rows)
    with open(EXPLANATIONS_JSONL, "w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    SUMMARY_JSON.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    logger.info("Wrote %s (%d rows), %s, %s",
                AUDIT_CSV, len(audit_rows), EXPLANATIONS_JSONL, SUMMARY_JSON)
    logger.info("Summary: %s", json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
