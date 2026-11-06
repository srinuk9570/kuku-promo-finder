#!/usr/bin/env python3
"""
Promo Finder: reads microdrama screenplays (timestamped) and proposes 20-60s promo clips.

Pipeline (all steps cheap & deterministic unless --llm is given):
  1. parse   -> structured episodes (parser.py)
  2. propose -> every (start,end) window of 20-60s that begins on a line/beat and ends on a line end
  3. score   -> rule-based: hook(first 3s) + cliffhanger(last beat) + intensity + standalone + length
  4. stitch  -> optional 2-segment promos: strong mid-episode hook + that episode's ending
  5. select  -> non-overlap, max 2 per episode, spoiler-aware, ranked
  6. (opt) LLM rerank/explain top-K with any OpenAI-compatible or Anthropic endpoint (llm.py)
Outputs: promos.json, promos.csv, promos.md
"""
import re, json, csv, argparse, os, sys
from collections import Counter
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from parser import load_pack, fmt

MIN_LEN, MAX_LEN, IDEAL = 20.0, 60.0, (30.0, 50.0)

# ---------- lexicons (editable; per-genre swap) ----------
HOOK_WORDS = r"\b(slap|slapped|divorce|pregnan\w*|kill|killed|die|dead|death|murder\w*|poison\w*|betray\w*|lied|lies|liar|secret|truth|duke|king|queen|prince|princess|emperor|heir|husband|wife|marry|married|wedding|bride|traitor|fired|arrest\w*|guard\w*|execut\w*|prison|beg|kneel|apolog\w*|how dare|get out|leave|never|forgive|revenge|vow|curse\w*|spy|blood|baby|child|mother|father|sister|crown|royal|identity|who are you|you\s+are|nobody|worthless|ashamed|humiliat\w*|expose\w*|proof|evidence|trap|trapped)\b"
REVEAL_WORDS = r"\b(gallows|arrest\w*|warrant|witch\w*|prisoner|trial|flame|burn\w*|ash|someone is coming|going somewhere|lawful|rightful|dead duke|not .{0,20}wife|ten days|duke|king|queen|prince|emperor|heir|royal|crown|identity|truth|secret|real|actually|was never|all along|you\s+knew|knew all|pregnan\w*|alive|dead|poison\w*|traitor|betray\w*|signed|proof|evidence|letter|ring|seal|sword|blood|the one)\b"
VIOLENCE_ACTION = r"\b(slap\w*|strikes?|shoves?|slams?|throws?|hurls?|grabs?|seizes?|draws? (?:a |his |her )?(?:sword|dagger|blade)|collapses?|faints?|stabs?|chokes?|drags?|tears?|rips?|shatters?|bursts? (?:in|open)|kneels?|unmask\w*|reveals?|removes? (?:his|her) (?:mask|hood)|crowd gasps?|gasps?)\b"
STRONG_TONE = r"(furious|shock\w*|menac\w*|cold|icy|ominous|threat\w*|desperate|trembl\w*|sneer\w*|cruel|enrag\w*|stunn\w*|horrif\w*|defian\w*|command\w*|dangerous|seeth\w*|panic\w*|tearful|pleading|accus\w*|mock\w*|arrogant|vicious|triumph\w*|fearless|authorit\w*|explosive|booming|whisper\w*)"
RESOLVED_END = r"\b(thank you|thanks|goodnight|good night|goodbye|farewell|sleep well|rest now|see you|of course|very well|as you wish|i understand|all right|alright)\b[\s.!\"â€]*$"
CONNECTIVE_START = r"^[\"â€œ]?\s*(yes|no|and|but|so|because|then|well|that|this|he|she|they|it|him|her|them|why|what do you mean|exactly|indeed|right|okay|ok)\b"
SOFT_END = r"\b(perhaps|trust|peace|safe|afraid|together|begin again|simple|home|love|hope|grateful|proud|better than|reason to|wrong|i didn.?t need)\b"
SPOILER_TERMS = r"\b(true identity|reveal\w*|duke)\b"

