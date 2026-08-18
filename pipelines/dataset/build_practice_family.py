#!/usr/bin/env python3
"""
build_practice_family.py
Assign every practice in the merged dataset to one of the FIVE expert categories
from the AICCRA/Adimassu paper (paper_long.txt):
  CPM  Crop production and management
  LPM  Livestock production and management
  ISFM Integrated Soil Fertility Management
  ECWM Erosion control and water management
  FAF  Forestry and agroforestry

Method:
- CSA-source practices (the 20 CSA_catago categories) use an explicit lookup
  built directly from the paper's category listings.
- ERA-source practices (81, many are 'A-B-C' combinations) are classified by
  keyword tokens; when a combined practice matches several categories, the paper
  notes such overlaps, so we resolve to ONE family by a documented priority:
      FAF > LPM > ISFM > ECWM > CPM
  (distinctive whole-system practices first; ISFM is the dominant ERA soil-fertility
   theme; ECWM for water/erosion; CPM as the base crop-management default).

Output: adds column `practice_family`; saves in place. Prints distribution and any
practice that fell to the CPM default without a keyword hit (for review).
"""
import pandas as pd, os
B=os.path.dirname(os.path.abspath(__file__))
F=os.path.join(B,"dataset","CSA_ERA_merged_model_ready.csv")

# full category names (replace abbreviations)
CPM ="Crop production and management"
LPM ="Livestock production and management"
ISFM="Integrated soil fertility management"
ECWM="Erosion control and water management"
FAF ="Agro-forestry and forest management"

# --- explicit map for the 20 CSA_catago categories (from paper category lists) ---
CSA_MAP={
 "Physical SWC measures":ECWM,
 "Animal feed management":LPM,
 "In-situ water harvesting":ECWM,
 "ISFM":ISFM,
 "Intercropping":CPM,
 "Exclosure":FAF,
 "organic amedements":ISFM,
 "Deficit irrigation":ECWM,
 "Conservation tillage":CPM,
 "agronomic/biological SWCP":ECWM,
 "furrow irrigation":ECWM,
 "drip irrigation":ECWM,
 "Physical + biological SWC practices":ECWM,
 "grazing management":LPM,
 "Biological SWC practices":ECWM,
 "weeding":CPM,
 "IWM":ECWM,                       # integrated water/watershed management
 "overhead irrigation with mulching":ECWM,
 "furrow irrigation_alternate":ECWM,
 "Drought tolerrant crops":CPM,
}

# --- keyword sets for ERA practices (searched as substrings, lowercased) ---
KW={
 "FAF":["agroforest","parkland","multistrata","alley crop","alleycropping","afforest","reforest",
        "exclosure","silvopast","silvo-past","prosopis","woodlot","fmnr",
        "natural regeneration","pruning","fodder tree","tree","shrub"],
 "LPM":["feed","forage","fodder","grazing","livestock","animal","breed",
        "supplement","silage","destock","dairy","pasture","herd"],
 "ISFM":["fertilizer","inorganic","organic","biochar","compost","vermicompost",
         "manure","lime","liming","gypsum","ph control","nutrient","bio fertil",
         "bioslurry","green manure","residue incorporation","microdose","micro-dose",
         "amendment","inoculant","soil fertility","integrated soil"],
 "ECWM":["irrigation","water harvest","bund","terrace","fanya","tied ridge",
         "tie-ridge","tie ridge","ridge","mulch","runoff","check dam","shallow well",
         "water storage","spate","drip","furrow","sprinkler","deficit","grass strip",
         "trench","waterway","sub-soil","sub soil","soil and water","moisture",
         "half moon","percolation","contour","broad bed","bbf","bbm","pond","diversion"],
 "CPM":["variet","cultivar","intercrop","rotation","tillage","minimum till","zero till",
        "weed","pest","ipm","planting date","sowing","seed","cover crop","fallow",
        "drought tolerant","conservation agri","advisory","insurance","diversif",
        "residue","relay","push-pull","botanical","striga"],
}
PRIORITY=["FAF","LPM","ISFM","ECWM","CPM"]
FULL={"CPM":CPM,"LPM":LPM,"ISFM":ISFM,"ECWM":ECWM,"FAF":FAF}

def classify_era(name):
    s=str(name).lower()
    hits={fam for fam,kws in KW.items() if any(k in s for k in kws)}
    for fam in PRIORITY:
        if fam in hits:
            return FULL[fam], (len(hits)>1)   # (family full name, was_multi)
    return CPM, None                          # default (no keyword) -> review

def main():
    m=pd.read_csv(F)
    fam=[]; default_hits={}
    for src,pr in zip(m.source,m.CSA_practices):
        if src=="CSA":
            fam.append(CSA_MAP.get(str(pr).strip(),CPM))
        else:
            f,multi=classify_era(pr)
            fam.append(f)
            if multi is None:
                default_hits[pr]=default_hits.get(pr,0)+1
    m["practice_family"]=fam
    # place practice_family right after CSA_practices
    cols=list(m.columns); cols.remove("practice_family")
    i=cols.index("CSA_practices")+1
    cols=cols[:i]+["practice_family"]+cols[i:]
    m=m[cols]
    m.to_csv(F,index=False)
    print("saved",F,m.shape,"missing",int(m.isna().sum().sum()))
    print("\npractice_family distribution:\n",m.practice_family.value_counts())
    print("\npractice_family x source:\n",pd.crosstab(m.practice_family,m.source))
    if default_hits:
        print("\nERA practices that hit NO keyword (defaulted to CPM) -- review:")
        for k,v in sorted(default_hits.items(),key=lambda x:-x[1]): print(f"  {v:5d}  {k}")
    else:
        print("\nAll ERA practices matched at least one keyword.")

if __name__=="__main__":
    main()
