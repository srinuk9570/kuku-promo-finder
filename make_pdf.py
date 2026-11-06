from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import mm
ss=getSampleStyleSheet()
B=ParagraphStyle('b',parent=ss['BodyText'],fontSize=8.6,leading=10.8,spaceAfter=2.5)
H=ParagraphStyle('h',parent=ss['Heading3'],fontSize=10.2,spaceBefore=4,spaceAfter=2,textColor=colors.HexColor('#222244'))
T=ParagraphStyle('t',parent=ss['Title'],fontSize=14,spaceAfter=2)
C=ParagraphStyle('c',parent=B,fontSize=7.6,leading=9.2)
def P(t,s=B): return Paragraph(t,s)
bul=lambda t: P("&bull; "+t)
doc=SimpleDocTemplate("Solution_Doc_Promo_Finder.pdf",pagesize=A4,leftMargin=14*mm,rightMargin=14*mm,topMargin=11*mm,bottomMargin=10*mm)
s=[]
s+= [P("Kuku AI Generalist - Problem 1: Promo Finder",T),
 P("<b>Input:</b> 50 episodes (~103 min) of <i>I Married a Broken Soldier. He Was a Duke</i>. <b>Output:</b> 25 ranked promos + best promo per episode. <b>Prototype:</b> github.com/srinuk9570/kuku-promo-finder &nbsp; <b>Run time:</b> ~4 s, no API key.",B)]
s+= [P("1. Why Problem 1, and assumptions",H),
 bul("Chosen because it is the only problem with a real input pack and a checkable output (timestamps), so I can show real runs and real failures rather than claims."),
 bul("Assumed: a promo may be 1 continuous clip or 2 stitched segments; it starts/ends on dialogue boundaries (no mid-line cuts); hook = first 3 s must contain speech or a violent/reveal action; ending must leave a question/threat open; a viewer has not seen the show; late-series twists (after ~40% of episodes) are mildly penalised to avoid spoilers."),
 bul("Assumed screenplay timestamps are accurate to the video. Parser also tolerates header-case differences (some episodes use SCENE START vs Scene start), found on first run: episode 6 parsed as 0 s until fixed.")]
s+= [P("2. How it works (what is code, what is AI)",H),
 bul("<b>Parse</b> screenplay into scenes/beats (dialogue with speaker + delivery tag, key actions, sound cues). Pure code."),
 bul("<b>Propose</b> every window of 20-60 s that starts on a line (or violent/reveal action) and ends on a line end: ~13,000 windows over 50 episodes. Pure code, so cut points are always valid and never invent timestamps."),
 bul("<b>Score</b> (weights): hook 0.30, cliffhanger 0.30, intensity 0.18, stand-alone 0.15, length 0.07, minus spoiler penalty. Hook looks at the first 3 s (speech, charged words, violent action, delivery tags, punchy, penalty for opening on a reply like 'Yes...' or mid-sentence '...'). Cliffhanger looks at the last beats (question/ellipsis/interruption, reveal or threat words such as <i>gallows, warrant, rightful</i>, sound sting; penalty for resolving or soft/reflective lines, and for cutting a sentence the next line continues). Stand-alone penalises many speakers, 3+ scenes, no relationship cue."),
 bul("<b>Stitch</b> 2-segment promos: strong mid-episode hook + that episode's ending."),
 bul("<b>Select</b>: highest score first, no overlaps, max 2 per episode, ranked. Each result lists hook, cliffhanger, one-line why, and <i>risks</i> (e.g. stitched, many speakers)."),
 bul("<b>LLM (optional, swappable)</b>: llm.py reranks the top 60 with any OpenAI-compatible or Anthropic model via 4 env vars (score, hook, cliffhanger, 'would a new viewer be confused?'). Written but <b>not executed</b> here (no network in my build environment); the shipped results are heuristic-only. Human editor stays final approver.")]
