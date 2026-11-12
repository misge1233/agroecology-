"""The metric library of the evaluation harness (E4 Part 5; roadmap Appendix B, exactly).

Every method is scored by these functions from the same prediction format (one row per
``(query_id, practice_id)``: ``score``, ``est_lrr``, ``lo``, ``hi``, ``abstain``) against
the ground-truth items (``y`` = pooled, oriented ``lrr`` per practice).

Per query (``y`` oriented so that higher is better; ``r`` the method's scores):

* **top-1 hit**: 1 if the top-ranked practice is an observed best (``argmax y``; several
  practices tied at the maximum all count); chance = ``1 / |P|``;
* **top-half hit**: 1 if the top-ranked practice is within the observed top half, i.e. its
  average rank by ``y`` (1 = worst) is above ``|P| / 2`` (as ``evaluate.ranking_metrics``);
* **C-index**: share of practice pairs with ``y_i != y_j`` for which the scores order them
  the same way; a tie in the scores counts half;
* **NDCG@3**: DCG of the top 3 by score with gains ``max(y_p - min(y), 0)``, discount
  ``1 / log2(rank + 1)``, divided by the DCG of the ideal ordering; ``nan`` when every gain
  is 0;
* **Spearman rho**: rank correlation between ``r`` and ``y`` (average ranks for ties;
  ``nan`` when either side is constant); reported as the median over queries;
* **RMSE** and **sign accuracy** of ``est_lrr`` against ``y`` on the items that carry an
  estimate;
* **80 % interval coverage** (share of items whose ``[lo, hi]`` contains ``y``) and
  **width** (median ``hi - lo``);
* **abstention**: a query is abstained when the method abstains on **any** of its candidates
  (it could not rank the full candidate set); accuracy is then reported on the answered
  queries with the answered share. Ranking an abstained candidate last instead would
  turn thin-evidence practices, which are often the ones a trial introduces, into
  systematic misses: ``nearest_studies`` showed a median Spearman of -0.56 on partially
  answered queries against +0.50 on fully answered ones (E4 run ``et_baselines_a``).

Aggregation (:func:`aggregate`): per ``(method, split, rep)`` the mean over queries, then
mean and sd across repetitions; :func:`bootstrap` gives a query-level 95 % interval
(1,000 resamples, seeded) of the per-query values averaged across repetitions.
"""
from __future__ import annotations

import math
from typing import Any, Iterable, Sequence

import numpy as np
import pandas as pd

QUERY_METRICS = ("top1_hit", "top1_chance", "tophalf_hit", "c_index", "c_concordant", "c_comparable", "ndcg3",
                 "spearman", "rmse", "sign_acc", "coverage80", "width80", "n_candidates", "n_estimates")
HEADLINE = ("top1_hit", "top1_chance", "tophalf_hit", "c_index", "ndcg3", "spearman_median", "rmse", "sign_acc",
            "coverage80", "width80", "abstention_rate", "n_queries", "n_answered")
MIN_CELL = 20  # a breakdown cell with fewer queries is shown as "n < 20", never as a number


# ----------------------------------------------------------------- ranks and pairs
def average_ranks(values: Sequence[float]) -> np.ndarray:
    """Ranks 1..n (1 = smallest), ties sharing their average rank."""
    arr = np.asarray(values, dtype=float)
    order = np.argsort(arr, kind="stable")
    ranks = np.empty(len(arr), dtype=float)
    ranks[order] = np.arange(1, len(arr) + 1, dtype=float)
    for value in np.unique(arr):
        tied = arr == value
        if tied.sum() > 1:
            ranks[tied] = ranks[tied].mean()
    return ranks


def spearman(a: Sequence[float], b: Sequence[float]) -> float:
    ra, rb = average_ranks(a), average_ranks(b)
    if len(ra) < 2 or np.std(ra) == 0 or np.std(rb) == 0:
        return float("nan")
    return float(np.corrcoef(ra, rb)[0, 1])


