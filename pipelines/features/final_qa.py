#!/usr/bin/env python3
"""
final_qa.py  -  Step 5: final quality check + save the canonical model-ready file.
Reads the merged dataset, runs QA, writes dataset/CSA_ERA_final_model_ready.csv.
Requires: pandas, numpy.
"""
import pandas as pd, numpy as np, os
B=os.path.dirname(os.path.abspath(__file__))
SRC=os.path.join(B,"dataset","CSA_ERA_merged_model_ready.csv")
OUT=os.path.join(B,"dataset","CSA_ERA_final_model_ready.csv")

FEATURES=["CSA_practices","practice_family","Crop_group","crop_type","aez_belt","Indicator",
 "Rainfall","Altitude_r","slope","temp_mean_annual","precip_seasonality","lgp_days",
 "soil_clay","soil_ph","land_cover","soil_soc"]
TARGET="log_response_ratio"
NUM=["Rainfall","Altitude_r","slope","temp_mean_annual","precip_seasonality","lgp_days",
     "soil_clay","soil_ph","soil_soc","response_ratio","log_response_ratio"]

def main():
    m=pd.read_csv(SRC)
    print("shape:",m.shape)
    print("total missing:",int(m.isna().sum().sum()))
    print("missing in features+target:",int(m[FEATURES+[TARGET]].isna().sum().sum()))
    print("exact dup rows (all cols):",int(m.duplicated().sum()))

    print("\n--- numeric ranges ---")
    for c in NUM:
        s=m[c]; print(f"  {c:20s} min={s.min():.3f} max={s.max():.3f} mean={s.mean():.3f}")

    print("\n--- categorical cardinality ---")
    for c in ["source","practice_family","Crop_group","crop_type","aez_belt","Indicator","land_cover"]:
        print(f"  {c:16s} {m[c].nunique()} levels")

    print("\n--- target by indicator ---")
    print(m.groupby("Indicator")[TARGET].agg(["count","mean","std"]).round(3))
    print("\n--- rows by source ---"); print(m.source.value_counts())
    print("\n--- practice_family ---"); print(m.practice_family.value_counts())

    # sanity: response_ratio == exp(log_response_ratio)
    ok=np.allclose(m.response_ratio, np.exp(m.log_response_ratio), rtol=1e-4)
    print("\nresponse_ratio == exp(log_response_ratio):",ok)
    print("groups (Study_No_):",m.Study_No_.nunique(),"| rows/group max",m.groupby('Study_No_').size().max())

    m.to_csv(OUT,index=False)
    print("\nSAVED ->",OUT,m.shape)

if __name__=="__main__":
    main()
