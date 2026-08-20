"""Build blinded per-expert scoring packets (Phase P3, step 4).

Reads ``rag/eval/results/explanations.jsonl`` (written by
``eval_faithfulness.py`` — one record per scenario with BOTH the
deterministic model-only text, condition A, and the model+RAG explanation,
condition B) and writes:

- ``expert_study/packets/expert_<i>.csv`` — one blinded packet per expert:
  scenario order shuffled per expert, A/B position randomized per scenario,
  opaque item codes, blank Likert columns (see ``protocol.md``).
- ``expert_study/answer_key.csv`` — item_code -> condition mapping. Keep it
  out of every packet email; unblind only after all ratings are back.

Pure stdlib. Usage:
    python rag/eval/expert_study/make_packets.py [--experts 4] [--seed 7]
"""
from __future__ import annotations

import argparse
import csv
import json
import random
from pathlib import Path
from typing import Any

STUDY_DIR = Path(__file__).resolve().parent
EVAL_DIR = STUDY_DIR.parent
EXPLANATIONS_JSONL = EVAL_DIR / "results" / "explanations.jsonl"
PACKETS_DIR = STUDY_DIR / "packets"
ANSWER_KEY = STUDY_DIR / "answer_key.csv"

LIKERT_COLUMNS = [
    "agronomic_soundness_1to5",
    "usefulness_1to5",
    "trustworthiness_1to5",
    "clarity_1to5",
]


# ------------------------------------------------------------- pure functions
def scenario_context(record: dict[str, Any]) -> str:
    """The shared (condition-independent) context block shown to experts."""
    rec = record.get("recommendation") or {}
    ctx = (rec.get("details") or {}).get("context") or {}
    practices = "; ".join(
        f"{r.get('practice')} ({r.get('effect')})"
        for r in rec.get("recommendations") or []
    )

    def _fmt(value: Any, suffix: str = "") -> str:
        try:
            return f"{float(value):.0f}{suffix}"
        except (TypeError, ValueError):
            return "n/a"

    return (
        f"AEZ belt: {ctx.get('aez_belt') or record.get('aez_belt') or 'n/a'} | "
        f"annual rainfall: {_fmt(ctx.get('Rainfall'), ' mm')} | "
        f"slope: {_fmt(ctx.get('slope'), '%')} | "
        f"crop: {record.get('crop_type') or 'unspecified'} | "
        f"challenge: {record['practice_family']} | "
        f"objective: {record['indicator']} | "
        f"model-ranked practices: {practices or 'n/a'}"
    )


def build_items(
    records: list[dict[str, Any]], expert_no: int, seed: int
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """(packet_rows, key_rows) for one expert — shuffled and blinded.

    Deterministic for a given (seed, expert_no): scenario order is shuffled
    per expert and the A/B position within each scenario is randomized, so
    no expert can infer the condition from position.
    """
    rng = random.Random(seed * 1000 + expert_no)
    order = list(records)
    rng.shuffle(order)

    packet: list[dict[str, str]] = []
    key: list[dict[str, str]] = []
    for record in order:
        sid = record["scenario_id"]
        conditions = [
            ("A_model_only", record["model_only_text"]),
            ("B_model_rag", record["explanation"]),
        ]
        rng.shuffle(conditions)
        for slot, (condition, text) in zip(("X", "Y"), conditions):
            item_code = f"E{expert_no}-{sid}-{slot}"
            packet.append(
                {
                    "item_code": item_code,
                    "scenario_context": scenario_context(record),
                    "advisory_text": text,
                    **{c: "" for c in LIKERT_COLUMNS},
                    "comments": "",
                }
            )
            key.append(
                {
                    "expert": str(expert_no),
                    "item_code": item_code,
                    "scenario_id": sid,
                    "condition": condition,
                }
            )
    return packet, key


# --------------------------------------------------------------------- main
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--experts", type=int, default=4,
                        help="number of packets to produce (3-5 per protocol)")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--explanations", type=Path, default=EXPLANATIONS_JSONL)
    args = parser.parse_args()

    if not args.explanations.is_file():
        raise SystemExit(
            f"{args.explanations} not found — run eval_faithfulness.py first "
            "(it writes the explanations both conditions are built from)."
        )
    with open(args.explanations, encoding="utf-8") as fh:
        records = [json.loads(line) for line in fh if line.strip()]

    PACKETS_DIR.mkdir(parents=True, exist_ok=True)
    packet_fields = ["item_code", "scenario_context", "advisory_text",
                     *LIKERT_COLUMNS, "comments"]
    all_keys: list[dict[str, str]] = []
    for expert_no in range(1, args.experts + 1):
        packet, key = build_items(records, expert_no, args.seed)
        all_keys.extend(key)
        path = PACKETS_DIR / f"expert_{expert_no}.csv"
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=packet_fields)
            writer.writeheader()
            writer.writerows(packet)
        print(f"wrote {path} ({len(packet)} items, {len(records)} scenarios)")

    with open(ANSWER_KEY, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh, fieldnames=["expert", "item_code", "scenario_id", "condition"]
        )
        writer.writeheader()
        writer.writerows(all_keys)
    print(f"wrote {ANSWER_KEY} — do NOT send this file to experts")


if __name__ == "__main__":
    main()