def concordance(truth: Sequence[float], pred: Sequence[float]) -> tuple[float, int]:
    """``(concordant pairs with ties counted half, comparable pairs)``."""
    t, p = np.asarray(truth, float), np.asarray(pred, float)
    concordant = 0.0
    comparable = 0
    for i in range(len(t)):
        for j in range(i + 1, len(t)):
            if t[i] == t[j]:
                continue
            comparable += 1
            if (t[i] - t[j]) * (p[i] - p[j]) > 0:
                concordant += 1.0
            elif p[i] == p[j]:
                concordant += 0.5
    return concordant, comparable


def c_index(truth: Sequence[float], pred: Sequence[float]) -> float:
    c, m = concordance(truth, pred)
    return c / m if m else float("nan")


def top1_hit(truth: Sequence[float], pred: Sequence[float]) -> float:
    t, p = np.asarray(truth, float), np.asarray(pred, float)
    best = int(np.argmax(p))
    return float(t[best] == t.max())


def tophalf_hit(truth: Sequence[float], pred: Sequence[float]) -> float:
    t, p = np.asarray(truth, float), np.asarray(pred, float)
    best = int(np.argmax(p))
    return float(average_ranks(t)[best] > len(t) / 2)


def ndcg_at_k(truth: Sequence[float], pred: Sequence[float], k: int = 3) -> float:
    t, p = np.asarray(truth, float), np.asarray(pred, float)
    gains = np.maximum(t - t.min(), 0.0)
    if not gains.any():
        return float("nan")
    order = np.argsort(-p, kind="stable")[:k]
    ideal = np.sort(gains)[::-1][:k]
    disc = 1.0 / np.log2(np.arange(2, 2 + k, dtype=float))
    dcg = float(np.sum(gains[order] * disc[:len(order)]))
    idcg = float(np.sum(ideal * disc[:len(ideal)]))
    return dcg / idcg if idcg > 0 else float("nan")


# ----------------------------------------------------------------- one query
def query_metrics(items: pd.DataFrame) -> dict[str, float]:
    """Metrics of one query from its joined items (``y``, ``score``, ``est_lrr``, ``lo``, ``hi``, ``abstain``).

    A query with any abstained candidate is ``abstained`` (the method could not rank the
    full candidate set): its ranking metrics are ``nan`` and it counts in the abstention
    rate (see the module docstring for why a partial answer is not scored).
    """
    n = len(items)
    out: dict[str, float] = {m: float("nan") for m in QUERY_METRICS}
    out["n_candidates"] = float(n)
    out["abstained"] = float(bool(items["abstain"].any())) if n else 1.0
    if n < 2 or out["abstained"]:
        out["n_estimates"] = 0.0
        return out
    y = items["y"].to_numpy(float)
    score = items["score"].to_numpy(float).copy()
    score[items["abstain"].to_numpy(bool)] = -np.inf
    out["top1_hit"] = top1_hit(y, score)
    out["top1_chance"] = 1.0 / n
    out["tophalf_hit"] = tophalf_hit(y, score)
    conc, comp = concordance(y, score)
    out["c_index"] = conc / comp if comp else float("nan")
    out["c_concordant"], out["c_comparable"] = float(conc), float(comp)
    out["ndcg3"] = ndcg_at_k(y, score, 3) if n >= 3 else float("nan")
    out["spearman"] = spearman(y, score)
    est = items["est_lrr"].to_numpy(float) if "est_lrr" in items else np.full(n, np.nan)
    ok = np.isfinite(est) & ~items["abstain"].to_numpy(bool)
    out["n_estimates"] = float(ok.sum())
    if ok.any():
        out["rmse"] = float(np.sqrt(np.mean((est[ok] - y[ok]) ** 2)))
        out["sign_acc"] = float(np.mean(np.sign(est[ok]) == np.sign(y[ok])))
        lo = items["lo"].to_numpy(float) if "lo" in items else np.full(n, np.nan)
        hi = items["hi"].to_numpy(float) if "hi" in items else np.full(n, np.nan)
        iv = ok & np.isfinite(lo) & np.isfinite(hi)
        if iv.any():
            out["coverage80"] = float(np.mean((lo[iv] <= y[iv]) & (y[iv] <= hi[iv])))
            out["width80"] = float(np.median(hi[iv] - lo[iv]))
    return out


