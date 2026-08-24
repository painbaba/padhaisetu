"""RAG bridge: wraps the repo-root stdlib BM25 retriever (rag.py, do-not-edit)
as a process-wide singleton and serves grounded explain answers.

Loads data/rag_chunks.jsonl once (~3s, 2816 chunks). Never raises outwards:
every failure degrades to "no hits" so chat/API paths stay graceful.
"""
import importlib.util
import json
import re

from . import config

ROOT = config.REPO_ROOT
MANIFEST_PATH = ROOT / "data" / "rag_manifest.json"

TOP_K = 2
EXCERPT_LEN = 400

_retriever = None


def get_retriever():
    """Singleton: loads rag.py from repo root and builds Retriever exactly once."""
    global _retriever
    if _retriever is None:
        spec = importlib.util.spec_from_file_location(
            "padhaisetu_rag_retriever", ROOT / "rag.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _retriever = mod.Retriever()
    return _retriever


def total_chunks() -> int:
    try:
        return int(json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))["total"])
    except Exception:
        try:
            return int(get_retriever().N)
        except Exception:
            return 0


def search(query: str, cls=None, subj=None, lang=None, k: int = TOP_K):
    """Top-k chunks with metadata filters; retries without lang filter when the
    preferred language has no coverage for that class/subject."""
    try:
        r = get_retriever()
    except Exception:
        return []
    hits = []
    try:
        if lang:
            hits = r.search(query, k=k, cls=cls, subj=subj, lang=lang)
        if not hits:
            hits = r.search(query, k=k, cls=cls, subj=subj) if (cls or subj) \
                else r.search(query, k=k)
    except Exception:
        return []
    return hits


_NCERT_RE = re.compile(r"^NCERT ([a-z]+)(\d+)_[a-z]+ ch(\d+)$")
_MPBSE_RE = re.compile(r"^MPBSE 2026 (\d+)th_(.+)$")

_SUBJECT_HI = {"maths": "गणित", "sci": "विज्ञान"}
_SUBJECT_EN = {"maths": "Maths", "sci": "Science"}
_MPBSE_SUBJECT_HI = {
    "Maths": "गणित", "Science": "विज्ञान", "Social_Science": "सामाजिक विज्ञान",
    "Biology": "जीव विज्ञान", "Physics": "भौतिक विज्ञान", "CHEMISTRY": "रसायन विज्ञान",
    "Book_keeping_and_accountancy": "बहीखाता एवं लेखाशास्त्र",
}
_MPBSE_VARIANTS = {"basic", "standard"}


def pretty_source(hit: dict, lang: str) -> str:
    """'NCERT sci10_hi ch9' -> 'NCERT विज्ञान कक्षा 10, अध्याय 9' (hi) /
    'NCERT Science class 10, chapter 9' (en); MPBSE papers likewise."""
    src = str(hit.get("source", ""))
    m = _NCERT_RE.match(src)
    if m:
        code, cls, ch = m.group(1), m.group(2), m.group(3)
        if lang == "hi":
            name = _SUBJECT_HI.get(code, code)
            return f"NCERT {name} कक्षा {cls}, अध्याय {ch}"
        name = _SUBJECT_EN.get(code, code)
        return f"NCERT {name} class {cls}, chapter {ch}"
    m = _MPBSE_RE.match(src)
    if m:
        cls, rest = m.group(1), m.group(2)
        variant = ""
        parts = rest.rsplit("_", 1)
        if len(parts) == 2 and parts[1].lower() in _MPBSE_VARIANTS:
            rest, variant = parts[0], f" ({parts[1].capitalize()})"
        if lang == "hi":
            name = _MPBSE_SUBJECT_HI.get(rest, rest.replace("_", " "))
            return f"MPBSE 2026 मॉडल पेपर — कक्षा {cls} {name}{variant}"
        name = rest.replace("_", " ")
        return f"MPBSE 2026 sample paper — class {cls} {name}{variant}"
    return src


def _trim(text: str, n: int = EXCERPT_LEN) -> str:
    t = " ".join((text or "").split())
    if len(t) <= n:
        return t
    cut = t[:n].rsplit(" ", 1)[0]
    return cut + "…"


def _gpt_explain(query: str, excerpt: str, lang: str, grade=None) -> str | None:
    """Optional friendly 2-sentence synthesis via OpenAI; None on any failure."""
    if not config.OPENAI_API_KEY:
        return None
    try:
        import httpx

        prompt = (
            "Tum ek MP Board tutor ho. Neeche diye textbook passage se student ke "
            "sawaal ka jawab {lang} mein sirf 2 dostana vaakyon mein do. "
            "Passage ke bahar ki baat mat karna.\nSawaal: {q}\n"
            "Passage: {p}".format(
                lang="Hindi" if lang == "hi" else "simple English",
                q=query, p=excerpt[:600],
            )
        )
        with httpx.Client(timeout=4.0) as client:
            r = client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {config.OPENAI_API_KEY}"},
                json={
                    "model": config.OPENAI_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 120,
                },
            )
            r.raise_for_status()
            out = r.json()["choices"][0]["message"]["content"].strip()
            return out[:500] or None
    except Exception:
        return None


def explain(query: str, cls=None, subj=None, lang: str = "hi"):
    """Retrieve + assemble a grounded explanation result.

    Returns dict(excerpt, citation, synth, chunks, hit).
    Composition into user-facing text lives in flows.ragflow so this module
    stays free of chat strings."""
    query = (query or "").strip()
    hits = search(query, cls=cls, subj=subj,
                  lang=(lang or None))
    if not hits:
        return {"excerpt": "", "citation": "", "synth": None, "chunks": [],
                "hit": None}
    top = hits[0]
    excerpt = _trim(top["text"])
    citation = pretty_source(top, lang)
    synth = _gpt_explain(query, excerpt, lang, grade=cls)
    chunks = [
        {"score": h.get("score"), "source": h.get("source"),
         "class": h.get("class"), "subject": h.get("subject"),
         "lang": h.get("lang"), "text": _trim(h.get("text", ""))}
        for h in hits
    ]
    return {"excerpt": excerpt, "citation": citation, "synth": synth,
            "chunks": chunks, "hit": top}
