# Promo Finder (Kuku AI Generalist - Problem 1)

Finds 20-60s promo clips (hook in first 3s, cliffhanger ending, understandable cold) in timestamped microdrama screenplays.

## Run (no installs, no API key, Python 3.9+)
    python3 promo_finder.py "<folder with episode-*.txt>" --out outputs --top 25
    python3 eval_endings.py "<folder>"          # sanity check of the cliffhanger scorer

Outputs: `promos.md/json/csv` (ranked, with segments, hook, cliffhanger, why, risks, transcript),
`best_per_episode.csv` (best promo for each of the 50 episodes), `run_log.txt`.

## Optional LLM rerank (swap any model)
    export LLM_PROVIDER=openai-compat LLM_API_KEY=... LLM_MODEL=... LLM_BASE_URL=https://api.groq.com/openai/v1
    python3 promo_finder.py "<folder>" --llm openai-compat
`anthropic` is also supported. This path is written to the public API specs but was NOT executed in the build sandbox (no network).

## Files
parser.py (screenplay -> structure) | promo_finder.py (propose, score, stitch, select, write) | llm.py (optional rerank) | eval_endings.py (QA)

## Adapting to a new show
Input format is the same timestamped screenplay. Genre lexicons (HOOK_WORDS, REVEAL_WORDS, SOFT_END...) are at the top of promo_finder.py.
Do not publish the input pack or the raw outputs: they contain Kuku's content.