# ----------------------------------------------------------------- many queries
def per_query_table(predictions: pd.DataFrame, items: pd.DataFrame) -> pd.DataFrame:
    """One row per ``(method, split, rep, query_id)`` with the query metrics.

    ``predictions`` holds the harness prediction format; ``items`` the ground truth
    (``query_id, practice_id, y``). Candidates without a prediction row are treated as
    abstained.
    """
    truth = items[["query_id", "practice_id", "y"]]
    cols = ["method", "split", "rep", "fold", "query_id", "practice_id", "score", "est_lrr", "lo", "hi", "abstain"]
    preds = predictions[[c for c in cols if c in predictions.columns]]
    rows: list[dict[str, Any]] = []
    for (method, split, rep), block in preds.groupby(["method", "split", "rep"], sort=True):
        fold_of = block.groupby("query_id")["fold"].first() if "fold" in block.columns else None
        joined = truth[truth["query_id"].isin(block["query_id"].unique())].merge(
            block, on=["query_id", "practice_id"], how="left")
        joined["abstain"] = joined["abstain"].fillna(True).astype(bool)
        joined["score"] = joined["score"].fillna(-np.inf)
        for qid, q in joined.groupby("query_id", sort=True):
            m = query_metrics(q)
            m.update(method=method, split=split, rep=int(rep), query_id=qid,
                     fold=int(fold_of[qid]) if fold_of is not None and qid in fold_of.index else -1)
            rows.append(m)
    return pd.DataFrame(rows)


def summarise_rep(pq: pd.DataFrame) -> dict[str, float]:
    """Headline metrics of one ``(method, split, rep)`` block of the per-query table."""
    answered = pq[pq["abstained"] == 0]
    out: dict[str, float] = {
        "n_queries": float(len(pq)), "n_answered": float(len(answered)),
        "abstention_rate": float(pq["abstained"].mean()) if len(pq) else float("nan"),
    }
    for m in ("top1_hit", "top1_chance", "tophalf_hit", "c_index", "ndcg3", "rmse", "sign_acc", "coverage80", "width80"):
        v = answered[m].to_numpy(float) if len(answered) else np.array([])
        v = v[np.isfinite(v)]
        out[m] = float(v.mean()) if v.size else float("nan")
    rho = answered["spearman"].to_numpy(float) if len(answered) else np.array([])
    rho = rho[np.isfinite(rho)]
    out["spearman_median"] = float(np.median(rho)) if rho.size else float("nan")
    out["spearman_mean"] = float(rho.mean()) if rho.size else float("nan")
    # pair-pooled C-index (sum of concordant over sum of comparable pairs): the P7 definition
    # (``evaluate.ranking_metrics``), reported beside the per-query mean for continuity
    comp = answered["c_comparable"].to_numpy(float) if len(answered) else np.array([])
    conc = answered["c_concordant"].to_numpy(float) if len(answered) else np.array([])
    ok = np.isfinite(comp) & np.isfinite(conc)
    out["c_index_pooled"] = float(conc[ok].sum() / comp[ok].sum()) if ok.any() and comp[ok].sum() > 0 else float("nan")
    return out


def _mean_sd(values: Iterable[float]) -> dict[str, float]:
    arr = np.array([float(v) for v in values], dtype=float)
    arr = arr[np.isfinite(arr)]
    return {"mean": float(arr.mean()) if arr.size else float("nan"),
            "sd": float(arr.std(ddof=1)) if arr.size > 1 else 0.0, "n_reps": int(arr.size)}


