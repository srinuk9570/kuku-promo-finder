"""QA: does cliff_score separate strong episode endings from weak ones? (single-rater labels by the author, see doc)"""
import sys; sys.path.insert(0,'.')
from promo_finder import *
STRONG = {1,3,4,15,23,24,26,27,28,30,31,32,34,35,36,38,42,43,44,45,46,11,13,37}
def auc(pos, neg):
    w=sum((p>n)+0.5*(p==n) for p in pos for n in neg); return w/(len(pos)*len(neg))
if __name__=="__main__":
    eps=load_pack(sys.argv[1]); rows=[]
    for e in eps:
        b=beats_of(e); et=e["duration"]; tail=[x for x in b if x["start"]>=et-30]
        c,_=cliff_score(tail, et, et, True); rows.append((c,e["num"]))
    pos=[c for c,n in rows if n in STRONG]; neg=[c for c,n in rows if n not in STRONG]
    print(f"AUC(strong vs other endings) = {auc(pos,neg):.2f}  (n_strong={len(pos)}, n_other={len(neg)})")
    top=sorted(rows,reverse=True)[:15]; print("top-15 by cliff_score:",[n for c,n in top]); print("precision@15 =",sum(n in STRONG for c,n in top)/15)
