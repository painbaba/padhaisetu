#!/usr/bin/env python3
"""PadhaiSetu RAG retriever — stdlib-only BM25 over data/rag_chunks.jsonl.
Usage:
    python rag.py "query text" [--class 10] [--subject science] [--lang hi] [--k 4]
"""
import json, math, re, os, sys, argparse

_HERE = os.path.dirname(os.path.abspath(__file__))
STORE = os.path.join(_HERE, "data", "rag_chunks.jsonl")

_stop = set("""a an the is are was were be been being to of in on at for with and or not
it its this that these those as by from we you he she they them his her their our your
i me my mine do does did done can could will would shall should may might must have has had
का के की है हैं था थे थी को में से पर और या नहीं भी यह वह इस उस कि जो तो ही एक हो होता होती होते कर करने किया""".split())

_tok = re.compile(r"[^\W_]+", re.UNICODE)

def tokenize(t):
    return [w.lower() for w in _tok.findall(t) if len(w) > 1 and w.lower() not in _stop]

class Retriever:
    def __init__(self):
        self.docs = []
        self.tf = []
        self.df = {}
        self.avgdl = 0.0
        self._load()

    def _load(self):
        with open(STORE, encoding="utf-8") as f:
            for line in f:
                d = json.loads(line)
                toks = tokenize(d["text"])
                self.docs.append(d)
                self.tf.append(toks)
                for w in set(toks):
                    self.df[w] = self.df.get(w, 0) + 1
        self.N = len(self.docs)
        self.avgdl = sum(len(t) for t in self.tf) / max(self.N, 1)

    def search(self, q, k=4, cls=None, subj=None, lang=None):
        qt = tokenize(q)
        k1, b = 1.5, 0.75
        scores = []
        for i, toks in enumerate(self.tf):
            d = self.docs[i]
            if cls and d["class"] != str(cls): continue
            if subj and d["subject"] != subj: continue
            if lang and d["lang"] != lang: continue
            s = 0.0
            dl = len(toks)
            tfm = {}
            for w in toks: tfm[w] = tfm.get(w, 0) + 1
            for w in qt:
                f = tfm.get(w)
                if not f: continue
                idf = math.log(1 + (self.N - self.df.get(w, 0) + 0.5) / (self.df.get(w, 0) + 0.5))
                s += idf * (f * (k1 + 1)) / (f + k1 * (1 - b + b * dl / self.avgdl))
            if s > 0: scores.append((s, i))
        scores.sort(reverse=True)
        out, seen = [], set()
        for s, i in scores:
            key = (self.docs[i]["source"], self.docs[i]["text"][:80])
            if key in seen: continue
            seen.add(key)
            out.append({"score": round(s, 2), **{x: self.docs[i][x] for x in ("source", "class", "subject", "lang")}, "text": self.docs[i]["text"]})
            if len(out) >= k: break
        return out

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("query")
    ap.add_argument("--class", dest="cls")
    ap.add_argument("--subject", dest="subj")
    ap.add_argument("--lang")
    ap.add_argument("--k", type=int, default=4)
    a = ap.parse_args()
    r = Retriever()
    for hit in r.search(a.query, k=a.k, cls=a.cls, subj=a.subj, lang=a.lang):
        print(f"[{hit['score']}] {hit['source']} ({hit['class']}/{hit['subject']}/{hit['lang']})")
        print("   ", hit["text"][:180].replace("\n", " "))
