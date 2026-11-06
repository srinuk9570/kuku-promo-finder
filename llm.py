"""
Optional LLM layer: rerank + explain the top-K heuristic candidates.
Model-agnostic: set env vars, nothing is hard-coded.
  LLM_PROVIDER = openai-compat | anthropic      (or pass --llm <provider>)
  LLM_API_KEY  = your key
  LLM_MODEL    = e.g. a free-tier Gemini/Groq/OpenRouter model, or a Claude model string
  LLM_BASE_URL = (openai-compat only) e.g. https://generativelanguage.googleapis.com/v1beta/openai , https://api.groq.com/openai/v1
NOTE: written to the public API specs but NOT executed in the build sandbox (no network) - treat as untested.
"""
import os, json, re, urllib.request
from promo_finder import beats_of, dlg, window_beats, clean, fmt

PROMPT = """You are an editor picking promos for a vertical microdrama (TikTok/Reels/ReelShort style).
A good promo (20-60s): HOOK in first 3 seconds (slap/reveal/shock line), ends on an unresolved CLIFFHANGER,
and is understandable to someone who has never seen the show.
Show: {logline}
Candidate clip (episode {ep}, {segs}). Transcript:
{text}
Reply with ONLY JSON: {{"score": 1-10, "hook": "...", "cliffhanger": "...", "why": "one line", "standalone_ok": true/false, "problem": "what would confuse a new viewer, or empty"}}"""

def _post(url, headers, body):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json", **headers})
    return json.load(urllib.request.urlopen(req, timeout=60))

def call(prompt, provider):
    key, model = os.environ["LLM_API_KEY"], os.environ["LLM_MODEL"]
    if provider == "anthropic":
        r = _post("https://api.anthropic.com/v1/messages", {"x-api-key": key, "anthropic-version": "2023-06-01"},
                  {"model": model, "max_tokens": 400, "messages": [{"role": "user", "content": prompt}]})
        return r["content"][0]["text"]
    base = os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    r = _post(base + "/chat/completions", {"Authorization": f"Bearer {key}"},
              {"model": model, "temperature": 0, "messages": [{"role": "user", "content": prompt}]})
    return r["choices"][0]["message"]["content"]

def rerank(picked, by, provider):
    for c in picked:
        ep = by[c["ep"]]; segs = ", ".join(f"{fmt(a)}-{fmt(b)}" for a, b in c["segments"])
        try:
            raw = call(PROMPT.format(logline=ep["logline"], ep=c["ep"], segs=segs, text=c["text"]), provider)
            j = json.loads(re.search(r"\{.*\}", raw, re.S).group(0))
            c["llm_score"] = float(j["score"]) / 10
            c["hook_text"], c["cliff_text"], c["why"] = j.get("hook", c["hook_text"]), j.get("cliffhanger", c["cliff_text"]), j.get("why", c["why"])
            if not j.get("standalone_ok", True): c["stand_why"] = c["stand_why"] + ["LLM: " + str(j.get("problem", ""))]
            c["score"] = 0.5 * c["score"] + 0.5 * c["llm_score"]
        except Exception as e:  # never lose a candidate because the API failed
            c["stand_why"] = c["stand_why"] + [f"LLM call failed ({type(e).__name__}); heuristic score kept"]
    return sorted(picked, key=lambda c: -c["score"])
