# rag/eval — Phase P3 evaluation harness

Offline evaluation of the RAG layer against the frozen corpus/index
(`docs/decisions/rag_design.md` §Evaluation plan). Run everything from the
repo with the backend venv (it has chromadb, rank-bm25, pandas, rasterio):

```
# 1. Build ~50 evaluation scenarios + silver era_code labels (no network)
python rag/eval/build_queries.py                  # -> queries.jsonl

# 2. Retrieval metrics with the REAL hybrid retriever
#    (needs OPENAI_API_KEY for query embeddings; ~1 embed call/scenario)
python rag/eval/eval_retrieval.py                 # -> results/retrieval_metrics.{json,md}

# 3. Faithfulness audit of the live /explain path
#    (needs rasters + csa_model.joblib + index + OPENAI_API_KEY;
#     ~1 gpt-4o-mini call/scenario)
python rag/eval/eval_faithfulness.py --n 30       # -> results/faithfulness_audit.csv,
                                                  #    results/faithfulness_summary.json,
                                                  #    results/explanations.jsonl

# 4. Blinded expert-study packets (pure stdlib; needs step 3's output)
python rag/eval/expert_study/make_packets.py --experts 4
#    -> expert_study/packets/expert_<i>.csv + expert_study/answer_key.csv
#    Protocol & rating instructions: expert_study/protocol.md
```

Tests (pure functions, no network/index):

```
cd rag/eval && python -m pytest test_build_queries.py -q
```

Notes
- Silver labels: for each scenario, relevant studies are the ERA-source
  era_codes whose dataset rows match the scenario's practice family +
  indicator + top practice, restricted to studies with chunks in the corpus
  (`relevant_era_codes_family_level` drops the practice constraint).
- Recall@k is study-level at chunk depth k; MRR is over the first chunk from
  a relevant study.
- `faithfulness_audit.csv` has blank `human_verdict`/`human_notes` columns —
  the human audit pass fills those in.
- `expert_study/answer_key.csv` unblinds the packets; never send it out.
