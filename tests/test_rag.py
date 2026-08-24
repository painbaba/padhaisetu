"""M9 gates: RAG retriever singleton, filtered search, explain intent with
bilingual citation in chat + /api/explain endpoint, no-key fallback, dashboard
corpus stat."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from app import db, flows, qbank, rag  # noqa: E402


@pytest.fixture(scope="module")
def ret():
    return rag.get_retriever()


@pytest.fixture()
def fresh(tmp_path, monkeypatch):
    monkeypatch.setenv("PADHAISETU_DB", str(tmp_path / "rag.db"))
    db.init_db()
    qbank.load_all(force=True)
    yield


@pytest.fixture()
def client(fresh):
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c


def send(phone, text):
    return flows.handle_message(phone, text)


def state_of(phone):
    uid = int(db.scalar("SELECT id FROM users WHERE phone=?", (phone,)))
    return db.scalar("SELECT state FROM chat_sessions WHERE user_id=?", (uid,))


def onboard_science(phone=":+918001", grade="10"):
    send(phone, "namaste")
    send(phone, "1")      # Hindi
    send(phone, grade)
    send(phone, "2")      # science -> diagnostic starts
    for _ in range(5):    # answer diagnostic correctly -> lands in menu
        import json as _json
        uid = int(db.scalar("SELECT id FROM users WHERE phone=?", (phone,)))
        ctx = _json.loads(db.scalar(
            "SELECT context_json FROM chat_sessions WHERE user_id=?", (uid,)))
        if not ctx.get("queue"):
            break
        qid = ctx["queue"][ctx["idx"]]["qid"]
        ci = int(db.scalar("SELECT correct_idx FROM questions WHERE id=?", (qid,)))
        send(phone, str(ci + 1))


# ---------- retriever ----------

def test_retriever_loads_full_corpus_once(ret):
    assert ret.N == 2816
    assert rag.get_retriever() is ret          # singleton


def test_search_hits_respect_metadata_filters(ret):
    for h in ret.search("photosynthesis", k=3, cls="10", subj="science"):
        assert h["class"] == "10" and h["subject"] == "science"
        assert h["source"] and h["text"]
    hi_hits = ret.search("गुरुत्वाकर्षण", k=3, cls="9", subj="science", lang="hi")
    assert hi_hits and all(h["lang"] == "hi" for h in hi_hits)


def test_search_falls_back_when_lang_has_no_coverage(ret):
    # every class-8 chunk carries lang=en metadata; a hi request must still hit
    hits = rag.search("crop production", cls="8", subj="science", lang="hi")
    assert hits and all(h["class"] == "8" and h["subject"] == "science"
                        for h in hits)


# ---------- citations ----------

def test_pretty_source_bilingual_formats():
    assert rag.pretty_source({"source": "NCERT sci10_hi ch9"}, "hi") == \
        "NCERT विज्ञान कक्षा 10, अध्याय 9"
    assert rag.pretty_source({"source": "NCERT sci10_hi ch9"}, "en") == \
        "NCERT Science class 10, chapter 9"
    assert rag.pretty_source(
        {"source": "MPBSE 2026 10th_Maths_basic"}, "hi") == \
        "MPBSE 2026 मॉडल पेपर — कक्षा 10 गणित (Basic)"
    assert rag.pretty_source(
        {"source": "MPBSE 2026 12th_Physics"}, "en") == \
        "MPBSE 2026 sample paper — class 12 Physics"


def test_explain_result_carries_excerpt_citation_chunks(ret):
    res = rag.explain("fundamental theorem of arithmetic",
                      cls="10", subj="maths", lang="en")
    assert len(res["excerpt"]) <= 401
    assert res["citation"].startswith("NCERT")
    assert res["chunks"] and res["chunks"][0]["text"]


# ---------- chat flow: explain intent ----------

def test_explain_intent_in_menu_answers_with_hindi_citation(fresh):
    phone = "+91910000001"
    onboard_science(phone, grade="9")
    replies = send(phone, "how does photosynthesis work")
    joined = "\n".join(replies)
    assert "स्रोत:" in joined                       # citation in user language
    assert "NCERT" in joined
    assert state_of(phone) == "menu"


def test_explain_intent_during_practice_keeps_question_pending(fresh):
    phone = "+91910000002"
    onboard_science(phone, grade="10")
    send(phone, "1")                                # start board-pattern set
    assert state_of(phone) == "practice"
    replies = send(phone, "explain why photosynthesis is important")
    joined = "\n".join(replies)
    assert "स्रोत:" in joined
    assert any("प्रश्न" in m for m in replies[-1:])  # current question re-rendered
    assert state_of(phone) == "practice"


def test_diagnostic_state_not_hijacked_by_explain_words(fresh):
    phone = "+91910000003"
    onboard_science(phone, grade="9")               # now at menu
    send(phone, "reset")
    send(phone, "1")                                # hindi
    send(phone, "9")                                # grade -> subject asked
    send(phone, "why")                              # during onb_subject: menu-ish
    # onboarding still owns the turn; no crash, still an onboarding state
    assert state_of(phone) in ("onb_subject", "onb_lang")


def test_explain_no_hits_gets_graceful_none_message(fresh):
    phone = "+91910000004"
    onboard_science(phone, grade="9")
    replies = send(phone, "zzqqxx gibberish क्यों")
    joined = "\n".join(replies)
    assert ("कोई पैसेज नहीं मिला" in joined) or ("could not find" in joined.lower())


# ---------- /api/explain ----------

def test_api_explain_grounding_and_shape_without_key(client, monkeypatch):
    from app import config
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    config.OPENAI_API_KEY = ""
    r = client.post("/api/explain", json={
        "phone_or_session": "+91910000011",
        "query": "quadratic equation roots",
    })
    assert r.status_code == 200
    data = r.json()
    assert data["chunks"] and len(data["chunks"]) <= 2
    assert data["source"].startswith(("NCERT", "MPBSE"))
    assert data["answer_text"].startswith(data["chunks"][0]["text"][:60])
    assert ("स्रोत: " + data["source"]) in data["answer_text"]  # citation last line
    # user row was auto-created with default lang so citation line is Hindi
    assert "स्रोत:" in data["answer_text"]


def test_api_explain_gpt_synthesis_wired_when_key_set(client, monkeypatch):
    from app import config
    from app.flows import ragflow
    monkeypatch.setattr(rag, "_gpt_explain",
                        lambda *a, **k: "प्रकाश संश्लेषण में पौधा अपना भोजन बनाता है।")
    config.OPENAI_API_KEY = "test-key"
    try:
        r = client.post("/api/explain", json={
            "phone_or_session": "+91910000012",
            "query": "photosynthesis",
        })
        data = r.json()
        assert data["answer_text"].startswith("आसान शब्दों में:")
        assert "पौधा" in data["answer_text"]
        assert "स्रोत:" in data["answer_text"]
    finally:
        config.OPENAI_API_KEY = ""


# ---------- dashboard ----------

def test_dashboard_shows_rag_corpus_stat(client):
    html = client.get("/dashboard").text
    assert "RAG corpus chunks" in html
    assert str(rag.total_chunks()) in html
    assert "__RAG_CHUNKS__" not in html
