#!/usr/bin/env python3
"""
groq_agent.py  -  Phase 4: LLM wiring for the CSA recommender (OpenAI).

The LLM's job:
  1. Understand the user (free text or UI selections) -> structured call to recommend().
  2. Present the model's recommendations in clean, short, natural language (default).
  3. On follow-up "why/explain" questions, justify using the details block
     (resolved context, evidence counts, confidence) + agronomic reasoning.
The model NEVER invents effect numbers - all numbers come from recommend() (the ML model).

Design:
- recommend() is exposed to the LLM as a single tool (function calling).
- Conversation state is kept so follow-ups reuse the last recommendation's details.
- Works without network for logic testing via a rule-based fallback parser
  (set OPENAI_API_KEY to use the real LLM).

Env: OPENAI_API_KEY only (model/URL in app.services.openai_chat)
Deps: httpx; recommend.py in the same folder.
"""
import os, json
import httpx
from recommend import recommend, DIRECTION

PRACTICE_FAMILIES=["Crop production and management","Livestock production and management",
 "Integrated soil fertility management","Erosion control and water management",
 "Agro-forestry and forest management"]
INDICATORS=list(DIRECTION.keys())
INDICATOR_PHRASING={
 "increase crop yield":"yield","increase yield":"yield","yield":"yield",
 "increase biomass":"biomass yield","fodder":"biomass yield","biomass yield":"biomass yield",
 "increase income":"income","income":"income","profit":"income",
 "water use efficiency":"water use efficiency","water efficiency":"water use efficiency",
 "soil organic matter":"SOM content","soil health":"SOM content","som":"SOM content",
 "reduce soil loss":"soil loss","erosion":"soil loss","soil loss":"soil loss",
 "reduce runoff":"runoff","runoff":"runoff",
}

SYSTEM_PROMPT=f"""You are a Climate-Smart Agriculture (CSA) advisor for Ethiopian farmers and
extension agents. You help users pick the best CSA practice for their location and goal.

You have ONE tool: recommend(lat, lon, practice_family, indicator, crop_type). It runs a
trained model over meta-analysis field evidence and returns ranked practices with a clean
"recommendations" list plus a "details" block (resolved context, evidence counts, confidence).

RULES:
- Required to call the tool: lat, lon, practice_family, indicator. crop_type is optional.
  practice_family must be one of: {PRACTICE_FAMILIES}.
  indicator must be one of: {INDICATORS}.
- The tool ranks ONLY CSA practices recorded under the user's chosen practice_family
  in the meta-analysis dataset — never practices from other challenge areas.
- EVIDENCE GATE: Never recommend a CSA practice, name techniques (e.g. contour farming,
  terraces, mulch), or invent effect numbers unless those practices appear in a recommend()
  tool result (or a server-provided recommendation JSON) for this turn. If inputs are
  incomplete, ONLY ask for what is missing — do not guess agronomy.
- LOCATION: Prefer coordinates from the user or a system-resolved place name. NEVER invent
  or guess lat/lon for towns. If only a place name is known and coordinates were not
  provided by the system, ask for a map pin or coordinates.
- Infer clearly stated intent from natural language when confident, e.g.
  "reduce soil loss on a sloping field" → practice_family "Erosion control and water
  management", indicator "soil loss". If ambiguous, ask a short clarifying question.
- If the user hasn't given location or a clear goal/challenge, ASK briefly for what's missing
  (a map location / Ethiopian place name, the challenge = practice_family, and the
  objective = indicator).
- DEFAULT ANSWER (first recommendation): clean, short, natural, and CONTEXT-AWARE. Open by
  grounding it in the user's location using the details block - name the agro-ecological zone
  and one or two salient context facts (e.g. rainfall, soil, slope) in plain words, then give
  the top practice and what it does, and briefly mention the other good options. Example shape:
  "For your <aez_belt> area (roughly <one/two context facts>), I'd recommend <top practice> to
  <goal>. Other good options: <b>, <c>." Do NOT show percentages, evidence counts, confidence,
  or raw numbers in this default answer.
- FOLLOW-UPS: understand the user's intent intelligently - they may ask why, how sure, how to
  do it, cost, whether another practice is better, what about a different crop/goal, etc.
  Answer whatever they actually ask, grounded in the tool's details block and sound agronomy.
  When they want justification/confidence, THEN cite evidence counts, confidence level, and the
  estimated effect, phrased as "<practice> is recommended because it is backed by N field
  observations (confidence: <level>), with an estimated <effect>...". If they ask something the
  data can't answer (e.g. exact local price), say so honestly and give practical guidance.
- SOCIAL / ACKNOWLEDGEMENTS: if the user only says thanks, thank you, ok, alright, bye,
  goodbye, great, cool, appreciated, or similar (no new question and no changed inputs),
  reply with a brief warm acknowledgement. Do NOT call the recommend tool.
- TOOL DISCIPLINE: call recommend ONLY when you need a NEW model score — first ask with enough
  inputs, or a follow-up that changes location, practice_family, indicator, or crop. If a prior
  recommendation (or "Previous recommendation" context) is already available, REUSE it for
  why/how/compare/thanks — do not re-call the tool.
- If a follow-up implies a changed goal, family, crop, or location, call the tool again with the
  updated inputs rather than guessing.
- NEVER invent or alter effect numbers. Every quantitative claim must come from the tool
  output. If confidence is low, say the evidence is limited and be honest.
- NEVER write raw tool/function-call markup in your reply (no "function=recommend", no
  XML-ish tool tags, no JSON argument blobs meant for tools). Speak only in natural language.
- Be warm, concise, and practical. Prefer plain words over technical terms with farmers.
"""

