#!/usr/bin/env python3
"""Render maps of the feature stack -> maps/aez_belt_map.png and maps/feature_maps.png.
Set MAPS_OUT to redirect output directory."""
import os, glob, csv, numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap, BoundaryNorm
from matplotlib.patches import Patch
import rasterio
from rasterio.enums import Resampling

BASE   = os.path.dirname(os.path.abspath(__file__))
LAYERS = os.path.join(BASE, "layers")
MAPS   = os.environ.get("MAPS_OUT", os.path.join(BASE, "maps")); os.makedirs(MAPS, exist_ok=True)
LOOKUP = os.path.join(BASE, "aez_belt_lookup.csv")
MAXW   = 1400

def read_dec(path, categorical=False):
    with rasterio.open(path) as s:
        sc = min(1.0, MAXW / s.width); w, h = int(s.width*sc), int(s.height*sc)
        rs = Resampling.nearest if categorical else Resampling.average
        a = s.read(1, out_shape=(h, w), resampling=rs).astype("float32")
        nd = s.nodata; b = s.bounds
    if nd is not None: a[a == nd] = np.nan
    a[a <= -9998] = np.nan
    return a, [b.left, b.right, b.bottom, b.top]

def names():
    d = {}
    with open(LOOKUP) as f:
        for r in csv.DictReader(f): d[int(r["value_OBJECTID"])] = r["Agro_zone"]
    return d

AEZ_COLORS = {1:"#7f3b08",2:"#b35806",3:"#e08214",4:"#fdb863",5:"#fee0b6",6:"#d8daeb",
              7:"#b2abd2",8:"#8073ac",9:"#c7eae5",10:"#80cdc1",11:"#35978f",12:"#4d9221",
              13:"#2166ac",14:"#762a83",15:"#40004b"}

def plot_aez(ax):
    nm = names()
    with rasterio.open(os.path.join(LAYERS,"aez_belt.tif")) as s:
        sc=min(1.0,MAXW/s.width); w,h=int(s.width*sc),int(s.height*sc)
        a=s.read(1,out_shape=(h,w),resampling=Resampling.nearest); b=s.bounds
    codes=sorted(AEZ_COLORS); cmap=ListedColormap([AEZ_COLORS[c] for c in codes])
    norm=BoundaryNorm([codes[0]-0.5]+[c+0.5 for c in codes],cmap.N)
    disp=np.where(a==0,np.nan,a).astype("float32")
    ax.imshow(disp,extent=[b.left,b.right,b.bottom,b.top],cmap=cmap,norm=norm,interpolation="nearest")
    ax.set_title("Agro-ecological belt (15 zones)",fontsize=11,weight="bold")
    ax.set_xlabel("Longitude"); ax.set_ylabel("Latitude")
    h=[Patch(facecolor=AEZ_COLORS[c],label="%d. %s"%(c,nm[c])) for c in codes]
    ax.legend(handles=h,fontsize=6.5,loc="center left",bbox_to_anchor=(1.01,0.5),frameon=False,title="AEZ belt")

def plot_cont(ax, path, title, cmap, unit):
    a,ext=read_dec(path); im=ax.imshow(a,extent=ext,cmap=cmap,interpolation="nearest")
    ax.set_title(title,fontsize=10,weight="bold"); ax.set_xlabel("Longitude"); ax.set_ylabel("Latitude")
    cb=plt.colorbar(im,ax=ax,shrink=0.8,pad=0.02); cb.set_label(unit,fontsize=8)

# standalone AEZ map
fig,ax=plt.subplots(figsize=(11,8)); plot_aez(ax)
fig.suptitle("Ethiopia - Agro-ecological Zones (CSA feature stack anchor)",fontsize=13,weight="bold")
fig.tight_layout(rect=[0,0,0.99,0.97])
fig.savefig(os.path.join(MAPS,"aez_belt_map.png"),dpi=150,bbox_inches="tight"); plt.close(fig)
print("wrote aez_belt_map.png")

cont=[("precip_annual.tif","Annual precipitation","YlGnBu","mm"),
      ("temp_mean_annual.tif","Mean annual temperature","inferno","degC"),
      ("precip_seasonality.tif","Rainfall seasonality (CV)","magma","%"),
      ("lgp_days.tif","Length of growing period","YlGn","days"),
      ("elevation.tif","Elevation","terrain","m"),
      ("slope.tif","Slope","cividis","%"),
      ("soil_clay.tif","Soil clay content","copper","%"),
      ("soil_ph.tif","Soil pH","Spectral","pH"),
      ("soil_soc.tif","Soil organic carbon","YlOrBr","g/kg"),
      ("land_cover.tif","Land cover class","tab20","class")]
panels=[("AEZ",None)]+[("c",c) for c in cont if os.path.exists(os.path.join(LAYERS,c[0]))]
n=len(panels); ncol=3; nrow=(n+ncol-1)//ncol
fig,axes=plt.subplots(nrow,ncol,figsize=(6*ncol,5*nrow)); axes=np.array(axes).reshape(-1)
for ax in axes[n:]: ax.axis("off")
for ax,(kind,info) in zip(axes,panels):
    if kind=="AEZ": plot_aez(ax)
    else:
        f,title,cmap,unit=info; plot_cont(ax,os.path.join(LAYERS,f),title,cmap,unit)
fig.suptitle("CSA Feature Stack - AEZ belt + 10 features",fontsize=15,weight="bold")
fig.tight_layout(rect=[0,0,1,0.98])
fig.savefig(os.path.join(MAPS,"feature_maps.png"),dpi=140,bbox_inches="tight"); plt.close(fig)
print("wrote feature_maps.png (%d panels)"%n)
