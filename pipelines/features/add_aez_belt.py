#!/usr/bin/env python3
"""
add_aez_belt.py  -  Step 2: add the 15-zone agro-ecological belt as a context feature.
Samples layers/aez_belt.tif at each row's lat/long (nearest-valid fallback for
border/water cells) and maps the code to its zone name via aez_belt_lookup.csv.
Adds column `aez_belt` (placed after land_cover). Saves in place.
Requires: pandas, numpy, rasterio.
"""
import pandas as pd, numpy as np, os, csv, rasterio
from rasterio.windows import Window
B=os.path.dirname(os.path.abspath(__file__))
F=os.path.join(B,"dataset","CSA_ERA_merged_model_ready.csv")
AEZ=os.path.join(B,"layers","aez_belt.tif")
LOOK=os.path.join(B,"aez_belt_lookup.csv")
MAXR=120  # ~30 km fallback (AEZ gaps/water can be a bit larger)

lut={}
with open(LOOK) as f:
    for r in csv.DictReader(f): lut[int(r["value_OBJECTID"])]=r["Agro_zone"]

def nearest(src,lon,lat,nd):
    r,c=src.index(lon,lat); H,W=src.height,src.width
    if not(0<=r<H and 0<=c<W): return None
    r0,r1=max(0,r-MAXR),min(H,r+MAXR+1); c0,c1=max(0,c-MAXR),min(W,c+MAXR+1)
    bl=src.read(1,window=Window(c0,r0,c1-c0,r1-r0))
    v=bl!=nd
    if not v.any(): return None
    rr,cc=np.where(v); d=(rr-(r-r0))**2+(cc-(c-c0))**2
    return int(bl[rr[int(d.argmin())],cc[int(d.argmin())]])

def main():
    m=pd.read_csv(F)
    pts=[(float(lo),float(la)) for lo,la in m[["longitude","latitude"]].drop_duplicates().values]
    code={}
    with rasterio.open(AEZ) as src:
        nd=src.nodata
        for (lo,la),val in zip(pts,[v[0] for v in src.sample(pts)]):
            if val is None or val==nd or val==0:
                val=nearest(src,lo,la,nd)
            code[(lo,la)]=val
    m["aez_belt"]=[lut.get(code.get((float(lo),float(la)))) for lo,la in zip(m.longitude,m.latitude)]
    cols=list(m.columns); cols.remove("aez_belt")
    i=cols.index("land_cover")+1
    m=m[cols[:i]+["aez_belt"]+cols[i:]]
    m.to_csv(F,index=False)
    print("saved",F,m.shape,"missing",int(m.isna().sum().sum()))
    print("\naez_belt distribution:\n",m.aez_belt.value_counts(dropna=False))
    print("\nany null aez_belt:",int(m.aez_belt.isna().sum()))

if __name__=="__main__":
    main()
