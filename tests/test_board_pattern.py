"""M7+M8 gates: board-pattern schema defaults, generator shape, and
grade-10 sessions served in the official MPBSE 2026 sample-paper mix."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from app import db, engine, flows, qbank  # noqa: E402
from app.models import Question  # noqa: E402
from data.gen_math import generate_board_pattern  # noqa: E402


@pytest.fixture()
def fresh(tmp_path, monkeypatch):
    monkeypatch.setenv("PADHAISETU_DB", str(tmp_path / "board.db"))
    db.init_db()
    qbank.load_all(force=True)
    yield


def send(phone, text):
    return flows.handle_message(phone, text)


def session_ctx(phone):
    uid = int(db.scalar("SELECT id FROM users WHERE phone=?", (phone,)))
    row = db.query_one("SELECT context_json FROM chat_sessions WHERE user_id=?", (uid,))
    return uid, json.loads(row["context_json"])


def onboard(phone, grade="10", subject="1"):
    send(phone, "namaste")
    send(phone, "1")        # Hindi
    send(phone, grade)      # class -> onb_subject
    return send(phone, subject)  # subject -> diagnostic starts


def answer_current_correctly(phone):
    uid, c = session_ctx(phone)
    if c.get("remediating"):
        qid = c["remedial_qid"]
    else:
        qid = c["queue"][c["idx"]]["qid"]
    ci = int(db.scalar("SELECT correct_idx FROM questions WHERE id=?", (qid,)))
    return str(ci + 1)


# ---------- M7: schema defaults ----------

def test_question_model_defaults_marks_and_qtype():
    q = Question(
        id=1, subject="maths", grade=10, skill_id="m10c1s1", difficulty=2,
        text_hi="hi", text_en="en", options=["a", "b", "c", "d"], correct_idx=0,
        hint_hi="h", hint_en="h", solution_hi="s", solution_en="s",
    )
    assert q.marks == 1
    assert q.qtype is None


def test_legacy_bank_rows_get_loader_defaults(fresh):
    # curated science rows have no marks/qtype keys at all
    row = db.query_one(
        "SELECT * FROM questions WHERE subject='science' AND grade=8 LIMIT 1")
    assert row is not None
    assert int(row["marks"]) == 1 and row["qtype"] is None
    # classic parametric maths templates stay untagged too
    legacy = db.query_one(
        "SELECT COUNT(*) AS n FROM questions WHERE subject='maths' AND grade=10 "
        "AND qtype IS NULL")
    assert int(legacy["n"]) > 50


# ---------- M7: board-pattern bank + generator shape ----------

def test_board_items_present_with_expected_counts(fresh):
    def count(where, params=()):
        return int(db.scalar(
            f"SELECT COUNT(*) FROM questions WHERE subject='maths' AND grade=10 "
            f"AND active=1 AND {where}", params))

    obj = count("marks<=1 AND qtype IN ('mcq','fill','tf')")
    two = count("marks=2")
    three = count("marks=3")
    four = count("marks=4")
    assert obj >= engine.BOARD_SHAPE[0][0]
    assert two >= engine.BOARD_SHAPE[1][0]
    assert three >= engine.BOARD_SHAPE[2][0] * 2   # mains + OR siblings
    assert four >= engine.BOARD_SHAPE[3][0] * 2

    tagged = db.query(
        "SELECT * FROM questions WHERE subject='maths' AND grade=10 AND qtype IS NOT NULL")
    assert tagged
    for r in tagged:
        assert r["text_hi"] and r["text_en"]
        assert r["hint_hi"] and r["hint_en"]
        assert r["solution_hi"] and r["solution_en"]
        opts = (r["options_json"] or "").split("|")
        assert len(opts) == len(set(opts)) and len(opts) >= 2
        assert 0 <= int(r["correct_idx"]) < len(opts)


def test_generate_board_pattern_set_shape_and_determinism():
    a = generate_board_pattern(10, seed=99, sets=1)
    b = generate_board_pattern(10, seed=99, sets=1)
    assert a == b  # deterministic regeneration
    mains = a["main"]
    assert len(mains) == 23
    marks_seq = [it["marks"] for it in mains]
    assert marks_seq == [1] * 5 + [2] * 12 + [3] * 3 + [4] * 3  # objective first, ascending
    obj_types = {it["qtype"] for it in mains[:5]}
    assert {"mcq", "fill", "tf"} <= obj_types
    assert all(it["qtype"] in ("mcq", "fill", "tf") for it in mains[:5])
    # every 3/4-mark main has exactly one OR sibling sharing its token & shape
    pool = a["main"] + a["alt"]
    tokens = {}
    for it in pool:
        tok = it["gen_params"].get("or_pair")
        if tok:
            tokens.setdefault(tok, []).append(it)
    threes_fours = [it for it in mains if it["marks"] >= 3]
    assert len(threes_fours) == 6
    for it in threes_fours:
        sib = tokens[it["gen_params"]["or_pair"]]
        assert len(sib) == 2
        other = [x for x in sib if x is not it][0]
        assert other["marks"] == it["marks"] and other["qtype"] == it["qtype"]
    assert len(a["alt"]) == 6


# ---------- M8: grade-10 sessions serve the mixed format ----------

def test_class10_practice_serves_full_board_mix(fresh):
    phone = "+91555001001"
    onboard(phone)                      # class 10 maths -> diagnostic starts
    for _ in range(5):                  # finish diagnostic
        send(phone, answer_current_correctly(phone))
    replies = send(phone, "1")          # start today's practice set
    uid, ctx = session_ctx(phone)
    from app.flows import load_session
    st, _c = load_session(uid)
    assert st == "practice"
    assert ctx["board"] is True
    queue = ctx["queue"]
    assert len(queue) == 23             # 5 objective + 12x2m + 3x3m + 3x4m
    rows = [db.query_one("SELECT * FROM questions WHERE id=?", (e["qid"],)) for e in queue]
    assert len({r["id"] for r in rows}) == 23
    marks = [int(r["marks"]) for r in rows]
    assert marks == [1] * 5 + [2] * 12 + [3] * 3 + [4] * 3
    assert all(r["qtype"] in ("mcq", "fill", "tf") for r in rows[:5])
    # no OR pair may appear twice inside one session
    toks = []
    for r in rows:
        if r["gen_params_json"]:
            try:
                tok = json.loads(r["gen_params_json"]).get("or_pair")
            except Exception:
                tok = None
            if tok:
                toks.append(tok)
    assert len(toks) == len(set(toks))
    joined = "\n".join(replies)
    assert "बोर्ड" in replies[0]                       # board-pattern intro
    assert "(1 अंक)" in joined                        # marks shown next to number


def test_class10_diagnostic_objective_first_with_marks_labels(fresh):
    phone = "+91555001002"
    replies = onboard(phone)            # diagnostic starts immediately
    uid, ctx = session_ctx(phone)
    assert len(ctx["queue"]) == 5
    rows = [db.query_one("SELECT * FROM questions WHERE id=?", (e["qid"],))
            for e in ctx["queue"]]
    assert [int(r["marks"]) for r in rows] == [1, 1, 2, 2, 3]
    assert rows[0]["qtype"] in ("mcq", "fill", "tf")
    assert "(1 अंक)" in replies[-1]


def test_grade9_practice_keeps_legacy_format(fresh):
    phone = "+91555001003"
    onboard(phone, grade="9")           # maths
    for _ in range(5):
        send(phone, answer_current_correctly(phone))
    replies = send(phone, "1")
    uid, ctx = session_ctx(phone)
    assert len(ctx["queue"]) == 5
    assert ctx.get("board") is not True
    first_qid = ctx["queue"][0]["qid"]
    r = db.query_one("SELECT * FROM questions WHERE id=?", (first_qid,))
    assert r["qtype"] is None           # untagged legacy question
    assert "अंक):" not in "\n".join(replies)   # no marks suffix in labels


def test_pick_board_set_none_when_tagged_items_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("PADHAISETU_DB", str(tmp_path / "thin.db"))
    db.init_db()
    qbank.load_all(force=True)
    with db.connect() as conn:
        conn.execute("DELETE FROM questions WHERE qtype IS NOT NULL")
    db.execute("INSERT INTO users(phone, lang, grade, created_at) VALUES(?,?,?,?)",
               ("+91555001004", "hi", 10, db.iso()))
    uid = int(db.scalar("SELECT id FROM users WHERE phone='+91555001004'"))
    assert engine.pick_board_set(uid, "maths", 10) is None
    # fallback path still yields a classic set
    picks = engine.pick_daily_set(uid, "maths", 10, n=5)
    assert 1 <= len(picks) <= 5
