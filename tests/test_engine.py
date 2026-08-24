import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from app import db, engine, graph, qbank  # noqa: E402


@pytest.fixture()
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setenv("PADHAISETU_DB", str(tmp_path / "engine.db"))
    db.init_db()
    qbank.load_all(force=True)
    yield


@pytest.fixture()
def student(tmp_db):
    db.execute("INSERT INTO users(phone, lang, grade, created_at) VALUES(?,?,?,?)",
               ("+911000000001", "hi", 8, db.iso()))
    return int(db.scalar("SELECT id FROM users WHERE phone='+911000000001'"))


# ---------- mastery math (pure functions) ----------

def test_new_score_slow_correct():
    assert engine.new_score(0.5, True, 25000) == pytest.approx(0.625)


def test_new_score_fast_correct_bonus():
    assert engine.new_score(0.5, True, 8000) == pytest.approx(
        0.75 * 0.5 + 0.25 * engine.FAST_BONUS)


def test_new_score_wrong_ignores_speed():
    assert engine.new_score(0.5, False, 1000) == pytest.approx(0.375)
    assert engine.new_score(0.5, False, 90000) == pytest.approx(0.375)


def test_new_score_clamps_to_one():
    assert engine.new_score(0.98, True, 5000) == 1.0
    assert engine.new_score(0.0, False, 5000) == 0.0


def test_due_delta_bands():
    assert engine.due_delta(0.30) == timedelta(days=1)
    assert engine.due_delta(engine.WEAK - 1e-9) == timedelta(days=1)
    assert engine.due_delta(0.45) == timedelta(days=3)
    assert engine.due_delta(0.69) == timedelta(days=3)
    assert engine.due_delta(0.70) == timedelta(days=7)
    assert engine.due_delta(1.0) == timedelta(days=7)


# ---------- record_attempt ----------

def test_record_attempt_updates_mastery_and_attempt_row(student):
    q = qbank.questions_for_skill("m8c1s1")[0]
    res = engine.record_attempt(student, q, True, 5000, "practice")
    assert res["seen"] == 1
    row = db.query_one("SELECT * FROM mastery WHERE user_id=? AND skill_id=?",
                       (student, "m8c1s1"))
    assert float(row["score"]) == pytest.approx(res["score"])
    att = db.query_one("SELECT * FROM attempts WHERE id=?", (res["attempt_id"],))
    assert int(att["correct"]) == 1 and att["mode"] == "practice"


def test_record_attempt_ewma_chains_correctly(student):
    q = qbank.questions_for_skill("m8c2s1")[0]
    s = engine.DEFAULT_SCORE
    for correct, ms in [(True, 30000), (True, 30000), (False, 30000)]:
        s = engine.new_score(s, correct, ms)
        res = engine.record_attempt(student, q, correct, ms, "practice")
        assert res["score"] == pytest.approx(s)
    assert abs(s - 0.5390625) < 1e-9


def test_due_after_written_by_band(student):
    q = qbank.questions_for_skill("m8c7s1")[0]
    r1 = engine.record_attempt(student, q, False, 60000, "practice")
    now = db.now_ist()
    assert datetime.fromisoformat(r1["due_after"]) <= now + timedelta(days=1, minutes=5)
    r2 = engine.record_attempt(student, q, True, 60000, "practice")
    assert r2["due_after"] > r1["due_after"]


# ---------- walker ----------

def test_walker_finds_weak_prereq_depth_first():
    # m10c3s1 -> m8c11s3 -> m8c11s1 chain exists in the real graph
    mastery = {"m8c11s3": 0.60, "m8c11s1": 0.30}
    target = graph.walker("m10c3s1", lambda s: mastery.get(s, 0.8))
    assert target == "m8c11s1"


def test_walker_skips_strong_prereqs():
    mastery = {"m8c11s3": 0.60, "m8c11s1": 0.80}
    assert graph.walker("m10c3s1", lambda s: mastery.get(s, 0.9)) is None


def test_walker_default_mastery_not_below_threshold():
    # unseen prereqs default to 0.5 which is >= 0.45
    assert graph.walker("m8c2s2", lambda s: 0.5) is None


# ---------- ranking / daily set / remediation ----------

def _seed_mastery(uid, rows):
    for sid, score, due_days in rows:
        due = (db.now_ist() + timedelta(days=due_days)).isoformat() if due_days > 0 \
            else (db.now_ist() - timedelta(days=-due_days)).isoformat()
        db.execute(
            """INSERT INTO mastery(user_id, skill_id, score, seen, last_seen, due_after)
               VALUES(?,?,?,?,?,?)
               ON CONFLICT(user_id, skill_id) DO UPDATE SET score=excluded.score""",
            (uid, sid, score, 2, db.iso(), due))


