"""Parse Kuku-style screenplay .txt files into structured episodes."""
import re, glob, os

TS = r"(\d+):(\d+(?:\.\d+)?)"
def to_sec(m, s): return int(m) * 60 + float(s)
def fmt(t):
    m, s = divmod(t, 60); return f"{int(m):02d}:{s:05.2f}"

BLOCK_RE = re.compile(r"^\*\*(.+?):\*\*\s*$")
TIME_RE = re.compile(r"Start:\s*\(" + TS + r"\)\s*\|\s*End:\s*\(" + TS + r"\)")
SCENE_TIME = re.compile(r"Scene (start|end):\s*" + TS, re.I)

def parse_episode(path):
    txt = open(path, encoding="utf-8").read()
    ep = {"path": path}
    m = re.search(r"EPISODE NUMBER:\s*Episode\s*(\d+)", txt)
    ep["num"] = int(m.group(1)) if m else int(re.search(r"episode-(\d+)", path).group(1))
    ep["logline"] = (re.search(r"EPISODE LOGLINE:\s*(.*)", txt) or [None, ""])[1].strip()
    ep["continuity"] = (re.search(r"CONTINUITY NOTES:\s*(.*)", txt) or [None, ""])[1].strip()
    body = txt.split("--- SCRIPT START ---")[-1].split("--- SCRIPT END ---")[0]
    lines = body.splitlines()
    scenes, cur, item = [], None, None
    for ln in lines:
        s = ln.strip()
        if s.startswith("SCENE ") and re.fullmatch(r"SCENE \d+", s):
            cur = {"id": s, "heading": "", "start": 0, "end": 0, "items": []}; scenes.append(cur); item = None; continue
        if cur is None: continue
        if s.lower().startswith("scene heading:"): cur["heading"] = s.split(":", 1)[1].strip(); continue
        sm = SCENE_TIME.match(s); sm and None
        if sm: cur["start" if sm.group(1).lower() == "start" else "end"] = to_sec(sm.group(2), sm.group(3)); continue
        bm = BLOCK_RE.match(s)
        if bm:
            label = bm.group(1)
            kind = "CAMERA" if label == "CAMERA" else "ACTION" if label == "ACTION" else "SOUND" if label.startswith("SOUND") else "DIALOGUE"
            speaker, tone = None, ""
            if kind == "DIALOGUE":
                mm = re.match(r"(.+?)\s*\((.*)\)\s*$", label)
                speaker, tone = (mm.group(1), mm.group(2)) if mm else (label, "")
            item = {"kind": kind, "speaker": speaker, "tone": tone, "start": None, "end": None, "text": ""}
            cur["items"].append(item); continue
        if item is not None:
            tm = TIME_RE.search(s)
            if tm:
                item["start"] = to_sec(tm.group(1), tm.group(2)); item["end"] = to_sec(tm.group(3), tm.group(4)); continue
            if s and s.lower() != "actions and dialogue:":
                item["text"] = (item["text"] + " " + s).strip()
    ep["scenes"] = scenes
    ep["duration"] = max([sc["end"] for sc in scenes] or [0])
    return ep

def load_pack(folder):
    files = sorted(glob.glob(os.path.join(folder, "**", "episode-*.txt"), recursive=True))
    return [parse_episode(f) for f in files]
