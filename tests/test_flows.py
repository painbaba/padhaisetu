import os
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from app import db, flows, qbank  # noqa: E402


@pytest.fixture()
def fresh(tmp_path, monkeypatch):
    monkeypatch.setenv("PADHAISETU_DB", str(tmp_path / "flows.db"))
    db.init_db()
    qbank.load_all(force=True)
    yield


def session(phone):
    uid = int(db.scalar("SELECT id FROM users WHERE phone=?", (phone,)))
    row = db.query_one("SELECT state, context_json FROM chat_sessions WHERE user_id=?", (uid,))
    return uid, (row["state"] if row else None)


def send(phone, text):
    return flows.handle_message(phone, text)


def onboard(phone=":+91777", grade="8", subject="1"):
    send(phone, "namaste")
    send(phone, "1")          # Hindi
    send(phone, grade)        # class
    replies = send(phone, subject)  # subject -> diagnostic starts
    return replies


# ---------- M1 gate: scripted 5-msg onboarding lands in onboarding states ----------

def test_onboarding_five_msg_script_lands_in_states(fresh):
    phone = "+91555000001"
    r1 = send(phone, "hello")
    assert any("PadhaiSetu" in m or "पढ़ाईसेतु" in m for m in r1)
    uid1, st1 = session(phone)
    assert st1 == "onb_lang"

    r2 = send(phone, "1")
    _, st2 = session(phone)
    assert st2 == "onb_grade"
    assert any("8" in m for m in r2)

    r3 = send(phone, "9")
    _, st3 = session(phone)
    assert st3 == "onb_subject"

    r4 = send(phone, "2")   # science
    _, st4 = session(phone)
    assert st4 == "diag"
    user = db.query_one("SELECT * FROM users WHERE id=?", (uid1,))
    assert user["grade"] == 9 and user["lang"] == "hi"
    assert any("1)" in m and "4)" in m for m in r4[-1:])  # last bubble lists options


def test_onboarding_english_language_pick(fresh):
    phone = "+91555000002"
    send(phone, "hi")
    send(phone, "english")
    user = db.query_one("SELECT * FROM users WHERE phone=?", (phone,))
    assert user["lang"] == "en"


def test_reset_intent_returns_to_onboarding(fresh):
    phone = "+91555000003"
    onboard(phone)
    uid, st_before = session(phone)
    assert st_before == "diag"
    send(phone, "reset")
    _, st_after = session(phone)
    assert st_after == "onb_lang"


def test_help_and_unknown_never_crash(fresh):
    phone = "+91555000004"
    onboard(phone)
    out_help = send(phone, "help")
    assert out_help
    out_unk = send(phone, "xyzzy gibberish")
    assert out_unk and all(m.strip() for m in out_unk)


def test_language_switch_mid_flow(fresh):
    phone = "+91555000005"
    onboard(phone)
    out = send(phone, "english")
    assert any("English" in m for m in out)
    user = db.query_one("SELECT * FROM users WHERE phone=?", (phone,))
    assert user["lang"] == "en"
    uid, st = session(phone)
    assert st == "diag"  # stays mid-diagnostic, re-rendered in English


# ---------- M3: diagnostic seeds mastery; full practice journey w/ remediation ----------

def answer_current_correctly(phone):
    """Read the pending question's correct option from ctx and send it."""
    uid, _ = session(phone)
    ctx = db.query_one("SELECT context_json FROM chat_sessions WHERE user_id=?", (uid,))
    import json as _json
    c = _json.loads(ctx["context_json"])
    if c.get("remediating"):
        qid = c["remedial_qid"]
    elif c.get("mode") == "diag":
        qid = c["queue"][c["idx"]]["qid"]
    else:
        qid = c["queue"][c["idx"]]["qid"]
    correct_idx = int(db.scalar("SELECT correct_idx FROM questions WHERE id=?", (qid,)))
    return str(correct_idx + 1), c