def aggregate(pq: pd.DataFrame) -> dict[str, dict[str, dict[str, Any]]]:
    """``{method: {split: {metric: {mean, sd, n_reps}}}}`` across repetitions."""
    out: dict[str, dict[str, dict[str, Any]]] = {}
    for (method, split), block in pq.groupby(["method", "split"], sort=True):
        reps = [summarise_rep(b) for _, b in block.groupby("rep", sort=True)]
        agg = {m: _mean_sd(r[m] for r in reps) for m in reps[0]} if reps else {}
        out.setdefault(method, {})[split] = agg
    return out


def bootstrap(pq: pd.DataFrame, metric: str, n_boot: int = 1000, seed: int = 0) -> dict[str, float]:
    """Query-level bootstrap 95 % interval of a metric (per-query values averaged across reps).

    ``spearman_median`` bootstraps the median of the per-query Spearman values.
    """
    key = "spearman" if metric == "spearman_median" else metric
    per_q = pq[pq["abstained"] == 0].groupby("query_id")[key].mean().to_numpy(float)
    per_q = per_q[np.isfinite(per_q)]
    if per_q.size == 0:
        return {"lo": float("nan"), "hi": float("nan"), "n": 0}
    rng = np.random.default_rng(seed)
    stat = np.median if metric == "spearman_median" else np.mean
    draws = np.array([stat(per_q[rng.integers(0, per_q.size, per_q.size)]) for _ in range(n_boot)])
    return {"lo": float(np.percentile(draws, 2.5)), "hi": float(np.percentile(draws, 97.5)), "n": int(per_q.size)}


def breakdown(pq: pd.DataFrame, queries: pd.DataFrame, by: str, metrics: Sequence[str] = ("top1_hit", "c_index", "ndcg3"),
              min_cell: int = MIN_CELL, explode: str | None = None) -> pd.DataFrame:
    """Mean metric per cell of a query attribute (``by``) for every ``(method, split)``.

    Values are averaged over repetitions first (one value per query), then over queries.
    Cells with fewer than ``min_cell`` queries carry ``"n < 20"`` instead of a number
    (``value`` column is the string; ``n`` the count). ``explode`` splits a ``;``-joined
    attribute (challenge ids) so a query counts in every cell it belongs to.
    """
    attrs = queries.set_index("query_id")
    rows = []
    q = pq[pq["abstained"] == 0].groupby(["method", "split", "query_id"])[list(metrics)].mean().reset_index()
    q[by] = q["query_id"].map(attrs[by] if by in attrs.columns else pd.Series(dtype=object))
    if explode:
        q[by] = q[by].map(lambda s: [x for x in str(s).split(explode) if x] if isinstance(s, str) else [])
        q = q.explode(by)
    q[by] = q[by].fillna("none").astype(str)
    for (method, split, cell), b in q.groupby(["method", "split", by], sort=True):
        n = int(b["query_id"].nunique())
        for m in metrics:
            v = b[m].to_numpy(float)
            v = v[np.isfinite(v)]
            value: Any = (f"n < {min_cell}" if n < min_cell else (float(v.mean()) if v.size else float("nan")))
            rows.append({"method": method, "split": split, by: cell, "n": n, "metric": m, "value": value})
    return pd.DataFrame(rows)


def coverage_accuracy_curve(pq: pd.DataFrame, predictions: pd.DataFrame, items: pd.DataFrame,
                            method: str, split: str, metric: str = "top1_hit", steps: int = 20) -> pd.DataFrame:
    """Accuracy of the answered queries when the least confident ones are dropped first.

    Confidence of a query = the method's score margin between its top two candidates
    (an engine without a numeric notion of confidence has margin 0 everywhere, which
    gives a flat curve). Returns ``coverage`` (share of queries kept) and ``accuracy``.
    """
    p = predictions[(predictions["method"] == method) & (predictions["split"] == split) & (~predictions["abstain"])]
    margins = {}
    for qid, g in p.groupby("query_id"):
        s = np.sort(g["score"].to_numpy(float))[::-1]
        margins[qid] = float(s[0] - s[1]) if len(s) > 1 else 0.0
    per_q = pq[(pq["method"] == method) & (pq["split"] == split) & (pq["abstained"] == 0)].groupby("query_id")[metric].mean()
    per_q = per_q[np.isfinite(per_q)]
    if per_q.empty:
        return pd.DataFrame(columns=["coverage", "accuracy"])
    order = per_q.index.map(lambda q: margins.get(q, 0.0))
    df = pd.DataFrame({"acc": per_q.to_numpy(float), "margin": np.asarray(order, float)}).sort_values("margin", ascending=False)
    rows = []
    for k in range(1, steps + 1):
        keep = max(1, int(round(len(df) * k / steps)))
        rows.append({"coverage": keep / len(df), "accuracy": float(df["acc"].iloc[:keep].mean())})
    return pd.DataFrame(rows)


