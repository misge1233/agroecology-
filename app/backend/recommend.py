#!/usr/bin/env python3
"""
recommend.py  -  Phase 3: the CSA practice recommender.

recommend(lat, lon, practice_family, indicator, crop_type=None, top_n=3) -> dict

Flow:
  1. Extract context from lat/long: aez_belt + stack features (nearest-valid fallback).
  2. Enumerate candidate CSA_practices seen in the data for the chosen practice_family.
  3. Predict log_response_ratio for each candidate (candidate + fixed context + indicator).
  4. Convert to % change, rank by the indicator's "better" direction.
  5. Return a TWO-TIER dict:
       - "recommendations": clean, short list for the UI (practice + one-line effect).
       - "details": evidence count, confidence, resolved context, model %s
                    (used ONLY when the user asks for an explanation).

Requires: pandas, numpy, rasterio, joblib.
"""
import os, json, numpy as np, pandas as pd, joblib, rasterio
from rasterio.windows import Window

B=os.path.dirname(os.path.abspath(__file__))
ART=os.path.join(B,"artifacts","csa_model.joblib")
DATA=os.path.join(B,"dataset","CSA_ERA_final_model_ready.csv")
LAYER_DIR=os.path.join(B,"layers")
AEZ_LOOK=os.path.join(B,"aez_belt_lookup.csv")

# indicator direction: +1 higher-is-better, -1 lower-is-better
DIRECTION={"yield":1,"biomass yield":1,"income":1,"water use efficiency":1,"SOM content":1,
           "soil loss":-1,"runoff":-1}
# stack layers used as context (model uses a subset; extras kept for explanation)
STACK={"precip_annual":"Rainfall","temp_mean_annual":"temp_mean_annual",
       "precip_seasonality":"precip_seasonality","elevation":"Altitude_r","slope":"slope",
       "soil_clay":"soil_clay","land_cover":"land_cover",
       # explanation-only extras:
       "lgp_days":"lgp_days","soil_ph":"soil_ph","soil_soc":"soil_soc"}
MAXR=120

_BUNDLE=None; _DF=None; _AEZ=None
def _load():
    global _BUNDLE,_DF,_AEZ
    if _BUNDLE is None:
        _BUNDLE=joblib.load(ART)
        _DF=pd.read_csv(DATA)
        _AEZ={}
        import csv
        with open(AEZ_LOOK) as f:
            for r in csv.DictReader(f): _AEZ[int(r["value_OBJECTID"])]=r["Agro_zone"]
    return _BUNDLE,_DF,_AEZ

def _nearest(src,lon,lat,nd):
    r,c=src.index(lon,lat); H,W=src.height,src.width
    if not(0<=r<H and 0<=c<W): return None
    r0,r1=max(0,r-MAXR),min(H,r+MAXR+1); c0,c1=max(0,c-MAXR),min(W,c+MAXR+1)
    bl=src.read(1,window=Window(c0,r0,c1-c0,r1-r0))
    v=(bl!=nd)&~np.isnan(bl) if bl.dtype.kind=='f' else (bl!=nd)
    if not v.any(): return None
    rr,cc=np.where(v); d=(rr-(r-r0))**2+(cc-(c-c0))**2
    return bl[rr[int(d.argmin())],cc[int(d.argmin())]].item()

def extract_context(lat,lon):
    ctx={}
    for fn,col in STACK.items():
        with rasterio.open(os.path.join(LAYER_DIR,fn+".tif")) as src:
            nd=src.nodata; val=list(src.sample([(lon,lat)]))[0][0]
            if val is None or (nd is not None and val==nd) or (isinstance(val,float) and np.isnan(val)):
                val=_nearest(src,lon,lat,nd)
            ctx[col]=None if val is None else (int(val) if col=="land_cover" else round(float(val),3))
    with rasterio.open(os.path.join(LAYER_DIR,"aez_belt.tif")) as src:
        v=list(src.sample([(lon,lat)]))[0][0]
        if v is None or v==src.nodata or v==0: v=_nearest(src,lon,lat,src.nodata)
        _,_,aez=_load(); ctx["aez_belt"]=aez.get(int(v)) if v else None
    return ctx

def _crop_group(df,crop_type):
    if not crop_type: return None
    hit=df.loc[df.crop_type.str.lower()==str(crop_type).lower(),"Crop_group"]
    return hit.iloc[0] if len(hit) else None