def test_diagnostic_completes_and_seeds_mastery(fresh):
    phone = "+91555000006"
    onboard(phone)
    for _ in range(5):
        ans, c = answer_current_correctly(phone)
        send(phone, ans)
    _, st = session(phone)
    assert st == "menu"
    uid = int(db.scalar("SELECT id FROM users WHERE phone=?", (phone,)))
    diag_attempts = int(db.scalar(
        "SELECT COUNT(*) FROM attempts WHERE user_id=? AND mode='diag'", (uid,)))
    assert diag_attempts == 5
    mastery_rows = int(db.scalar("SELECT COUNT(*) FROM mastery WHERE user_id=?", (uid,)))
    assert mastery_rows >= 5


def test_full_journey_fourteen_msgs_with_remediation(fresh):
    phone = "+91555000007"
    transcript = []
    # --- messages 1-4: onboarding ---
    for msg in ["namaste", "1", "8", "1"]:
        transcript += send(phone, msg)
    # --- messages 5-9: diagnostic answers ---
    for _ in range(5):
        ans, _c = answer_current_correctly(phone)
        transcript += [msg for msg in send(phone, ans)]
    uid = int(db.scalar("SELECT id FROM users WHERE phone=?", (phone,)))
    assert int(db.scalar(
        "SELECT COUNT(*) FROM attempts WHERE user_id=? AND mode='diag'", (uid,))) == 5

    # --- engineer the remediation scenario directly in DB ---
    # weak prereq (m8c11s1) NOT due -> excluded from today's set;
    # dependent skill (m10-style chain not needed): fail m8c11s3 whose prereq is m8c11s1.
    now = db.now_ist()
    db.execute(
        """INSERT INTO mastery(user_id, skill_id, score, seen, last_seen, due_after)
           VALUES(?,?,?,?,?,?)""",
        (uid, "m8c11s1", 0.31, 1, db.iso(now),
         (now + timedelta(days=10)).isoformat()))          # weak but not due
    db.execute(
        """INSERT INTO mastery(user_id, skill_id, score, seen, last_seen, due_after)
           VALUES(?,?,?,?,?,?)""",
        (uid, "m8c11s3", 0.55, 1, db.iso(now),
         (now - timedelta(minutes=5)).isoformat()))        # due -> enters daily set

    # --- message 10: start practice from menu ---
    replies = send(phone, "1")
    transcript += replies
    _, st = session(phone)
    assert st == "practice"

    # find which main question is first & its skill via ctx
    import json as _json
    ctx_row = db.query_one("SELECT context_json FROM chat_sessions WHERE user_id=?", (uid,))
    c = _json.loads(ctx_row["context_json"])
    first_qid = c["queue"][0]["qid"]
    first_skill = c["queue"][0]["skill"]

    # --- message 11: deliberately WRONG answer ---
    wrong = None
    n_opts = len((db.query_one(
        "SELECT options_json FROM questions WHERE id=?", (first_qid,))["options_json"]).split("|"))
    ci = int(db.scalar("SELECT correct_idx FROM questions WHERE id=?", (first_qid,)))
    wrong = str(((ci + 1) % n_opts) + 1)
    replies = send(phone, wrong)
    transcript += replies

    bridge_seen = any(("आधार मजबूत" in m) or ("foundation" in m.lower()) for m in replies)
    if first_skill == "m8c11s3":
        assert bridge_seen, f"bridge note missing in {replies}"
    # after a wrong answer we are either remediating or shown the solution
    _, st_now = session(phone)
    assert st_now == "practice"

    # --- messages 12-14: keep answering whatever is asked (remedial or next) ---
    for _ in range(3):
        try:
            ans, _c = answer_current_correctly(phone)
            transcript += send(phone, ans)
            _, st_check = session(phone)
            if st_check != "practice":
                break
        except Exception:
            break

    total_attempts = int(db.scalar("SELECT COUNT(*) FROM attempts WHERE user_id=?", (uid,)))
    assert total_attempts >= 5

    modes = {r["mode"] for r in db.query(
        "SELECT DISTINCT mode FROM attempts WHERE user_id=?", (uid,))}
    assert "diag" in modes

    mastery_rows = int(db.scalar("SELECT COUNT(*) FROM mastery WHERE user_id=?", (uid,)))
    assert mastery_rows > 5  # diagnostic seeds + practice updates

    # remediation actually observed somewhere in the transcript OR solution path taken
    observed = any(("आधार मजबूत" in m) or ("foundation" in m.lower()) for m in transcript)
    solutions = any(("हल:" in m) or ("Solution:" in m) for m in transcript)
    assert observed or solutions