def calibration_table(predictions: pd.DataFrame, items: pd.DataFrame, method: str, split: str,
                      bins: int = 8) -> pd.DataFrame:
    """Observed ``y`` versus estimated ``est_lrr`` in quantile bins (for the calibration plot)."""
    p = predictions[(predictions["method"] == method) & (predictions["split"] == split) & (~predictions["abstain"])]
    j = p.merge(items[["query_id", "practice_id", "y"]], on=["query_id", "practice_id"])
    j = j[np.isfinite(j["est_lrr"].astype(float))]
    if j.empty:
        return pd.DataFrame(columns=["bin", "est_mean", "y_mean", "n", "coverage80"])
    j = j.copy()
    j["bin"] = pd.qcut(j["est_lrr"].rank(method="first"), q=min(bins, len(j)), labels=False)
    rows = []
    for b, g in j.groupby("bin"):
        cov = ((g["lo"] <= g["y"]) & (g["y"] <= g["hi"])).mean() if g["lo"].notna().any() else float("nan")
        rows.append({"bin": int(b), "est_mean": float(g["est_lrr"].mean()), "y_mean": float(g["y"].mean()),
                     "n": int(len(g)), "coverage80": float(cov)})
    return pd.DataFrame(rows)


def expected_random(n_candidates: Sequence[int], seed: int = 0, n_perm: int = 2000) -> dict[str, float]:
    """Analytic (or enumerated) expectations of a random ranker on queries with these sizes.

    top-1 = mean 1/n; top-half = mean ``ceil(n/2)/n`` (ranks above n/2); C-index = 0.5;
    Spearman median = 0;
    NDCG@3 is averaged over all permutations of ``n`` with gains ``n-1, ..., 0``, which is the
    expectation for distinct truths up to the gain profile; it is reported here only for the
    unit test, where the truths are evenly spaced.
    """
    from itertools import permutations

    ns = [int(n) for n in n_candidates]
    top1 = float(np.mean([1.0 / n for n in ns]))
    tophalf = float(np.mean([math.ceil(n / 2) / n for n in ns]))
    ndcgs = []
    for n in ns:
        if n < 3:
            continue
        gains = np.arange(n, dtype=float)[::-1]
        disc = 1.0 / np.log2(np.arange(2, 5, dtype=float))
        idcg = float(np.sum(np.sort(gains)[::-1][:3] * disc))
        vals = [float(np.sum(gains[list(perm[:3])] * disc)) / idcg for perm in permutations(range(n))] if n <= 7 else None
        if vals is None:
            rng = np.random.default_rng(seed)
            vals = [float(np.sum(gains[rng.permutation(n)[:3]] * disc)) / idcg for _ in range(n_perm)]
        ndcgs.append(float(np.mean(vals)))
    return {"top1_hit": top1, "tophalf_hit": tophalf, "c_index": 0.5, "spearman_median": 0.0,
            "ndcg3": float(np.mean(ndcgs)) if ndcgs else float("nan")}


# ----------------------------------------------------------------- E5 Part 0: fair comparison
FILL_SUFFIX = "+prior"