def clean(t): return re.sub(r"\s+", " ", t.strip().strip('"â€œâ€'))

# ---------- beats ----------
def beats_of(ep):
    """flatten to time-ordered beats: dialogue, key action, sound"""
    out = []
    for sc in ep["scenes"]:
        for it in sc["items"]:
            if it["kind"] in ("DIALOGUE", "ACTION", "SOUND"):
                out.append({**it, "scene": sc["id"], "heading": sc["heading"]})
    out.sort(key=lambda b: (b["start"], b["end"]))
    return out

def window_beats(beats, a, b):
    return [x for x in beats if x["start"] >= a - 0.01 and x["start"] < b]

def dlg(beats): return [x for x in beats if x["kind"] == "DIALOGUE"]

# ---------- feature scoring (each returns 0..1) ----------
def hook_score(wbeats, a):
    first = [x for x in wbeats if x["start"] <= a + 3.0]
    d = [x for x in first if x["kind"] == "DIALOGUE"]
    s, why = 0.0, []
    if not first: return 0.0, ["nothing in first 3s"]
    # something must happen in first 3 seconds (voice or striking action), not just camera
    if d: s += 0.30; why.append("speech in first 3s")
    txt = " ".join(x["text"] for x in first)
    tone = " ".join(x["tone"] for x in d)
    if re.search(HOOK_WORDS, txt, re.I): s += 0.20; why.append("charged keyword")
    if re.search(VIOLENCE_ACTION, " ".join(x["text"] for x in first if x["kind"] == "ACTION"), re.I): s += 0.25; why.append("physical action")
    if re.search(STRONG_TONE, tone, re.I): s += 0.15; why.append("strong delivery")
    if "!" in txt or "?" in txt: s += 0.10; why.append("!/? punctuation")
    if d and len(clean(d[0]["text"]).split()) <= 14: s += 0.05   # punchy
    if d and re.match(CONNECTIVE_START, clean(d[0]["text"]), re.I): s -= 0.20; why.append("opens on reply/pronoun (needs context)")
    if d and re.match(r"^[\"â€œ]?\s*(\.{2,}|â€¦)", d[0]["text"].strip()): s -= 0.30; why.append("opens mid-sentence (starts with ellipsis)")
    if d and re.search(r"off-?screen|voice", d[0]["speaker"] or "", re.I): s -= 0.10; why.append("opens on off-screen voice")
    return max(0.0, min(1.0, s)), why

def cliff_score(wbeats, b, ep_dur, ep_ends_here, nxt=None):
    tail = [x for x in wbeats if x["end"] >= b - 4.0]
    d = dlg(tail)
    s, why = 0.0, []
    if not d: return 0.0, ["no speech at end"]
    last = clean(d[-1]["text"]); txt = " ".join(clean(x["text"]) for x in d)
    if ep_ends_here: s += 0.15; why.append("episode ending (designed cliffhanger)")
    if re.search(r"(\?|\.{2,}|â€¦|â€”|-)[\"â€\s]*$", d[-1]["text"].strip()): s += 0.20; why.append("ends on question/ellipsis/interruption")
    if re.search(REVEAL_WORDS, txt, re.I): s += 0.20; why.append("reveal/threat words in last beats")
    if re.search(STRONG_TONE, " ".join(x["tone"] for x in d), re.I): s += 0.10; why.append("tense delivery")
    if any(x["kind"] == "SOUND" and re.search(r"(sting|cliff|ominous|swell|silence|gasp|thud|crash)", x["text"], re.I) for x in tail): s += 0.10; why.append("sound sting")
    if nxt is not None and re.match(r"^[\"â€œ]?\s*(\.{2,}|â€¦)", nxt["text"].strip()): s -= 0.30; why.append("cuts mid-sentence (next line continues the thought)")
    if re.search(SOFT_END, " ".join(clean(x["text"]) for x in d[-2:]), re.I) and "?" not in last: s -= 0.25; why.append("soft/reflective ending (low tension)")
    if re.search(RESOLVED_END, last, re.I): s -= 0.35; why.append("ends on a resolving line")
    return max(0.0, min(1.0, s)), why

