"""M10 gates: mock board exam — triggers, MPBSE paper shape, exam rules (skip,
no hints/remediation/feedback), bilingual scorecard, mock_attempts history,
dashboard counters, NLU widening, and the practice handoff."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from app import db, engine, flows, nlu, qbank  # noqa: E402


@pytest.fixture()
def fresh(tmp_path, monkeypatch):
    monkeypatch.setenv("PADHAISETU_DB", str(tmp_path / "mock.db"))
    db.init_db()
    qbank.load_all(force=True)
    yield


def send(phone, text):
    return flows.handle_message(phone, text)


def session_ctx(phone):
    uid = int(db.scalar("SELECT id FROM users WHERE phone=?", (phone,)))
    row = db.query_one("SELECT state, context_json FROM chat_sessions WHERE user_id=?",
                       (uid,))
    return uid, row["state"], json.loads(row["context_json"])


def onboard(phone, grade="10", subject="1"):
    send(phone, "namaste")
    send(phone, "1")          # Hindi
    send(phone, grade)        # class
    send(phone, subject)      # subject -> diagnostic
    for _ in range(5):
        _, st, c = session_ctx(phone)
        qid = c["queue"][c["idx"]]["qid"]
        ci = int(db.scalar("SELECT correct_idx FROM questions WHERE id=?", (qid,)))
        send(phone, str(ci + 1))
    _, st, _c = session_ctx(phone)
    assert st == "menu"


def pending_qid(phone):
    _, _st, c = session_ctx(phone)
    return c["queue"][c["idx"]]["qid"], c


def correct_reply(phone):
    qid, _c = pending_qid(phone)
    ci = int(db.scalar("SELECT correct_idx FROM questions WHERE id=?", (qid,)))
    return str(ci + 1)


def wrong_reply(phone):
    qid, _c = pending_qid(phone)
    row = db.query_one("SELECT options_json, correct_idx FROM questions WHERE id=?",
                       (qid,))
    n = len(row["options_json"].split("|"))
    return str(((int(row["correct_idx"]) + 1) % n) + 1)


# ---------- NLU widening ----------

def test_nlu_mock_triggers():
    assert nlu.classify("mock") == nlu.MOCK
    assert nlu.classify("MOCK") == nlu.MOCK
    assert nlu.classify("मॉक") == nlu.MOCK
    assert nlu.classify("पेपर") == nlu.MOCK
    assert nlu.classify("4") == nlu.NONE          # menu option, not a text intent


def test_nlu_explain_widened_with_kya_hai_and_what_is():
    assert nlu.classify("प्रकाश संश्लेषण क्या है") == nlu.EXPLAIN
    assert nlu.classify("क्या है फोटोसिंथेसिस") == nlu.EXPLAIN
    assert nlu.classify("what is photosynthesis") == nlu.EXPLAIN
    assert nlu.classify("What is a quadratic equation?") == nlu.EXPLAIN
    # older triggers keep working; non-questions stay none
    assert nlu.classify("यह समझाइए") == nlu.EXPLAIN
    assert nlu.classify("2") == nlu.NONE
    assert nlu.classify("namaste") == nlu.GREET


def test_nlu_pick_menu_number_accepts_four():
    assert nlu.pick_menu_number("4") == 4
    assert nlu.pick_menu_number("4)") == 4
    assert nlu.pick_menu_number("5") is None


# ---------- triggers from menu / menu option ----------

def test_mock_hindi_trigger_starts_full_paper(fresh):
    phone = "+91555020001"
    onboard(phone)
    replies = send(phone, "मॉक")
    uid, st, ctx = session_ctx(phone)
    assert st == "mock"
    assert ctx["mode"] == "mock" and len(ctx["queue"]) == engine.MOCK_SIZE
    intro = "\n".join(replies)
    assert "मॉक" in intro and "skip" in intro          # skip rule announced up front
    assert "(1 अंक)" in replies[-1]                    # first objective Q carries marks


def test_mock_menu_option_and_paper_word_trigger(fresh):
    phone = "+91555020002"
    onboard(phone)
    send(phone, "4")
    _, st, _c = session_ctx(phone)
    assert st == "mock"

    phone2 = "+91555020003"
    onboard(phone2)
    send(phone2, "पेपर")
    _, st2, _c2 = session_ctx(phone2)
    assert st2 == "mock"


# ---------- paper shape (MPBSE 2026 mix, seeded per attempt) ----------

def test_mock_paper_shape_matches_board_pattern(fresh):
    phone = "+91555020004"
    onboard(phone)
    send(phone, "mock")
    _, st, ctx = session_ctx(phone)
    rows = [db.query_one("SELECT * FROM questions WHERE id=?", (e["qid"],))
            for e in ctx["queue"]]
    assert len({r["id"] for r in rows}) == 23                       # no repeats
    marks = [int(r["marks"]) for r in rows]
    assert marks == [1] * 5 + [2] * 12 + [3] * 3 + [4] * 3         # objective first, ascending
    assert all(r["qtype"] in ("mcq", "fill", "tf") for r in rows[:5])
    assert sum(marks) == 50 and ctx["max_marks"] == 50
    # OR siblings never both served
    toks = []
    for r in rows:
        tok = None
        if r["gen_params_json"]:
            try:
                tok = json.loads(r["gen_params_json"]).get("or_pair")
            except Exception:
                tok = None
        if tok:
            toks.append(tok)
    assert len(toks) == len(set(toks))


# ---------- exam rules: no hints, no feedback, skip allowed ----------

def test_mock_wrong_answer_no_hint_no_feedback_moves_on(fresh):
    phone = "+91555020005"
    onboard(phone)
    send(phone, "mock")
    replies = send(phone, wrong_reply(phone))
    joined = "\n".join(replies)
    assert "संकेत" not in joined and "हल:" not in joined           # no hint/solution
    assert "गलत हुआ" not in joined and "सही उत्तर" not in joined   # no verdict either
    _, st, ctx = session_ctx(phone)
    assert st == "mock" and ctx["idx"] == 1                        # straight to next Q
    assert ctx["records"][0]["earned"] == 0

    gibberish = send(phone, "kuchh bhi")
    joined_g = "\n".join(gibberish)
    assert "skip" in joined_g                                      # choose-or-skip prompt
    _, st, ctx = session_ctx(phone)
    assert ctx["idx"] == 1                                         # index unchanged

    send(phone, "skip")
    _, st, ctx = session_ctx(phone)
    assert ctx["idx"] == 2
    assert ctx["records"][1]["skipped"] is True                    # skip -> 0 marks
    assert ctx["earned"] == 0


def test_mock_never_remediates_even_on_repeat_wrong(fresh):
    phone = "+91555020006"
    onboard(phone)
    send(phone, "mock")
    for i in range(3):
        send(phone, wrong_reply(phone))
        _, st, ctx = session_ctx(phone)
        assert st == "mock"
        assert "remediating" not in ctx                            # exam: no remediation
        assert all(not r.get("skipped") for r in ctx["records"])


# ---------- full journey: scorecard, DB history, practice handoff ----------

def run_board_mock(phone):
    """Correct for idx 0..16, skip idx 17 (3-mark), wrong for the rest.
    Returns every reply bubble of the paper (scorecard lands at the end)."""
    replies = send(phone, "mock")
    while True:
        _, st, ctx = session_ctx(phone)
        if st != "mock":
            return replies
        idx = int(ctx["idx"])
        if idx <= 16:
            replies += send(phone, correct_reply(phone))
        elif idx == 17:
            replies += send(phone, "छोड़ें")
        else:
            replies += send(phone, wrong_reply(phone))


def test_mock_scorecard_sections_total_weak_skills_handoff(fresh):
    phone = "+91555020007"
    onboard(phone)
    replies = run_board_mock(phone)
    _, st, ctx = session_ctx(phone)
    assert st == "menu"

    scorecard = "\n".join(replies)
    assert "स्कोरकार्ड" in scorecard
    assert "- वस्तुनिष्ठ: 5/5" in scorecard
    assert "- लघु उत्तरीय (2 अंक): 24/24" in scorecard
    assert "- मध्यम उत्तरीय (3 अंक): 0/9" in scorecard
    assert "- दीर्घ उत्तरीय (4 अंक): 0/12" in scorecard
    assert "कुल: 29/50 (58.0%)" in scorecard
    assert "कमज़ोर टॉपिक" in scorecard
    assert "practice करने के लिए 1 भेजिए" in scorecard

    row = db.query_one(
        """SELECT * FROM mock_attempts WHERE user_id=?
           ORDER BY id DESC LIMIT 1""", (uid_of(phone),))
    assert row is not None
    assert int(row["earned_marks"]) == 29 and int(row["total_marks"]) == 50
    assert abs(float(row["pct"]) - 58.0) < 0.01
    detail = json.loads(row["detail_json"])
    assert len(detail) == 23
    assert sum(1 for d in detail if d["skipped"]) == 1
    assert {d["skill_id"] for d in detail}                          # skill_id recorded
    mock_mode = int(db.scalar(
        "SELECT COUNT(*) FROM attempts WHERE user_id=? AND mode='mock'", (uid_of(phone),)))
    assert mock_mode == 23


def uid_of(phone):
    return int(db.scalar("SELECT id FROM users WHERE phone=?", (phone,)))


def test_practice_after_mock_targets_weakest_mock_skills(fresh):
    phone = "+91555020008"
    onboard(phone)
    run_board_mock(phone)
    _, st, ctx = session_ctx(phone)
    assert st == "menu"
    focus = ctx.get("mock_focus") or []
    assert 0 < len(focus) <= 3

    send(phone, "wrong answer text")                                # menu chatter safe
    replies = send(phone, "1")
    _, st, pctx = session_ctx(phone)
    assert st == "practice"
    assert pctx["queue"][0]["skill"] in focus                       # weak skills first
    assert len(pctx["queue"]) == 5
    assert any("अभ्यास सेट" in m for m in replies)


def test_mock_works_after_practice_completes(fresh):
    phone = "+91555020009"
    onboard(phone)
    send(phone, "1")                                                # board practice set
    _, st, pctx = session_ctx(phone)
    assert st == "practice" and len(pctx["queue"]) == 23
    while True:
        _, st, _c = session_ctx(phone)
        if st != "practice":
            break
        send(phone, correct_reply(phone))
    _, st, _c = session_ctx(phone)
    assert st == "menu"
    send(phone, "mock")                                             # then the exam
    _, st, ctx = session_ctx(phone)
    assert st == "mock" and ctx["mode"] == "mock"


def test_mock_fallback_plain_paper_for_non_board_grade(fresh):
    phone = "+91555020010"
    onboard(phone, grade="8")
    send(phone, "mock")
    _, st, ctx = session_ctx(phone)
    assert st == "mock" and ctx["mode"] == "mock"
    assert 1 <= len(ctx["queue"]) <= engine.MOCK_SIZE
    total = len(ctx["queue"])
    for _ in range(total):
        send(phone, correct_reply(phone))
    _, st, ctx = session_ctx(phone)
    assert st == "menu"
    row = db.query_one("SELECT * FROM mock_attempts WHERE user_id=?", (uid_of(phone),))
    assert row is not None
    assert int(row["earned_marks"]) == int(row["total_marks"]) == total
    assert float(row["pct"]) == 100.0


# ---------- pure helpers ----------

def test_engine_mock_sections_and_weak_skills_pure_math():
    records = [
        {"skill_id": "sA", "marks": 1, "earned": 1},
        {"skill_id": "sB", "marks": 2, "earned": 2},
        {"skill_id": "sB", "marks": 2, "earned": 0},
        {"skill_id": "sC", "marks": 3, "earned": 3},
        {"skill_id": "sD", "marks": 4, "earned": 0, "skipped": True},
        {"skill_id": "sD", "marks": 4, "earned": 4},
    ]
    secs = {s["name"]: s for s in engine.mock_sections(records)}
    assert (secs["objective"]["got"], secs["objective"]["max"]) == (1, 1)
    assert (secs["short"]["got"], secs["short"]["max"]) == (2, 4)
    assert (secs["medium"]["got"], secs["medium"]["max"]) == (3, 3)
    assert (secs["long"]["got"], secs["long"]["max"]) == (4, 8)

    weak = engine.weak_skills_from_records(records)
    assert weak[0] == "sD"                 # 50% on 8 marks -> weakest
    assert "sC" not in weak                # perfect skills excluded
    assert engine.weak_skills_from_records(
        [{"skill_id": "x", "marks": 2, "earned": 2}]) == []


# ---------- dashboard ----------

def test_dashboard_shows_mocks_taken_and_latest_mock_score(fresh):
    phone = "+91555020011"
    onboard(phone)
    run_board_mock(phone)

    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        html = c.get("/dashboard").text
    mocks = int(db.scalar("SELECT COUNT(*) FROM mock_attempts"))
    assert '<div class="l">Mocks taken</div>' in html
    assert f'<div class="n">{mocks}</div>' in html
    assert "mock <b>29/50</b>" in html                              # latest score in card
