#!/usr/bin/env python3
"""
generate_practice_images.py — generate the ACTUAL photos for each CSA practice.

Reads image_prompts.csv (same folder). For each practice it calls an image model,
then normalizes the result to 1200x800 WEBP named <slug>.webp (the UI's filename).
Run wherever you have an image-model API key + internet.

Providers (choose with --provider; key via env):
  openai     OPENAI_API_KEY     model gpt-image-1     [default; matches the sample style]
  gemini     GEMINI_API_KEY     imagen-3.0
  stability  STABILITY_API_KEY  stable-image core

Setup & run:
  pip install pillow requests openai
  export OPENAI_API_KEY=sk-...
  python generate_practice_images.py                 # generate all 99 (skips existing)
  python generate_practice_images.py --overwrite      # regenerate everything
  python generate_practice_images.py --only mulch parklands drip-irrigation
"""
import os, csv, io, base64, argparse, time
from PIL import Image
HERE=os.path.dirname(os.path.abspath(__file__)); CSV=os.path.join(HERE,"image_prompts.csv")
W,H=1200,800
def to_webp(b, dest):
    im=Image.open(io.BytesIO(b)).convert("RGB")
    r=max(W/im.width,H/im.height); im=im.resize((round(im.width*r),round(im.height*r)))
    l=(im.width-W)//2; t=(im.height-H)//2; im=im.crop((l,t,l+W,t+H))
    im.save(dest,"WEBP",quality=90,method=6)
def openai_gen(p):
    from openai import OpenAI
    d=OpenAI().images.generate(model="gpt-image-1",prompt=p,size="1536x1024",n=1)
    return base64.b64decode(d.data[0].b64_json)
def gemini_gen(p):
    import requests; k=os.environ["GEMINI_API_KEY"]
    u=f"https://generativelanguage.googleapis.com/v1beta/models/imagen-3.0-generate-002:predict?key={k}"
    r=requests.post(u,json={"instances":[{"prompt":p}],"parameters":{"sampleCount":1,"aspectRatio":"3:2"}},timeout=120)
    r.raise_for_status(); return base64.b64decode(r.json()["predictions"][0]["bytesBase64Encoded"])
def stability_gen(p):
    import requests; k=os.environ["STABILITY_API_KEY"]
    r=requests.post("https://api.stability.ai/v2beta/stable-image/generate/core",
      headers={"authorization":f"Bearer {k}","accept":"image/*"},files={"none":''},
      data={"prompt":p,"aspect_ratio":"3:2","output_format":"webp"},timeout=120)
    r.raise_for_status(); return r.content
GEN={"openai":openai_gen,"gemini":gemini_gen,"stability":stability_gen}
def main():
    a=argparse.ArgumentParser()
    a.add_argument("--provider",default="openai",choices=list(GEN))
    a.add_argument("--overwrite",action="store_true"); a.add_argument("--only",nargs="*")
    o=a.parse_args(); g=GEN[o.provider]; done=skip=fail=0
    for row in csv.DictReader(open(CSV)):
        sl=row["slug"]; dest=os.path.join(HERE,sl+".webp")
        if o.only and sl not in o.only: continue
        if os.path.exists(dest) and not o.overwrite: skip+=1; continue
        try:
            to_webp(g(row["image_prompt"]),dest); done+=1; print("ok  ",sl); time.sleep(1)
        except Exception as e: fail+=1; print("FAIL",sl,"::",str(e)[:120])
    print(f"\ndone={done} skipped={skip} failed={fail}")
if __name__=="__main__": main()