def intensity_score(wbeats):
    d = dlg(wbeats)
    if not d: return 0.0
    n = len(d); tones = sum(1 for x in d if re.search(STRONG_TONE, x["tone"], re.I))
    exc = sum(("!" in x["text"] or "?" in x["text"]) for x in d)
    switches = sum(1 for i in range(1, n) if d[i]["speaker"] != d[i-1]["speaker"])
    dur = max(1.0, wbeats[-1]["end"] - wbeats[0]["start"])
    density = min(1.0, (n / dur) / 0.25)   # ~1 line per 4s = full marks
    return min(1.0, 0.35 * density + 0.30 * (tones / n) + 0.15 * (exc / n) + 0.20 * min(1.0, switches / max(2, n - 1)))

def standalone_score(wbeats, ep, a):
    d = dlg(wbeats); why = []
    if not d: return 0.0, ["no dialogue"]
    spk = {x["speaker"] for x in d}
    s = 1.0
    if len(spk) > 4: s -= 0.30; why.append(">4 speakers (hard to follow cold)")
    if len(spk) < 2 and len(d) > 2: s -= 0.25; why.append("monologue/one voice")
    scenes = {x["scene"] for x in wbeats}
    if len(scenes) > 2: s -= 0.20; why.append("spans 3+ scenes")
    # does a named/relational anchor show up (who is who)? proxy: names or kinship/titles in window
    if not re.search(r"\b(husband|wife|sister|mother|father|duke|lord|lady|king|queen|fiance|fiancÃ©|bride|groom|brother|daughter|son)\b", " ".join(x["text"] for x in wbeats), re.I): s -= 0.15; why.append("no relationship cue in window")
    return max(0.0, s), why

def length_score(L):
    if IDEAL[0] <= L <= IDEAL[1]: return 1.0
    if L < IDEAL[0]: return 0.6 + 0.4 * (L - MIN_LEN) / (IDEAL[0] - MIN_LEN)
    return 0.6 + 0.4 * (MAX_LEN - L) / (MAX_LEN - IDEAL[1])

W = dict(hook=0.30, cliff=0.30, intensity=0.18, standalone=0.15, length=0.07)

def spoiler_penalty(ep_num, total_eps):
    # promos should not give away late-series twists: mild penalty beyond first 40% of the show
    r = ep_num / total_eps
    return 0.0 if r <= 0.4 else min(0.12, (r - 0.4) * 0.2)

# ---------- candidate generation ----------
def score_window(ep, beats, a, b, total_eps, ep_dur_end):
    wb = window_beats(beats, a, b)
    if len(dlg(wb)) < 3: return None
    ends_ep = b >= ep_dur_end - 1.0
    nxt = next((x for x in beats if x["kind"] == "DIALOGUE" and x["start"] >= b - 0.01), None) if not ends_ep else None
    h, hw = hook_score(wb, a); c, cw = cliff_score(wb, b, ep["duration"], ends_ep, nxt)
    i = intensity_score(wb); st, sw = standalone_score(wb, ep, a); l = length_score(b - a)
    total = W["hook"]*h + W["cliff"]*c + W["intensity"]*i + W["standalone"]*st + W["length"]*l - spoiler_penalty(ep["num"], total_eps)
    return dict(score=total, hook=h, cliff=c, intensity=i, standalone=st, length=l, hook_why=hw, cliff_why=cw, stand_why=sw)

def propose(ep, total_eps):
    beats = beats_of(ep); out = []
    ends_t = ep["duration"]
    starts = sorted({round(x["start"], 2) for x in beats if x["kind"] == "DIALOGUE"} |
                    {round(x["start"], 2) for x in beats if x["kind"] == "ACTION" and re.search(VIOLENCE_ACTION, x["text"], re.I)})
    ends = sorted({round(x["end"], 2) for x in beats if x["kind"] == "DIALOGUE"} | {round(ends_t, 2)})
    for a in starts:
        for b in ends:
            L = b - a
            if L < MIN_LEN or L > MAX_LEN: continue
            sc = score_window(ep, beats, a, b, total_eps, ends_t)
            if sc: out.append(dict(ep=ep["num"], segments=[(a, b)], **sc))
    return out, beats

