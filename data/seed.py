"""Demo seed: 3 students with realistic attempt history so the dashboard looks alive.
Run AFTER first server start (or standalone - it inits + loads banks itself):
    python data/seed.py
Deterministic: fixed rng seed, so judges see the same story every reset.
"""
import json
import random
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import db, engine, graph, qbank  # noqa: E402

STUDENTS = [
    {"phone": "+919000000101", "name": "आरती", "lang": "hi", "grade": 8,
     "subject": "maths", "days": 6, "per_day": 5, "accuracy": 0.55,
     "streak_days": 4},
    {"phone": "+919000000102", "name": "राहुल", "lang": "hi", "grade": 10,
     "subject": "maths", "days": 5, "per_day": 4, "accuracy": 0.70,
     "streak_days": 1},
    {"phone": "+919000000103", "name": "Sneha", "lang": "en", "grade": 9,
     "subject": "science", "days": 4, "per_day": 5, "accuracy": 0.65,
     "streak_days": 2},
]


def seed_mock(uid: int, cfg: dict, rng: random.Random, day) -> None:
    """One completed mock-paper row built from real bank questions so the
    dashboard's Mocks-taken counter and latest-mock score have real backing."""
    picks, board = engine.pick_mock_set(uid, cfg["subject"], cfg["grade"])
    if not picks:
        return
    records, earned, total = [], 0, 0
    for p in picks:
        q = p["question"]
        marks = int(q["marks"] or 1)
        total += marks
        e = marks if rng.random() < cfg["accuracy"] else 0
        earned += e
        records.append({"qid": q["id"], "skill_id": p["skill_id"], "marks": marks,
                        "earned": e, "skipped": False})
    started = db.now_ist().replace(
        year=day.year, month=day.month, day=day.day, hour=18, minute=10)
    db.execute(
        """INSERT INTO mock_attempts(user_id, subject, grade, started_at, finished_at,
           total_marks, earned_marks, pct, detail_json) VALUES(?,?,?,?,?,?,?,?,?)""",
        (uid, cfg["subject"], cfg["grade"], db.iso(started), db.iso(started),
         total, earned, round(100.0 * earned / total, 1) if total else 0.0,
         json.dumps(records, ensure_ascii=False)))
    print(f"  + mock paper {'board' if board else 'plain'} "
          f"({earned}/{total} marks)")


def seed_student(cfg: dict, rng: random.Random) -> None:
    existing = db.query_one("SELECT id FROM users WHERE phone=?", (cfg["phone"],))
    if existing:
        print(f"skip {cfg['phone']} (already seeded)")
        return
    db.execute(
        "INSERT INTO users(phone, lang, name, grade, created_at) VALUES(?,?,?,?,?)",
        (cfg["phone"], cfg["lang"], cfg["name"], cfg["grade"], db.iso()))
    uid = int(db.scalar("SELECT id FROM users WHERE phone=?", (cfg["phone"],)))

    skills = sorted(qbank.skills_with_questions(cfg["subject"], cfg["grade"]))
    today = db.now_ist().date()

    for day_offset in range(cfg["days"], 0, -1):
        day = today - timedelta(days=day_offset)
        if day_offset > cfg["streak_days"]:
            continue  # only recent days keep the streak alive
        day_dt = db.now_ist().replace(
            year=day.year, month=day.month, day=day.day, hour=17, minute=30)
        picks = rng.sample(skills, min(cfg["per_day"], len(skills)))
        for sid in picks:
            q = engine.pick_question_for_skill(sid, pref_diff=2)
            if q is None:
                continue
            correct = rng.random() < cfg["accuracy"]
            ms = rng.randint(6000, 40000)
            res = engine.record_attempt(uid, q, correct, ms, "practice",
                                        now=day_dt)

    cur = min(cfg["streak_days"], cfg["days"])
    best = max(cur, rng.randint(cur, cur + 2))
    last_day = (today - timedelta(days=1)).isoformat()
    db.execute(
        """INSERT INTO streaks(user_id, current, best, last_day) VALUES(?,?,?,?)
           ON CONFLICT(user_id) DO UPDATE SET current=excluded.current,
             best=excluded.best, last_day=excluded.last_day""",
        (uid, cur, best, last_day))

    seed_mock(uid, cfg, rng, today - timedelta(days=1))

    payload = engine.weekly_payload(uid)
    engine.store_report(uid, payload)
    n_att = db.scalar("SELECT COUNT(*) FROM attempts WHERE user_id=?", (uid,))
    print(f"seeded {cfg['phone']} {cfg['name']}: {n_att} attempts")


def main() -> None:
    db.init_db()
    inserted = qbank.ensure_loaded()
    if inserted:
        print(f"loaded question banks ({inserted} new)")
    rng = random.Random(7)  # deterministic demo story
    for cfg in STUDENTS:
        seed_student(cfg, rng)
    users = db.scalar("SELECT COUNT(*) FROM users")
    attempts = db.scalar("SELECT COUNT(*) FROM attempts")
    print(f"done. users={users} attempts={attempts}")


if __name__ == "__main__":
    main()