def recommend(lat,lon,practice_family,indicator,crop_type=None,top_n=3):
    bundle,df,_=_load()
    model=bundle["model"]; cmaps=bundle["cat_maps"]; FEAT=bundle["features"]; CAT=bundle["cat"]
    conf_map=bundle["indicator_confidence"]
    if indicator not in DIRECTION:
        raise ValueError("unknown indicator: %s"%indicator)
    ctx=extract_context(lat,lon)
    cg=_crop_group(df,crop_type)

    # candidate practices seen for this family (optionally supported for this indicator)
    fam=df[df.practice_family==practice_family]
    if fam.empty: raise ValueError("unknown practice_family: %s"%practice_family)
    cand=sorted(fam.CSA_practices.unique())

    rows=[]
    for pr in cand:
        sub=fam[(fam.CSA_practices==pr)&(fam.Indicator==indicator)]
        n_evi=int(len(sub))
        row={"CSA_practices":pr,"practice_family":practice_family,
             "Crop_group":cg if cg else (sub.Crop_group.mode().iloc[0] if len(sub) else fam.Crop_group.mode().iloc[0]),
             "crop_type":crop_type if crop_type else "Unspecified",
             "aez_belt":ctx["aez_belt"],"Indicator":indicator,
             "land_cover":ctx["land_cover"],"Rainfall":ctx["Rainfall"],
             "Altitude_r":ctx["Altitude_r"],"temp_mean_annual":ctx["temp_mean_annual"],
             "precip_seasonality":ctx["precip_seasonality"],"slope":ctx["slope"],
             "soil_clay":ctx["soil_clay"]}
        rows.append((pr,row,n_evi))

    # encode + predict
    Xrows=[]
    for pr,row,n in rows:
        enc={}
        for c in FEAT:
            if c in CAT: enc[c]=cmaps[c].get(str(row.get(c)),-1)
            else: enc[c]=float(row.get(c)) if row.get(c) is not None else np.nan
        Xrows.append(enc)
    X=pd.DataFrame(Xrows)[FEAT]
    pred=model.predict(X)                       # log response ratio
    direction=DIRECTION[indicator]

    items=[]
    for (pr,row,n),lr in zip(rows,pred):
        ratio=float(np.exp(lr)); pct=(ratio-1)*100
        items.append({"practice":pr,"pct_change":round(pct,1),
                      "log_ratio":round(float(lr),4),"n_evidence":n})
    # prefer evidence-grounded candidates (>=1 observation for this family+indicator)
    grounded = [it for it in items if it["n_evidence"] >= 1]
    if not grounded:
        raise ValueError(
            "No field evidence in the dataset for challenge "
            f"'{practice_family}' with objective '{indicator}'. "
            "Choose a different objective for this challenge."
        )
    pool = grounded
    # rank by benefit in the indicator's direction (within this practice_family only)
    pool.sort(key=lambda d: direction * d["log_ratio"], reverse=True)
    top = pool[:top_n]

    allowed = set(cand)
    for it in top:
        if it["practice"] not in allowed:
            raise RuntimeError(
                f"Internal error: recommended practice '{it['practice']}' "
                f"is not in practice_family '{practice_family}'."
            )

    goal_txt={1:"increase",-1:"reduce"}[direction]
    conf=conf_map.get(indicator,"low")
    # clean UI list
    clean=[]
    for it in top:
        eff=abs(it["pct_change"])
        clean.append({"practice":it["practice"],
                      "effect":f"~{eff:.0f}% {goal_txt} in {indicator}"})
    return {
      "query":{"lat":lat,"lon":lon,"practice_family":practice_family,
               "indicator":indicator,"crop_type":crop_type or None,"goal_direction":goal_txt},
      "recommendations":clean,                       # <- clean & short, for default UI
      "details":{                                    # <- only shown if user asks "why"
         "context":ctx,"crop_group":cg,
         "confidence":conf,
         "ranked":top,
         "n_candidates":len(cand),
         "n_grounded":len(grounded),
         "ranking_scope":(
             f"Practices ranked only within '{practice_family}' "
             f"({len(cand)} in dataset, {len(grounded)} with evidence for '{indicator}')."
         ),
         "note":"Effects are model estimates of the with/without response ratio from "
                "meta-analysis evidence; confidence reflects out-of-fold reliability "
                "for this indicator."}
    }

if __name__=="__main__":
    import sys
    r=recommend(8.38,39.37,"Erosion control and water management","soil loss",top_n=3)
    print(json.dumps(r,indent=2,default=str))