def test_ranked_skills_due_weakest_first(student):
    _seed_mastery(student, [
        ("m8c1s1", 0.31, -1),   # weak & due -> must come first
        ("m8c2s1", 0.90, -1),   # strong & due -> after unseen defaults
        ("m8c5s1", 0.55, 4),    # not due yet -> pushed to the tail
    ])
    ranked = engine.ranked_skills(student, "maths", 8)
    ids = [r["skill_id"] for r in ranked]
    assert ids[0] == "m8c1s1"
    assert "m8c5s1" not in ids[:5]
    assert ids.index("m8c2s1") > ids.index("m8c10s1")  # strong-due loses to fresh skills


def test_pick_daily_set_size_and_question_presence(student):
    picks = engine.pick_daily_set(student, "maths", 8, n=5)
    assert 1 <= len(picks) <= 5
    for p in picks:
        assert p["question"]["skill_id"] == p["skill_id"]


def test_pick_daily_set_excludes_skills_without_questions(student):
    picks = engine.pick_daily_set(student, "maths", 8, n=99)
    have_q = qbank.skills_with_questions("maths", 8)
    assert all(p["skill_id"] in have_q for p in picks)


def test_remediation_target_serves_easier_question_at_weak_prereq(student):
    # chain: m10c3s1 (has questions) -> m8c11s3 (default 0.5, skipped) -> m8c11s1
    _seed_mastery(student, [("m8c11s1", 0.31, 30)])
    target = engine.remediation_target(student, "m10c3s1")
    assert target is not None
    assert target["skill_id"] == "m8c11s1"
    main_q = engine.pick_question_for_skill("m10c3s1")
    assert main_q is not None
    assert target["question"]["difficulty"] <= max(1, main_q["difficulty"] - 1) + 1


def test_remediation_target_none_when_prereqs_ok(student):
    target = engine.remediation_target(student, "m8c2s2")
    assert target is None


# ---------- streaks ----------

def test_streak_consecutive_days_increment(student):
    d0 = date(2026, 8, 20)
    c1, b1 = engine.apply_streak(student, d0)
    c2, b2 = engine.apply_streak(student, d0 + timedelta(days=1))
    c3, b3 = engine.apply_streak(student, d0 + timedelta(days=2))
    assert (c1, c2, c3) == (1, 2, 3)
    assert b3 == 3


def test_streak_gap_resets(student):
    d0 = date(2026, 8, 10)
    engine.apply_streak(student, d0)
    engine.apply_streak(student, d0 + timedelta(days=1))
    cur, best = engine.apply_streak(student, d0 + timedelta(days=5))
    assert cur == 1 and best == 2


def test_streak_same_day_no_double_count(student):
    d0 = date(2026, 8, 10)
    engine.apply_streak(student, d0)
    cur, best = engine.apply_streak(student, d0)
    assert cur == 1 and best == 1


# ---------- weekly report payload ----------

def test_weekly_payload_matches_manual_stats(student):
    uid = student
    today = date(2026, 8, 24)  # Monday
    monday = today

    def iso_for(d):
        return db.iso(datetime.combine(d, datetime.min.time()).replace(tzinfo=db.ist_tz()))

    qs = {sid: qbank.questions_for_skill(sid)[0]
          for sid in ("m8c1s1", "m8c2s1")}
    plan = [
        (qs["m8c1s1"], True, monday),          # this week
        (qs["m8c1s1"], False, monday),         # this week
        (qs["m8c2s1"], True, monday),          # this week
        (qs["m8c2s1"], False, monday - timedelta(days=2)),  # last week: excluded
    ]
    for q, ok, day in plan:
        db.execute(
            "INSERT INTO attempts(user_id, question_id, correct, time_ms, mode, skill_id,"
            " created_at) VALUES(?,?,?,?,?,?,?)",
            (uid, q["id"], 1 if ok else 0, 20000, "practice", q["skill_id"], iso_for(day)))

    payload = engine.weekly_payload(uid, today)
    assert payload["week_of"] == monday.isoformat()
    assert payload["attempts"] == 3
    assert payload["correct"] == 2
    assert payload["accuracy"] == round(100 * 2 / 3, 1)
    assert set(payload["focus_skills"]) == {"m8c1s1", "m8c2s1"}


def test_store_report_persists_row(student):
    payload = engine.weekly_payload(student)
    rid = engine.store_report(student, payload)
    row = db.query_one("SELECT * FROM reports WHERE id=?", (rid,))
    assert row is not None
    assert row["week_of"] == payload["week_of"]
    assert '"attempts"' in row["payload_json"]


def test_diagnostic_results_due_immediately(student):
    q = qbank.questions_for_skill("m8c1s1")[0]
    res = engine.record_attempt(student, q, False, 60000, "diag")
    assert res["due_after"] <= db.iso()          # practicable today
    res2 = engine.record_attempt(student, q, False, 60000, "practice")
    assert res2["due_after"] > db.iso()          # practice keeps SR spacing