def propose_stitched(ep, beats, total_eps):
    """2-segment promos: best mid-episode hook beat (8-22s) + the episode ending (14-30s)."""
    ends_t = ep["duration"]; out = []
    tails = []
    for a in sorted({x["start"] for x in beats if x["kind"] == "DIALOGUE" and ends_t - x["start"] <= 30 and ends_t - x["start"] >= 14}):
        tails.append(a)
    if not tails: return out
    ta = tails[0]
    heads = sorted({x["start"] for x in beats if x["kind"] == "DIALOGUE" or (x["kind"]=="ACTION" and re.search(VIOLENCE_ACTION, x["text"], re.I))})
    for a in heads:
        for L in (8, 12, 16, 22):
            b = a + L
            if b > ta - 3: continue
            hb = window_beats(beats, a, b)
            if len(dlg(hb)) < 2: continue
            hk, hw = hook_score(hb, a)
            if hk < 0.6: continue
            wb = window_beats(beats, a, b) + window_beats(beats, ta, ends_t)
            total_len = L + (ends_t - ta)
            if not (MIN_LEN <= total_len <= MAX_LEN): continue
            c, cw = cliff_score(window_beats(beats, ta, ends_t), ends_t, ends_t, True)
            i = intensity_score(wb); st, sw = standalone_score(wb, ep, a); l = length_score(total_len)
            sw.append("stitched: mid-episode hook + episode ending (viewer may miss the connection)")
            st = max(0.0, st - 0.15)
            total = W["hook"]*hk + W["cliff"]*c + W["intensity"]*i + W["standalone"]*st + W["length"]*l - spoiler_penalty(ep["num"], total_eps) - 0.03
            out.append(dict(ep=ep["num"], segments=[(a, b), (ta, ends_t)], score=total, hook=hk, cliff=c, intensity=i, standalone=st, length=l, hook_why=hw, cliff_why=cw, stand_why=sw))
    return out

def overlap(s1, s2):
    for (a, b) in s1:
        for (c, d) in s2:
            if min(b, d) - max(a, c) > 1.0: return True
    return False

def select(cands, k, per_ep):
    cands = sorted(cands, key=lambda c: -c["score"]); chosen = []; cnt = Counter()
    for c in cands:
        if cnt[c["ep"]] >= per_ep: continue
        if any(x["ep"] == c["ep"] and overlap(x["segments"], c["segments"]) for x in chosen): continue
        chosen.append(c); cnt[c["ep"]] += 1
        if len(chosen) >= k: break
    return chosen

def clip_text(ep_by_num, c):
    parts = []
    for (a, b) in c["segments"]:
        beats = beats_of(ep_by_num[c["ep"]])
        parts.append(" / ".join(f'{x["speaker"].title()}: "{clean(x["text"])}"' for x in dlg(window_beats(beats, a, b))))
    return "  ||  ".join(parts)

def describe(ep_by_num, c):
    ep = ep_by_num[c["ep"]]; beats = beats_of(ep)
    first = window_beats(beats, c["segments"][0][0], c["segments"][0][0] + 3.0)
    fd = dlg(first); fa = [x for x in first if x["kind"] == "ACTION"]
    hook = (f'{fd[0]["speaker"].title()}: "{clean(fd[0]["text"])}"' if fd else clean(fa[0]["text"]) if fa else "n/a")
    lastseg = c["segments"][-1]; ld = dlg(window_beats(beats, lastseg[0], lastseg[1]))
    cliff = f'{ld[-1]["speaker"].title()}: "{clean(ld[-1]["text"])}"' if ld else "n/a"
    c["hook_text"] = hook; c["cliff_text"] = cliff
    reasons = c["hook_why"][:2] + c["cliff_why"][:2]
    c["why"] = "; ".join(reasons) if reasons else "high overall intensity"
    return c