TOOLS=[{"type":"function","function":{
  "name":"recommend",
  "description":"Recommend CSA practices for a location and goal using the trained model.",
  "parameters":{"type":"object","properties":{
     "lat":{"type":"number","description":"latitude (Ethiopia, 3.3-14.9)"},
     "lon":{"type":"number","description":"longitude (Ethiopia, 32.9-48.2)"},
     "practice_family":{"type":"string","enum":PRACTICE_FAMILIES,
        "description":"the challenge area the user selected"},
     "indicator":{"type":"string","enum":INDICATORS,
        "description":"the objective/outcome to improve"},
     "crop_type":{"type":["string","null"],"description":"optional specific crop"},
     "top_n":{"type":"integer","default":1,"description":"How many ranked practices to return (default 1)"}},
   "required":["lat","lon","practice_family","indicator"]}}}]

def run_tool(name,args):
    if name=="recommend":
        try:
            from app.services import recommender_service as svc
            return svc.recommend(
                lat=args["lat"],
                lon=args["lon"],
                practice_family=args["practice_family"],
                indicator=args["indicator"],
                crop_type=args.get("crop_type"),
                top_n=args.get("top_n", 1),
            )
        except ImportError:
            return recommend(
                lat=args["lat"],
                lon=args["lon"],
                practice_family=args["practice_family"],
                indicator=args["indicator"],
                crop_type=args.get("crop_type"),
                top_n=args.get("top_n", 1),
            )
    raise ValueError(name)

def _openai_headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

