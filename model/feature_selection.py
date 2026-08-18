#!/usr/bin/env python3
"""
feature_selection.py  -  Phase 1: assess feature relevance & redundancy.

- HistGradientBoostingRegressor (handles categoricals natively; no target-encoding leakage).
- GroupKFold by Study_No_ for an honest performance estimate (+ per-indicator R2).
- Grouped permutation importance on a held-out group split.
- Numeric correlation matrix to flag multicollinearity.

Design-required features are always kept (CSA_practices, practice_family, Indicator);
this analysis informs which CONTEXT features to keep/prune.

Requires: pandas, numpy, scikit-learn (>=1.1).
"""
import pandas as pd, numpy as np, os
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.model_selection import GroupKFold, GroupShuffleSplit
from sklearn.inspection import permutation_importance
from sklearn.metrics import r2_score, mean_squared_error

B=os.path.dirname(os.path.abspath(__file__))
F=os.path.join(B,"dataset","CSA_ERA_final_model_ready.csv")
TARGET="log_response_ratio"; GROUP="Study_No_"
CAT=["CSA_practices","practice_family","Crop_group","crop_type","aez_belt","Indicator","land_cover"]
NUM=["Rainfall","Altitude_r","slope","temp_mean_annual","precip_seasonality","lgp_days",
     "soil_clay","soil_ph","soil_soc"]
FEATURES=CAT+NUM

def encode(df):
    X=df[FEATURES].copy()
    for c in CAT:
        X[c]=X[c].astype("category").cat.codes   # ordinal codes; -1 if missing (none here)
    return X
cat_mask=[c in CAT for c in FEATURES]

def main():
    df=pd.read_csv(F)
    X=encode(df); y=df[TARGET].values; g=df[GROUP].values
    ind=df["Indicator"].values

    # ---- GroupKFold performance ----
    gkf=GroupKFold(n_splits=5); r2s=[]; rmses=[]; oof=np.full(len(y),np.nan)
    for tr,te in gkf.split(X,y,g):
        m=HistGradientBoostingRegressor(categorical_features=cat_mask,
              learning_rate=0.06,max_iter=500,max_depth=None,
              l2_regularization=1.0,random_state=0)
        m.fit(X.iloc[tr],y[tr])
        p=m.predict(X.iloc[te]); oof[te]=p
        r2s.append(r2_score(y[te],p)); rmses.append(mean_squared_error(y[te],p)**.5)
    print("=== GroupKFold(5) by Study_No_ ===")
    print("R2  per fold:", [round(x,3) for x in r2s], "| mean %.3f"%np.mean(r2s))
    print("RMSE per fold:", [round(x,3) for x in rmses], "| mean %.3f"%np.mean(rmses))
    print("\n=== out-of-fold R2 per indicator ===")
    for i in sorted(set(ind)):
        mask=ind==i
        print(f"  {i:22s} n={mask.sum():5d}  R2={r2_score(y[mask],oof[mask]):.3f}")

    # ---- grouped permutation importance (held-out groups) ----
    tr,te=next(GroupShuffleSplit(n_splits=1,test_size=0.25,random_state=0).split(X,y,g))
    m=HistGradientBoostingRegressor(categorical_features=cat_mask,learning_rate=0.06,
          max_iter=500,l2_regularization=1.0,random_state=0).fit(X.iloc[tr],y[tr])
    pi=permutation_importance(m,X.iloc[te],y[te],n_repeats=10,random_state=0,
                              scoring="r2")
    imp=pd.Series(pi.importances_mean,index=FEATURES).sort_values(ascending=False)
    print("\n=== permutation importance (drop in R2 on held-out studies) ===")
    for k,v in imp.items(): print(f"  {k:20s} {v:+.4f}")

    # ---- numeric multicollinearity ----
    print("\n=== |corr|>0.8 among numeric features ===")
    corr=df[NUM].corr().abs()
    pairs=[(a,b,round(corr.loc[a,b],2)) for i,a in enumerate(NUM) for b in NUM[i+1:] if corr.loc[a,b]>0.8]
    print(pairs if pairs else "  none")

if __name__=="__main__":
    main()