def run(folder, k=25, per_ep=2, stitched=True):
    eps = load_pack(folder); by = {e["num"]: e for e in eps}; total = len(eps); allc = []
    for ep in eps:
        c, beats = propose(ep, total); allc += c
        if stitched: allc += propose_stitched(ep, beats, total)
    picked = select(allc, k, per_ep)
    for i, c in enumerate(picked, 1):
        c["rank"] = i; describe(by, c)
        c["duration"] = round(sum(b - a for a, b in c["segments"]), 1)
        c["text"] = clip_text(by, c)
    return picked, by, len(allc)

def write_outputs(picked, by, outdir, n_cands):
    os.makedirs(outdir, exist_ok=True)
    def seg_str(c): return " + ".join(f"EP{c['ep']} {fmt(a)}-{fmt(b)}" for a, b in c["segments"])
    js = [dict(rank=c["rank"], episode=c["ep"], segments=[dict(start=fmt(a), end=fmt(b)) for a, b in c["segments"]],
               duration_s=c["duration"], hook=c["hook_text"], cliffhanger=c["cliff_text"], why=c["why"],
               score=round(c["score"], 3), subscores={k: round(c[k], 2) for k in ("hook", "cliff", "intensity", "standalone", "length")},
               risks=c["stand_why"], transcript=c["text"]) for c in picked]
    json.dump(js, open(os.path.join(outdir, "promos.json"), "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    with open(os.path.join(outdir, "promos.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["rank", "episode", "segments", "duration_s", "score", "hook", "cliffhanger", "why", "risks"])
        for c in picked: w.writerow([c["rank"], c["ep"], seg_str(c), c["duration"], round(c["score"], 3), c["hook_text"], c["cliff_text"], c["why"], "; ".join(c["stand_why"])])
    with open(os.path.join(outdir, "promos.md"), "w", encoding="utf-8") as f:
        f.write(f"# Promo candidates ({n_cands} windows scored, top {len(picked)} shown)\n\n")
        for c in picked:
            f.write(f"## #{c['rank']}  {seg_str(c)}  ({c['duration']}s, score {c['score']:.2f})\n- **Hook:** {c['hook_text']}\n- **Cliffhanger:** {c['cliff_text']}\n- **Why:** {c['why']}\n")
            if c["stand_why"]: f.write(f"- **Risks:** {'; '.join(c['stand_why'])}\n")
            f.write(f"- **Transcript:** {c['text']}\n\n")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("folder"); ap.add_argument("--out", default="outputs"); ap.add_argument("--top", type=int, default=25)
    ap.add_argument("--per-episode", type=int, default=2); ap.add_argument("--no-stitch", action="store_true")
    ap.add_argument("--llm", default=None, help="provider: openai-compat | anthropic (see llm.py)")
    a = ap.parse_args()
    picked, by, n = run(a.folder, k=max(a.top, 60) if a.llm else a.top, per_ep=a.per_episode, stitched=not a.no_stitch)
    if a.llm:
        import llm; picked = llm.rerank(picked, by, a.llm)[:a.top]
        for i, c in enumerate(picked, 1): c["rank"] = i
    write_outputs(picked, by, a.out, n)
    # also: best single promo for EVERY episode (full coverage view)
    allbest, _, _ = run(a.folder, k=500, per_ep=1, stitched=not a.no_stitch)
    allbest = sorted(allbest, key=lambda c: c["ep"])
    with open(os.path.join(a.out, "best_per_episode.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["episode", "segments", "duration_s", "score", "hook", "cliffhanger", "why"])
        for c in allbest: w.writerow([c["ep"], " + ".join(f"{fmt(x)}-{fmt(y)}" for x, y in c["segments"]), c["duration"], round(c["score"], 3), c["hook_text"], c["cliff_text"], c["why"]])
    print(f"scored {n} windows; wrote {len(picked)} promos to {a.out}/")

