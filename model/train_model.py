#!/usr/bin/env python3
"""
train_model.py  -  Phase 2: train & select the CSA response-ratio model.

- 13 features (see feature_selection_report.md). Target: log_response_ratio.
- GroupKFold(5) by Study_No_. Compares: mean-baseline (practice x indicator),
  RandomForest, HistGradientBoosting. Reports overall + per-indicator + per-source.
- Derives per-indicator confidence flags (from grouped OOF R2).
- Fits the best model on ALL data; saves model + category encoders + metadata to
  artifacts/csa_model.joblib and artifacts/model_metrics.json.

Pipeline position:  merged -> (build_practice_family) -> final -> (this script)
  in   data/processed/CSA_ERA_final_model_ready.csv   (--dataset)
  out  model/artifacts/{csa_model.joblib, model_metrics.json}   (--artifacts)
  and, with --copy-to (default app/backend/artifacts), the copies the API
  serves. See docs/reports/merged_dataset_notes.md.

Usage:
    python model/train_model.py
    python model/train_model.py --dataset X.csv --artifacts out/ --no-copy

Requires: pandas, numpy, scikit-learn, joblib.
"""
import argparse, shutil, pandas as pd, numpy as np, os, json, joblib
from pathlib import Path
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.model_selection import GroupKFold
from sklearn.metrics import r2_score, mean_squared_error

REPO_ROOT=Path(__file__).resolve().parents[1]
DATASET_PATH=REPO_ROOT/"data"/"processed"/"CSA_ERA_final_model_ready.csv"
ARTIFACTS_DIR=REPO_ROOT/"model"/"artifacts"
BACKEND_ARTIFACTS=REPO_ROOT/"app"/"backend"/"artifacts"

CAT=["CSA_practices","practice_family","Crop_group","crop_type","aez_belt","Indicator","land_cover"]
NUM=["Rainfall","Altitude_r","temp_mean_annual","precip_seasonality","slope","soil_clay"]
FEATURES=CAT+NUM
TARGET="log_response_ratio"; GROUP="Study_No_"
cat_mask=[c in CAT for c in FEATURES]

def build_cat_maps(df):
    return {c:{v:i for i,v in enumerate(sorted(df[c].astype(str).unique()))} for c in CAT}

def encode(df, cmaps):
    X=pd.DataFrame(index=df.index)
    for c in FEATURES:
        if c in CAT:
            X[c]=df[c].astype(str).map(cmaps[c]).fillna(-1).astype(int)
        else:
            X[c]=df[c].astype(float)
    return X[FEATURES]

def gkf_eval(make_model, X, y, g, ind, src):
    oof=np.full(len(y),np.nan)
    for tr,te in GroupKFold(5).split(X,y,g):
        m=make_model(); m.fit(X.iloc[tr],y[tr]); oof[te]=m.predict(X.iloc[te])
    r2=r2_score(y,oof); rmse=mean_squared_error(y,oof)**.5
    per_ind={i:(int((ind==i).sum()),round(r2_score(y[ind==i],oof[ind==i]),3)) for i in sorted(set(ind))}
    per_src={s:round(r2_score(y[src==s],oof[src==s]),3) for s in sorted(set(src))}
    return r2,rmse,oof,per_ind,per_src

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--dataset",type=Path,default=DATASET_PATH,
                        help="final model-ready csv to train on")
    parser.add_argument("--artifacts",type=Path,default=ARTIFACTS_DIR,
                        help="directory for csa_model.joblib + model_metrics.json")
    parser.add_argument("--copy-to",type=Path,default=BACKEND_ARTIFACTS,
                        help="also copy both artifacts here (the API's copies)")
    parser.add_argument("--no-copy",dest="copy",action="store_false",
                        help="skip the copy step")
    args=parser.parse_args(argv)
    ART=args.artifacts; ART.mkdir(parents=True,exist_ok=True)

    df=pd.read_csv(args.dataset)
    print("dataset:",args.dataset,df.shape,flush=True)
    cmaps=build_cat_maps(df)
    X=encode(df,cmaps); y=df[TARGET].values; g=df[GROUP].values
    ind=df["Indicator"].values; src=df["source"].values

    # --- baseline: mean log-ratio per (CSA_practices, Indicator), global fallback (vectorized) ---
    key=["CSA_practices","Indicator"]; b=np.full(len(y),np.nan)
    for tr,te in GroupKFold(5).split(X,y,g):
        t=df.iloc[tr]; km=t.groupby(key)[TARGET].mean(); gm=t[TARGET].mean()
        keys=list(zip(df.iloc[te]["CSA_practices"],df.iloc[te]["Indicator"]))
        b[te]=[km.get(k,gm) for k in keys]
    print("Baseline (practice x indicator mean): R2 %.3f RMSE %.3f"%(
        r2_score(y,b),mean_squared_error(y,b)**.5),flush=True)

    models={
     "RandomForest":lambda:RandomForestRegressor(n_estimators=150,min_samples_leaf=3,
                        n_jobs=-1,random_state=0),
     "HistGBM":lambda:HistGradientBoostingRegressor(categorical_features=cat_mask,
                        learning_rate=0.06,max_iter=400,l2_regularization=1.0,
                        min_samples_leaf=20,random_state=0),
    }
    results={}; oofs={}
    for name,mk in models.items():
        r2,rmse,oof,pi,ps=gkf_eval(mk,X,y,g,ind,src)
        results[name]=dict(r2=r2,rmse=rmse,per_indicator=pi,per_source=ps); oofs[name]=oof
        print(f"\n=== {name}: R2 {r2:.3f} RMSE {rmse:.3f} ===",flush=True)
        print("  per indicator:",pi); print("  per source:",ps,flush=True)

    best=max(results,key=lambda k:results[k]["r2"])
    print("\nBEST:",best,flush=True)

    # per-indicator confidence from best model's stored OOF
    pi=results[best]["per_indicator"]
    conf={i:("high" if r>=0.10 else ("medium" if r>=0.0 else "low")) for i,(n,r) in pi.items()}

    # fit best on ALL data
    final=models[best](); final.fit(X,y)
    joblib.dump({"model":final,"cat_maps":cmaps,"features":FEATURES,"cat":CAT,"num":NUM,
                 "cat_mask":cat_mask,"target":TARGET,"model_name":best,
                 "indicator_confidence":conf}, ART/"csa_model.joblib")
    meta=dict(model=best,cv_r2=results[best]["r2"],cv_rmse=results[best]["rmse"],
              baseline_r2=r2_score(y,b),per_indicator=results[best]["per_indicator"],
              per_source=results[best]["per_source"],indicator_confidence=conf,
              n_rows=len(df),n_groups=int(df[GROUP].nunique()),features=FEATURES)
    json.dump(meta,open(ART/"model_metrics.json","w"),indent=2,default=str)
    print("\nsaved",ART/"csa_model.joblib","+",ART/"model_metrics.json")
    print("indicator confidence:",conf)

    if args.copy and args.copy_to.resolve()!=ART.resolve():
        args.copy_to.mkdir(parents=True,exist_ok=True)
        for name in ("csa_model.joblib","model_metrics.json"):
            shutil.copyfile(ART/name,args.copy_to/name)
        print("copied both artifacts to",args.copy_to)
    return 0

if __name__=="__main__":
    raise SystemExit(main())