s+= [P("3. Top of the ranking (full list in outputs/promos.md)",H)]
rows=[["#","Ep","Segment","Hook (first 3 s)","Cliffhanger"],
["1","15","00:44.8-01:26.0","\"Get out of the way!\"","Thugs: \"You want to fight us, veteran?\""],
["2","27","00:44.5-01:32.4","\"What is your husband's name?\"","\"...you knew better than every physician?\""],
["3","11","00:58.0-01:24.0","\"Stop! Those are my mother's medicines!\"","Gerald: \"Going to strike a gentleman...?\""],
["4","28","00:46.8-01:24.4","\"Let me help her!\"","\"My mother's locket!\""],
["5","1","00:57.0-01:21.2","\"You let me believe I was walking toward my husband!\"","\"Father...\" (nobody answers)"],
["6","28","01:35.2-02:18.5","Juliana's secret identity exposed","\"...before he sends you to the gallows.\""]]
t=Table([[P(c,C) for c in r] for r in rows],colWidths=[7*mm,9*mm,28*mm,66*mm,72*mm])
t.setStyle(TableStyle([('GRID',(0,0),(-1,-1),0.3,colors.grey),('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e8e8f4')),('VALIGN',(0,0),(-1,-1),'TOP'),('TOPPADDING',(0,0),(-1,-1),1.2),('BOTTOMPADDING',(0,0),(-1,-1),1.2)]))
s+=[t,Spacer(1,3),P("<b>Why this order:</b> rank 1-3 open on a direct confrontation and end on a taunt/accusation with the outcome unresolved; ep 1 and 28 are the show's two signature humiliation beats. Recommended posting order: lead with the abandonment/humiliation promos (ep 1, 2) for cold audiences since the premise is clearest there, then the confrontation promos; hold back late-series twist promos (ep 45 'not lawful wife', ep 36 'dead Duke') for retargeting viewers who already know the leads.")]
s+= [P("4. How I checked quality, and where it fails",H),
 bul("<b>Check 1 - cliffhanger scorer vs Claude-made labels.</b> The last two lines of all 50 episodes were labelled by Claude (24 strong cliffhangers; single rater, an AI, generous) and I have not independently re-labelled them. Scoring the final-30-s window of each: AUC = <b>0.61</b>, precision@15 = <b>0.67</b>. Better than chance but weak: it is a rough filter, not a judge. Before adding the soft-ending penalty, the 'episode ending' bonus alone treated all 50 endings as equal; many are soft (ep 6, 8, 17, 19: 'I don't feel afraid', 'Perhaps I was wrong')."),
 bul("<b>Check 2 - manual read of the top 25.</b> Most are plausible clips; the failures below are real."),
 bul("<b>Failure A, generic hooks:</b> #1 (ep 15) opens on 'Get out of the way!' which is any thug, any show. The lexicon rewards charged words but cannot tell a show-specific shock from a generic shout. #6's hook is an action line, not speech, so it needs a visual cut-in that the screenplay cannot confirm."),
 bul("<b>Failure B, no context:</b> clips from mid-plot (ep 27, 33, 34: poisoning, trial) lean on earlier episodes; the stand-alone score is only a proxy (speaker count, scenes, kinship cue). A new viewer may not know who Catherine or Gerald are."),
 bul("<b>Failure C, near-duplicates:</b> ep 28 and ep 11 each place twice; the selector prevents overlap but not 'same beat, shifted by 2 s'. Stitched promos rarely win; they are scored down because the join may confuse."),
 bul("<b>Failure D, text-only blind spot:</b> no access to video, acting or music, so a slap that looks great but has no dialogue is under-ranked, and screenplay timestamps could drift from the final cut. A human must watch the cut before posting.")]
s+= [P("5. Scale and cost; AI usage",H),
 bul("Heuristic pass is CPU-only: ~13k windows / 50 episodes in seconds, so zero marginal cost for every new show each week. LLM rerank only touches the top 60 candidates per show (~60 calls of ~600 tokens): a few cents on a paid model, free on free tiers. Model is a config value, so a stronger API model can be dropped in at the interview."),
 bul("Editor workflow: tool outputs a shortlist with timestamps + reasons + risks; editor watches ~25 clips instead of ~100 min, and approves. Success metric once live: share of editor-approved promos among top 10 (target &gt;50%), time-to-first-promo per show, then promo click-through/install per post."),
 bul("<b>Tools used:</b> Claude (planned, wrote and debugged the code and this doc). <b>Where AI got it wrong:</b> my first scoring pass kept the field name <i>hook</i> for both the numeric score and the hook text, so the first full run crashed with a TypeError; and my first parser silently read episode 6 as 0 seconds because of header casing. Both caught by running, not by reading. The ending rules were tuned against these same labels, so 0.61 is optimistic.")]
doc.build(s)



