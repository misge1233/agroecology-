#!/usr/bin/env python3
"""
final_qa.py  -  Step 5: final quality check + save the canonical model-ready file.
Reads the merged dataset, runs QA, writes dataset/CSA_ERA_final_model_ready.csv.
Requires: pandas, numpy.
"""
import pandas as pd, numpy as np
import os, sys
_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)
from pipelines.geodata import qa as gqa  # noqa: E402  (checks moved there; wrap, never fork)
B=os.path.dirname(os.path.abspath(__file__))
SRC=os.path.join(B,"dataset","CSA_ERA_merged_model_ready.csv")
OUT=os.path.join(B,"dataset","CSA_ERA_final_model_ready.csv")

FEATURES, TARGET, NUM = gqa.DATASET_FEATURES, gqa.DATASET_TARGET, gqa.DATASET_NUM

def main():
    m=pd.read_csv(SRC)
    gqa.dataset_qa(m)

    m.to_csv(OUT,index=False)
    print("\nSAVED ->",OUT,m.shape)

if __name__=="__main__":
    main()