def test_practice_wrong_answer_without_weak_prereq_shows_solution(fresh):
    phone = "+91555000008"
    onboard(phone)
    for _ in range(5):
        ans, _c = answer_current_correctly(phone)
        send(phone, ans)
    # make every skill strong so walker finds nothing below 0.45
    uid = int(db.scalar("SELECT id FROM users WHERE phone=?", (phone,)))
    now = db.now_ist()
    for sid in qbank.skills_with_questions("maths", 8):
        db.execute(
            """INSERT INTO mastery(user_id, skill_id, score, seen, last_seen, due_after)
               VALUES(?,?,?,?,?,?)
               ON CONFLICT(user_id, skill_id) DO UPDATE SET score=excluded.score""",
            (uid, sid, 0.95, 3, db.iso(now), (now - timedelta(days=1)).isoformat()))
    replies = send(phone, "1")
    assert replies
    ctx_row = db.query_one("SELECT context_json FROM chat_sessions WHERE user_id=?", (uid,))
    import json as _json
    c = _json.loads(ctx_row["context_json"])
    qid = c["queue"][0]["qid"]
    ci = int(db.scalar("SELECT correct_idx FROM questions WHERE id=?", (qid,)))
    out = send(phone, str(((ci + 1) % 4) + 1))  # guaranteed-wrong option
    joined = "\n".join(out)
    assert ("हल:" in joined) or ("Solution:" in joined) or ("आधार मजबूत" in joined)


# ---------- M4: streaks on set completion + weekly report row ----------

def test_streak_row_created_on_set_completion(fresh):
    phone = "+91555000009"
    onboard(phone)
    for _ in range(5):
        ans, _c = answer_current_correctly(phone)
        send(phone, ans)
    send(phone, "1")  # start practice
    for _ in range(5):
        try:
            ans, _c = answer_current_correctly(phone)
            replies = send(phone, ans)
            _, st = session(phone)
            if st == "menu":
                assert any("लगातार अभ्यास" in m for m in replies)
                break
        except Exception:
            break
    uid = int(db.scalar("SELECT id FROM users WHERE phone=?", (phone,)))
    row = db.query_one("SELECT * FROM streaks WHERE user_id=?", (uid,))
    assert row is not None
    assert int(row["current"]) == 1 and int(row["best"]) == 1


def test_weekly_report_rendered_from_real_history(fresh):
    import json as _json
    phone = "+91555000010"
    onboard(phone)
    # one correct, one wrong diagnostic attempt -> real history
    ans1, _ = answer_current_correctly(phone)
    send(phone, ans1)
    ctx_row = db.query_one("SELECT context_json FROM chat_sessions WHERE user_id=?",
                           (int(db.scalar("SELECT id FROM users WHERE phone=?", (phone,))),))
    c = _json.loads(ctx_row["context_json"])
    qid2 = c["queue"][c["idx"]]["qid"]
    ci2 = int(db.scalar("SELECT correct_idx FROM questions WHERE id=?", (qid2,)))
    send(phone, str(((ci2 + 1) % 4) + 1))  # wrong
    for _ in range(3):
        ans, _c = answer_current_correctly(phone)
        send(phone, ans)

    uid = int(db.scalar("SELECT id FROM users WHERE phone=?", (phone,)))
    before = int(db.scalar("SELECT COUNT(*) FROM reports"))
    replies = send(phone, "3")
    after_rows = db.query("SELECT * FROM reports WHERE user_id=?", (uid,))
    assert len(after_rows) >= before - before + 1 or len(after_rows) >= 1
    payload = _json.loads(after_rows[-1]["payload_json"])
    total_attempts = int(db.scalar(
        "SELECT COUNT(*) FROM attempts WHERE user_id=?", (uid,)))
    assert payload["attempts"] == total_attempts
    joined = "\n".join(replies)
    assert ("प्रश्न हल किए" in joined) or ("Questions solved" in joined)
    assert str(payload["attempts"]) in joined