def fill_abstentions(preds: pd.DataFrame, filler: str = "practice_prior", suffix: str = FILL_SUFFIX) -> pd.DataFrame:
    """Full-coverage variants: where a method abstains on a query, that query's rows are
    replaced by the filler method's rows and the method is labelled ``<method>+prior``.

    A method that never abstains gets no variant (its own rows are already full coverage);
    the filler itself and existing ``+prior`` variants are left alone, so the call is
    idempotent. The filled rows keep the filler's estimates and intervals and carry
    ``lead_source = prior_fill:<filler lead source>`` so the share of filled queries stays
    visible.
    """
    filler_rows = preds[preds["method"] == filler]
    if filler_rows.empty:
        return preds
    keys = ["split", "rep", "query_id"]
    existing = set(preds["method"].unique())
    f_index = pd.MultiIndex.from_frame(filler_rows[keys])
    out = [preds]
    for m in sorted(existing):
        if m == filler or m.endswith(suffix) or (m + suffix) in existing:
            continue
        block = preds[preds["method"] == m]
        abst = block.groupby(keys)["abstain"].any()
        abst_keys = abst[abst].index
        if len(abst_keys) == 0:
            continue
        b_index = pd.MultiIndex.from_frame(block[keys])
        kept = block[~b_index.isin(abst_keys)].copy()
        fill = filler_rows[f_index.isin(abst_keys)].copy()
        fill["lead_source"] = "prior_fill:" + fill["lead_source"].astype(str)
        new = pd.concat([kept, fill], ignore_index=True)
        new["method"] = m + suffix
        out.append(new)
    return pd.concat(out, ignore_index=True)


def common_subset(pq: pd.DataFrame, methods: Sequence[str]) -> dict[str, Any]:
    """Queries that every listed method answered in every repetition, per split.

    Returns ``{split: {"n": size, "query_ids": [...], "per_query": frame}}``; the frame is
    the per-query table restricted to the subset and the methods, ready for
    :func:`aggregate`.
    """
    out: dict[str, Any] = {}
    sub = pq[pq["method"].isin(list(methods))]
    for split, block in sub.groupby("split", sort=True):
        answered = block.groupby(["query_id", "method"])["abstained"].max().unstack("method")
        answered = answered.reindex(columns=list(methods))
        ok = answered.fillna(1).eq(0).all(axis=1)
        ids = sorted(answered.index[ok])
        out[split] = {"n": len(ids), "query_ids": ids, "per_query": block[block["query_id"].isin(ids)]}
    return out


def paired_bootstrap(pq: pd.DataFrame, a: str, b: str, metrics: Sequence[str] = ("top1_hit", "c_index", "ndcg3"),
                     n_boot: int = 1000, seed: int = 0) -> dict[str, dict[str, Any]]:
    """Paired bootstrap 95 % interval of the mean difference ``a - b`` per split.

    Per-query values are averaged across repetitions on the queries both methods
    answered in every repetition; queries are resampled 1,000 times (seeded). ``beats`` is
    true when the interval excludes zero on the positive side.
    """
    out: dict[str, dict[str, Any]] = {}
    for split, block in pq[pq["method"].isin([a, b])].groupby("split", sort=True):
        subset = common_subset(block, [a, b])[split]
        per = subset["per_query"]
        res: dict[str, Any] = {"n": subset["n"]}
        for m in metrics:
            va = per[per["method"] == a].groupby("query_id")[m].mean()
            vb = per[per["method"] == b].groupby("query_id")[m].mean()
            d = (va - vb.reindex(va.index)).to_numpy(float)
            d = d[np.isfinite(d)]
            if d.size == 0:
                res[m] = {"diff": float("nan"), "lo": float("nan"), "hi": float("nan"), "beats": False, "n": 0}
                continue
            rng = np.random.default_rng(seed)
            draws = np.array([d[rng.integers(0, d.size, d.size)].mean() for _ in range(n_boot)])
            lo, hi = float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5))
            res[m] = {"diff": float(d.mean()), "lo": lo, "hi": hi, "beats": bool(lo > 0), "n": int(d.size)}
        out[split] = res
    return out