def _parse_tool_args(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def _openai_chat_config():
    from app.services.openai_chat import OPENAI_CHAT_COMPLETIONS_URL, OPENAI_CHAT_MODEL

    return OPENAI_CHAT_MODEL, OPENAI_CHAT_COMPLETIONS_URL

# Pure acknowledgements / closers — never need a tool call.
_SOCIAL_ACK_RE=None
def _is_social_ack(text:str)->bool:
    """True when the message is only thanks/ok/bye (no new ask)."""
    global _SOCIAL_ACK_RE
    import re
    if _SOCIAL_ACK_RE is None:
        _SOCIAL_ACK_RE=re.compile(
            r"^\s*(?:thanks|thank\s*you|thx|ty|ok|okay|alright|all\s*right|"
            r"great|cool|nice|perfect|awesome|appreciated|much\s*appreciated|"
            r"bye|goodbye|see\s*you|cheers|got\s*it|sounds\s*good|"
            r"that\s*helps|helpful)[\s!.]*$"
            ,re.I)
    return bool(_SOCIAL_ACK_RE.match((text or "").strip()))

# ------------------------------------------------------------------ OpenAI loop
class CSAAdvisor:
    def __init__(self, model=None):
        chat_model, _ = _openai_chat_config()
        self.model = model or chat_model
        self.messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        self._api_key = os.environ.get("OPENAI_API_KEY") or None

    def chat(self, user_text):
        """One turn. Returns the assistant's natural-language reply."""
        self.messages.append({"role": "user", "content": user_text})
        if self._api_key is None:
            return self._offline(user_text)
        _, completions_url = _openai_chat_config()
        messages = list(self.messages)
        headers = _openai_headers(self._api_key)
        for _ in range(4):
            payload = {
                "model": self.model,
                "messages": messages,
                "tools": TOOLS,
                "tool_choice": "auto",
                "temperature": 0.3,
            }
            try:
                with httpx.Client(timeout=60.0, headers=headers) as client:
                    resp = client.post(completions_url, json=payload)
                    resp.raise_for_status()
                    choice = resp.json()["choices"][0]["message"]
            except Exception as e:
                print("[openai unavailable: %s]" % e)
                return self._offline(user_text)
            messages.append(choice)
            tool_calls = choice.get("tool_calls") or []
            if tool_calls:
                for tc in tool_calls:
                    fn = tc.get("function") or {}
                    args = _parse_tool_args(fn.get("arguments"))
                    try:
                        out = run_tool(fn.get("name"), args)
                    except Exception as e:
                        out = {"error": str(e)}
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.get("id") or "",
                            "content": json.dumps(out, default=str),
                        }
                    )
                continue
            reply = choice.get("content") or ""
            self.messages.append({"role": "assistant", "content": reply})
            return reply
        return "Sorry, I couldn't complete that."

    # ---- offline fallback: slot extraction + evidence (no invented practices) ----
    def _offline(self,text):
        import re
        t=text.lower().strip()
        # Pure social / acknowledgement turns — never re-score.
        if _is_social_ack(t) and getattr(self,"_last",None) is not None:
            return ("You're welcome — glad it helped. Ask anytime if you want to know why, "
                    "how to apply it, or try a different location, crop, or goal.")
        if _is_social_ack(t):
            return ("You're welcome. Share a map location, challenge area, and objective "
                    "whenever you're ready and I'll recommend CSA practices.")

        try:
            from app.services.slot_extraction import (
                clarification_message,
                evidence_summary,
                extract_slots,
            )
            slots = extract_slots(text, last_recommendation=getattr(self, "_last", None))
        except Exception:
            slots = None

        want_why=any(w in t for w in ["why","explain","how sure","evidence","confidence","detail","because"])
        m=re.findall(r"(-?\d+\.\d+)",text)
        # follow-up with no new scored inputs: reuse the last recommendation
        if getattr(self,"_last",None) is not None:
            reuse = True
            if slots is not None and slots.is_complete:
                q = self._last.get("query") or {}
                reuse = (
                    slots.practice_family == q.get("practice_family")
                    and slots.indicator == q.get("indicator")
                    and abs(float(slots.lat) - float(q.get("lat", 0))) < 1e-4
                    and abs(float(slots.lon) - float(q.get("lon", 0))) < 1e-4
                )
            elif len(m) >= 2:
                reuse = False
            if reuse and (want_why or (slots is not None and slots.is_followup) or len(m) < 2):
                res=self._last; recs=res["recommendations"]; d=res["details"]; ctx=d["context"]; top=recs[0]
                if want_why:
                    return (f"{top['practice']} is recommended because it is backed by "
                            f"{d['ranked'][0]['n_evidence']} field observations (confidence: {d['confidence']}), "
                            f"with an estimated {top['effect']}. It fits your {ctx['aez_belt']} conditions "
                            f"(~{ctx['Rainfall']:.0f} mm rainfall, clay {ctx['soil_clay']}% soil, slope {ctx['slope']:.0f}%).")
                if any(w in t for w in ["how","implement","apply","steps","do it"]):
                    return (f"To apply {top['practice']}, follow local extension guidance for your "
                            f"{ctx['aez_belt']} area; it's the top option here for {res['query']['indicator']}. "
                            f"Ask 'why' to see the evidence behind it.")
                if any(w in t for w in ["alternativ","other","instead","better","else","compare"]):
                    alts=", ".join(r['practice'] for r in recs[1:]) or "no strong alternatives"
                    return f"Other good options for your area: {alts}. Ask 'why' to compare their evidence."
                if slots is not None and slots.is_followup:
                    return (f"{top['practice']} remains the top suggestion for your {ctx['aez_belt']} area. "
                            f"You can ask why it's recommended, how to apply it, or change your location, "
                            f"goal, or crop.")

        if slots is not None:
            if not slots.is_complete:
                return clarification_message(slots)
            res = run_tool("recommend", {
                "lat": slots.lat, "lon": slots.lon,
                "practice_family": slots.practice_family,
                "indicator": slots.indicator,
                "crop_type": slots.crop_type, "top_n": 1,
            })
            self._last = res
            if want_why:
                d=res["details"]; ctx=d["context"]; recs=res["recommendations"]
                top=recs[0]["practice"]
                return (f"For your area ({ctx['aez_belt']}, ~{ctx['Rainfall']:.0f} mm rainfall, "
                        f"clay {ctx['soil_clay']}%, slope {ctx['slope']}%), the strongest option is "
                        f"{top}. It is backed by {d['ranked'][0]['n_evidence']} field observations "
                        f"(confidence: {d['confidence']}). Effect estimate: {recs[0]['effect']}.")
            return evidence_summary(res)

        # Legacy minimal fallback if slot module unavailable.
        if len(m)<2:
            return ("I can help. Please share your location (latitude and longitude), the "
                    "challenge area, and your objective (e.g. increase yield or reduce erosion).")
        fam=next((f for f in PRACTICE_FAMILIES if f.lower() in t),None)
        if fam is None:
            if any(w in t for w in ["erosion","soil loss","runoff","water harvest","bund"]):fam="Erosion control and water management"
            elif any(w in t for w in ["fertil","soil fertility","compost","manure"]):fam="Integrated soil fertility management"
            elif "livestock" in t or "feed" in t or "forage" in t:fam="Livestock production and management"
            elif "tree" in t or "forest" in t or "agroforest" in t:fam="Agro-forestry and forest management"
            else:fam="Crop production and management"
        ind=next((v for k,v in INDICATOR_PHRASING.items() if k in t),"yield")
        lat,lon=float(m[0]),float(m[1])
        crop=None
        for c in ["maize","teff","wheat","barley","sorghum","potato","onion","coffee"]:
            if c in t: crop=c.title()
        res=run_tool("recommend",{
            "lat":lat,"lon":lon,"practice_family":fam,"indicator":ind,
            "crop_type":crop,"top_n":1})
        self._last=res
        try:
            from app.services.slot_extraction import evidence_summary
            return evidence_summary(res)
        except Exception:
            lead=res["recommendations"][0]
            return f"I'd recommend **{lead['practice']}** ({lead['effect']})."

if __name__=="__main__":
    a=CSAAdvisor()
    print("MODE:", "OPENAI" if a._api_key else "OFFLINE fallback")
    print("\nU: My farm is at 8.38, 39.37 and I want to reduce erosion.")
    print("A:", a.chat("My farm is at 8.38, 39.37 and I want to reduce erosion."))
    print("\nU: Why that one?")
    print("A:", a.chat("Why that one?"))
