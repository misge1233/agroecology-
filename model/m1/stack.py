"""The stacker and fallback chain of Methodology 1 v2 (E5 Part 2.5).

For every candidate the available component scores (regressor estimate, ranker score,
matched-studies estimate and its precision, the shrunken prior) are combined by a small
ridge model on standardised scores, fitted on the **inner out-of-fold** component
predictions of the training queries; one ridge per availability pattern (which of
regressor, ranker and matched studies exist for the candidate; the prior always does), so
a missing component never silently becomes zero. On the inner folds the ridge is compared
with plain rank averaging; ``mode="auto"`` keeps the ridge only when it beats rank
averaging there (decision recorded in the fit summary).

``lead_source`` is the component with the largest weighted contribution ``|w_j x z_j|``:
``model`` (regressor or ranker), ``matched_studies`` or ``prior``, which map to the fusion
labels model-led, study-led and documented.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge

from model import metrics as mm
from model.m1 import inner

COMPONENTS = ("reg", "rank", "matched", "matched_prec", "prior")
PATTERN_KEYS = ("reg", "rank", "matched")
SOURCE_OF = {"reg": "model", "rank": "model", "matched": "matched_studies", "matched_prec": "matched_studies", "prior": "prior"}


def rank_average(frame: pd.DataFrame, cols: list[str]) -> np.ndarray:
    """Per query, the mean of the available components' ranks (1 = worst), as a score."""
    out = np.zeros(len(frame))
    for _, idx in frame.groupby("qkey").indices.items():
        block = frame.iloc[idx]
        ranks = []
        for c in cols:
            v = block[c].to_numpy(float)
            if np.isfinite(v).all() and len(v) > 1:
                ranks.append(mm.average_ranks(v))
        out[idx] = np.mean(ranks, axis=0) if ranks else 0.0
    return out


class Stacker:
    def __init__(self, mode: str = "auto", alpha: float = 1.0) -> None:
        self.mode = mode          # "auto" | "ridge" | "rank_avg"
        self.alpha = float(alpha)
        self.mu: dict[str, float] = {}
        self.sd: dict[str, float] = {}
        self.models: dict[tuple[bool, ...], Ridge] = {}
        self.chosen = "rank_avg"
        self.summary: dict[str, Any] = {}

    # ------------------------------------------------------------ helpers
    @staticmethod
    def pattern(row: pd.Series) -> tuple[bool, ...]:
        return tuple(bool(np.isfinite(row[k])) for k in PATTERN_KEYS)

    def _z(self, frame: pd.DataFrame, cols: list[str]) -> np.ndarray:
        return np.column_stack([(frame[c].to_numpy(float) - self.mu[c]) / self.sd[c] for c in cols])

    @staticmethod
    def _cols(pattern: tuple[bool, ...]) -> list[str]:
        cols = [k for k, on in zip(PATTERN_KEYS, pattern) if on]
        if "matched" in cols:
            cols.append("matched_prec")
        cols.append("prior")
        return cols

    # ------------------------------------------------------------ fit
    def fit(self, oof: pd.DataFrame) -> "Stacker":
        """``oof``: inner out-of-fold component predictions per training item with ``y`` and ``qkey``."""
        for c in COMPONENTS:
            v = oof[c].to_numpy(float) if c in oof else np.full(len(oof), np.nan)
            ok = np.isfinite(v)
            self.mu[c] = float(v[ok].mean()) if ok.any() else 0.0
            self.sd[c] = float(v[ok].std()) if ok.sum() > 1 and v[ok].std() > 0 else 1.0
        patterns = oof.apply(self.pattern, axis=1)
        for pat in sorted(set(patterns)):
            sel = oof[patterns == pat]
            if len(sel) < 10:
                continue
            cols = self._cols(pat)
            self.models[pat] = Ridge(alpha=self.alpha).fit(self._z(sel, cols), sel["y"].to_numpy(float))
        if self.mode == "ridge":
            self.chosen = "ridge"
        elif self.mode == "rank_avg":
            self.chosen = "rank_avg"
        else:
            ridge_score = inner.score_items(oof, self._ridge_scores(oof))
            avg_score = inner.score_items(oof, rank_average(oof, [k for k in PATTERN_KEYS] + ["prior"]))
            self.chosen = "ridge" if inner.better(ridge_score, avg_score) else "rank_avg"
            self.summary = {"ridge": ridge_score, "rank_avg": avg_score}
        self.summary["chosen"] = self.chosen
        self.summary["patterns"] = {"".join("1" if b else "0" for b in p): {c: float(w) for c, w in zip(self._cols(p), m.coef_)}
                                    for p, m in self.models.items()}
        return self

    def _ridge_scores(self, frame: pd.DataFrame) -> np.ndarray:
        out = np.full(len(frame), np.nan)
        patterns = frame.apply(self.pattern, axis=1)
        for i, (pat, (_, row)) in enumerate(zip(patterns, frame.iterrows())):
            model = self.models.get(pat)
            if model is None:  # no sub-model for this pattern: the prior alone
                out[i] = float(row["prior"])
                continue
            cols = self._cols(pat)
            out[i] = float(model.predict(self._z(frame.iloc[[i]], cols))[0])
        return out

    # ------------------------------------------------------------ predict
    def predict(self, frame: pd.DataFrame) -> tuple[np.ndarray, list[str]]:
        """``(scores, lead sources)`` for the candidates of one or more queries (``qkey`` column)."""
        leads: list[str] = []
        if self.chosen == "ridge":
            scores = self._ridge_scores(frame)
            patterns = frame.apply(self.pattern, axis=1)
            for i, (pat, (_, row)) in enumerate(zip(patterns, frame.iterrows())):
                model = self.models.get(pat)
                if model is None:
                    leads.append("prior")
                    continue
                cols = self._cols(pat)
                z = self._z(frame.iloc[[i]], cols)[0]
                contrib: dict[str, float] = {}
                for c, w, zz in zip(cols, model.coef_, z):
                    contrib[SOURCE_OF[c]] = contrib.get(SOURCE_OF[c], 0.0) + abs(float(w) * float(zz))
                leads.append(max(contrib, key=lambda k: (contrib[k], k)))
        else:
            cols = list(PATTERN_KEYS) + ["prior"]
            scores = rank_average(frame, cols)
            # every available component contributes rank_j / K to the mean: the largest contribution
            # is the component that ranks the candidate highest (ties: model, matched studies, prior)
            leads = [""] * len(frame)
            order = {"model": 0, "matched_studies": 1, "prior": 2}
            for _, idx in frame.groupby("qkey").indices.items():
                block = frame.iloc[idx]
                ranks: dict[str, np.ndarray] = {}
                for c in cols:
                    v = block[c].to_numpy(float)
                    if np.isfinite(v).all() and len(v) > 1:
                        ranks[c] = mm.average_ranks(v)
                for i, pos in enumerate(idx):
                    best = max(ranks, key=lambda c: (ranks[c][i], -order[SOURCE_OF[c]])) if ranks else "prior"
                    leads[pos] = SOURCE_OF[best]
        return scores, leads
