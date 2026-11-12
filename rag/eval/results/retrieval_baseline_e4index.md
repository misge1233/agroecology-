# Retrieval baseline on the E4 Tier 1 index (11 Nov 2026, E5 Part 0)

The Tier 1 collection `era_corpus` was rebuilt in E4 from `rag/corpus/chunks.jsonl` with the
open-access Habtamu papers (2,788 chunks: ERA 1,188, HAB 1,600; one paper chunked once per DOI
with every store study id on its chunks; pypdf 6.21 text extraction). Index hash
(`rag.retrieve.index_hash`): `3dc545151183d96c6953a613ae18099c75972ea916f6c9895dd664b4ed476f2e`.
`rag/eval/eval_retrieval.py` was rerun unchanged on both scenario files; the figures below are
the new retrieval baseline. The earlier figures (`retrieval_metrics.md`, 23 Oct 2026, and
`retrieval_metrics_v2.md`, 24 Oct 2026) were measured on the August 2026 index (1,191 ERA chunks).
The chat evaluation (`chat_eval.jsonl`, `app/backend/tests/test_chat_u9.py`) does not use the
index and is unchanged.

| scenarios | index | n | success@4 | success@8 | success@16 | recall@8 | MRR | success@8 (family) | MRR (family) |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `queries.jsonl` | August 2026 | 50 | 0.400 | 0.560 | 0.660 | 0.245 | 0.300 | 0.600 | 0.394 |
| `queries.jsonl` | **E4** | 50 | 0.380 | 0.520 | 0.600 | 0.220 | 0.315 | 0.580 | 0.382 |
| `queries_v2.jsonl` | August 2026 | 45 | 0.378 | 0.556 | 0.622 | 0.241 | 0.328 | 0.622 | 0.438 |
| `queries_v2.jsonl` | **E4** | 45 | 0.400 | 0.511 | 0.556 | 0.227 | 0.338 | 0.600 | 0.418 |

Change: success@8 falls by 0.04 (2 of 50 scenarios) and 0.044 (2 of 45), success@16 by 0.06
and 0.067, while MRR rises by 0.015 and 0.010 and success@4 moves by -0.02 and +0.022. The
silver labels only know ERA studies (the Habtamu papers cannot be "relevant" to them), so the
1,600 new chunks can only displace labelled ERA chunks from the top-k lists; the re-extracted
ERA texts (448 of 1,188 chunks changed) move individual ranks by a place or two. Full tables:
`retrieval_metrics_e4index.{json,md}` and `retrieval_metrics_v2_e4index.{json,md}`.
