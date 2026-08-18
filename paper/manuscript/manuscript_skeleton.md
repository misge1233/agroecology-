# Manuscript skeleton — Computers and Electronics in Agriculture

**Working title:**
**AgroAdvisor-ET: coupling meta-analytic machine learning with retrieval-augmented
generation for evidence-grounded agroecological practice recommendation in Ethiopia**

*Reserve titles:* "From evidence to advisory: a hybrid machine-learning and
retrieval-augmented-generation system for context-specific agroecological practice
recommendation" · "Evidence in, advice out: an AI advisor that ranks agroecological
practices from field trials and explains them from the literature"

**Authors:**
Misganu Tuse¹\*, Wuletawu Abera²
¹ International Center for Tropical Agriculture (CIAT), Addis Ababa, Ethiopia
² International Center for Tropical Agriculture (CIAT), Accra, Ghana
\* Corresponding author: m.tuse@cgiar.org

**Article type:** Original research (systems + methods) · target ~8,000–9,500 words,
6–8 figures, 3–4 tables.

---

## Highlights (5 × ≤85 characters — draft)

- 8,664 paired field observations from two corpora harmonized into one effect-size dataset
- One map pin auto-derives full agro-ecological context from an 11-layer 250 m stack
- Grouped-CV RandomForest ranks practices honestly, with per-objective confidence
- RAG layer retrieves from the model's own ~300 source studies — cited explanations
- Experts rated grounded advisories against model-only output across AEZ belts

## Abstract (~250 words — structure)

Context/problem (evidence–advice gap) → system (hybrid ML + RAG, division of
labour) → data (ERA + CSA, harmonization) → methods (stack, GroupKFold RF, RAG
over source studies) → results (model metrics; RAG faithfulness; expert study) →
significance (transferable architecture for evidence-grounded advisory).

---

## 1. Introduction
- [ ] Evidence–advice gap in Ethiopian/African extension; context-specificity (15 AEZ belts)
- [ ] Why plain-LLM agronomy advice is untrustworthy (hallucinated effects); why pure ML rankers are unexplained
- [ ] Contribution list (5 claims — see research_project_plan.md §1.4)
- Source material: deck slides 1–3

## 2. Related work
- [ ] Agricultural decision-support & practice recommenders
- [ ] Meta-analytic evidence bases (ERA; Adimassu et al. CSA prioritization)
- [ ] LLM/RAG in agriculture (thin literature — position our novelty)
- Needs: literature search (P4 task)

## 3. Data: two evidence corpora, one effect-size currency
- [ ] Corpora description; response ratio ln(with/without); yi verification
- [ ] Harmonization rules table (PRISMA-style flow, Fig. 2)
- [ ] Practice-family crosswalk (AICCRA/Adimassu families; priority rule)
- [ ] Final dataset: 8,664 rows × 20 cols, 337 studies, imbalance discussion
- Source material: docs/reports/*.md (near paper-ready)

## 4. Geospatial context engine
- [ ] 11 aligned 250 m layers (Table); one-pin feature derivation; nearest-valid fallback
- [ ] Train/serve consistency (same code path) — zero skew
- Source material: geodata/README.md, deck 8–11; Fig. 3 from make_maps.py

## 5. Practice-ranking model
- [ ] Feature selection (grouped permutation importance; collinearity; 13 features)
- [ ] GroupKFold(5) by study; baselines (practice×indicator mean; HGB); RF selection
- [ ] Honest framing: CV R² 0.190 vs 0.188 baseline; per-indicator/per-source metrics; confidence flags
- Source material: model/artifacts/model_metrics.json, docs/reports/feature_selection_report.md

## 6. RAG explanation layer  ← NEW WORK (P2)
- [ ] Corpus: ~300 DOI-linked ERA source studies; acquisition & coverage table
- [ ] era_code linkage: chunk ↔ training rows (the novelty)
- [ ] Structured-query retrieval (practice × context × indicator); hybrid dense+BM25
- [ ] Cite-or-silent generation; numeric-guardrail
- Source material: docs/decisions/rag_design.md

## 7. System: AgroAdvisor-ET
- [ ] Architecture (Fig. 1); FastAPI wrap-never-fork; SSE chat; Next.js UI; honesty-by-design table
- Source material: deck 15–19, app/ code

## 8. Evaluation  ← NEW WORK (P3)
- [ ] Model: grouped CV, per-indicator, per-source (have)
- [ ] Retrieval: Recall@k / MRR on ~50 labelled queries (silver via era_code)
- [ ] Groundedness: RAGAS-style faithfulness + citation precision (hand-audited)
- [ ] Expert study: blinded rating, model-only vs model+RAG, ~30 scenarios × 3–5 experts
      **Expert panel (placeholders — to be invited):**
      1. [Expert 1 — AEZ specialist, EIAR]
      2. [Expert 2 — extension specialist, MoA]
      3. [Expert 3 — CSA/agroecology researcher, CGIAR]
      4. [Expert 4 — soil & water conservation specialist]
      5. [Expert 5 — livestock systems specialist]
- [ ] Ablations: no-RAG / unfiltered / metadata-filtered

## 9. Discussion
- [ ] Ranking-not-forecasting; what R² ≈ 0.19 means on heterogeneous trials
- [ ] Imbalance (yield 68%, ERA 84%) and thin indicators; mixed practice granularity
- [ ] Transferability beyond Ethiopia (swap stack + evidence, keep pipeline)
- [ ] Limitations & future work (Amharic/Afaan Oromo, offline clients, new layers)

## 10. Conclusion

---

## Figures
| # | Content | Source |
|---|---|---|
| F1 | System architecture (hybrid ML + RAG) | draw (plan §1.2) |
| F2 | Data harmonization flow, PRISMA-style row counts | docs/reports |
| F3 | Feature-stack maps of Ethiopia | pipelines/features/make_maps.py |
| F4 | Permutation importance + per-indicator out-of-fold R² | model artifacts |
| F5 | RAG pipeline + era_code linkage diagram | draw |
| F6 | Worked example: pin → ranked cards → cited explanation | app screenshots |
| F7 | Expert-evaluation results (model vs model+RAG) | P3 output |

## Tables
T1 corpora & harmonization rules · T2 the 11 layers · T3 model comparison &
per-indicator metrics · T4 RAG corpus coverage & evaluation results

## Statements
- **Data availability:** ERA via Harvard Dataverse (cite deposit DOI); merged
  model-ready dataset + code: GitHub + Zenodo DOI at submission.
- **Author contributions (CRediT):** MT — conceptualization, methodology, software,
  data curation, writing (original draft). WA — supervision, methodology, writing
  (review & editing). *(adjust as you see fit)*
- **Declaration of competing interest:** none.
- **AI use disclosure:** generative AI used for coding assistance and drafting
  support under author supervision (per Elsevier policy).
- **Funding:** [to add]

## Reviewer-pushback pre-loads
| Likely objection | Our answer |
|---|---|
| "R² is only 0.19" | ranking framing; beats mean-baseline; grouped CV is honest where random splits inflate; confidence flags |
| "Source imbalance" | per-source metrics; source kept as diagnostic, never a feature |
| "Practice taxonomy mixed granularity" | crosswalk section + explicit limitation + roadmap |
| "LLM hallucination risk" | architecture: model owns numbers; cite-or-silent; guardrail regex; faithfulness metrics |
