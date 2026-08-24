"""Adaptive engine: EWMA mastery updates, spaced repetition, weakness ranking,
next-question picking, prerequisite remediation, streaks. Deterministic & unit-testable."""
import json
from datetime import date, timedelta

from . import db, graph, qbank

FAST_MS = 20000
FAST_BONUS = 1.15
WEAK = 0.45
OK = 0.7
DEFAULT_SCORE = 0.5


# ---------- mastery math (pure) ----------

def speed_bonus(time_ms: int) -> float:
    return FAST_BONUS if time_ms is not None and time_ms < FAST_MS else 1.0


def new_score(old: float, correct: bool, time_ms: int) -> float:
    """score <- clamp(0.75*score + 0.25*(correct?1:0)*speed_bonus)."""
    gained = 0.25 * speed_bonus(time_ms) if correct else 0.0
    v = 0.75 * float(old) + gained
    return min(1.0, max(0.0, v))


def due_delta(score: float) -> timedelta:
    """Spaced repetition bands: <0.45 -> 1 day, <0.7 -> 3 days, else 7 days."""
    if score < WEAK:
        return timedelta(days=1)
    if score < OK:
        return timedelta(days=3)
    return timedelta(days=7)


def due_after_from(score: float, now) -> str:
    return db.iso(now + due_delta(score))


# ---------- mastery state ----------

def get_mastery(user_id: int) -> dict:
    """skill_id -> row dict for one user."""
    rows = db.query("SELECT * FROM mastery WHERE user_id=?", (user_id,))
    return {r["skill_id"]: dict(r) for r in rows}


def score_of(mastery_map: dict, skill_id: str) -> float:
    row = mastery_map.get(skill_id)
    return float(row["score"]) if row else DEFAULT_SCORE


def record_attempt(user_id: int, question, correct: bool, time_ms: int, mode: str, now=None) -> dict:
    """Insert attempt + EWMA-update mastery + set due_after band."""
    now = now or db.now_ist()
    sid = question["skill_id"]
    prev_row = db.query_one(
        "SELECT score, seen FROM mastery WHERE user_id=? AND skill_id=?", (user_id, sid)
    )
    prev_score = float(prev_row["score"]) if prev_row else DEFAULT_SCORE
    ns = new_score(prev_score, correct, time_ms)
    seen = (int(prev_row["seen"]) if prev_row else 0) + 1
    aid = db.execute(
        "INSERT INTO attempts(user_id, question_id, correct, time_ms, mode, skill_id, created_at)"
        " VALUES(?,?,?,?,?,?,?)",
        (user_id, question["id"], 1 if correct else 0, int(time_ms), mode, sid, db.iso(now)),
    )
    db.execute(
        """INSERT INTO mastery(user_id, skill_id, score, seen, last_seen, due_after)
           VALUES(?,?,?,?,?,?)
           ON CONFLICT(user_id, skill_id)
           DO UPDATE SET score=excluded.score, seen=excluded.seen,
                         last_seen=excluded.last_seen, due_after=excluded.due_after""",
        (user_id, sid, ns, seen, db.iso(now), due_after_from(ns, now)),
    )
    return {"attempt_id": aid, "score": ns, "due_after": due_after_from(ns, now), "seen": seen}


# ---------- ranking / selection ----------

def ranked_skills(user_id: int, subject: str, grade: int, now=None) -> list[dict]:
    """Weakest-first candidate skills that have questions.
    Sort key ascending on (not-due-first? no): due skills first, then lowest score*weight."""
    now = now or db.now_ist()
    have_q = qbank.skills_with_questions(subject, grade)
    mmap = get_mastery(user_id)
    entries = []
    for sid in sorted(have_q):
        meta = graph.skill(sid)
        if not meta:
            continue
        row = mmap.get(sid)
        score = float(row["score"]) if row else DEFAULT_SCORE
        due = True
        if row and row["due_after"]:
            due = row["due_after"] <= db.iso(now)
        entries.append({
            "skill_id": sid,
            "score": score,
            "weight": meta["weight"],
            "weakness": score * meta["weight"],
            "seen": int(row["seen"]) if row else 0,
            "due": due,
        })
    entries.sort(key=lambda e: (0 if e["due"] else 1, e["weakness"], e["seen"], e["skill_id"]))
    return entries


def preferred_difficulty(score: float) -> int:
    if score < WEAK:
        return 1
    if score < OK:
        return 2
    return 3


def pick_question_for_skill(skill_id: str, pref_diff: int = 2):
    rows = qbank.questions_for_skill(skill_id)
    if not rows:
        return None
    best = min(rows, key=lambda r: (abs(r["difficulty"] - pref_diff), r["difficulty"], r["id"]))
    return best


def pick_daily_set(user_id: int, subject: str, grade: int, n: int = 5, now=None) -> list[dict]:
    """n questions targeting weakest/due skills. Returns [{question, skill_id, score}]."""
    picks = []
    used_skills: set[str] = set()
    for entry in ranked_skills(user_id, subject, grade, now):
        if len(picks) >= n:
            break
        sid = entry["skill_id"]
        if sid in used_skills:
            continue
        q = pick_question_for_skill(sid, preferred_difficulty(entry["score"]))
        if q is None:
            continue
        used_skills.add(sid)
        picks.append({"question": q, "skill_id": sid, "score": entry["score"]})
    return picks


# ---------- remediation ----------

def remediation_target(user_id: int, skill_id: str, exclude: set[str] | None = None) -> dict | None:
    """Walk prereqs; first with mastery<0.45 gets an easier question served.
    Returns {'question':row,'skill_id':...} or None."""
    mmap = get_mastery(user_id)
    target_sid = graph.walker(skill_id, lambda s: score_of(mmap, s))
    if not target_sid or (exclude and target_sid in exclude):
        return None
    cur = graph.skill(skill_id)
    cur_diff = pick_question_for_skill(skill_id)
    pref = max(1, (cur_diff["difficulty"] if cur_diff else 2) - 1)
    q = pick_question_for_skill(target_sid, pref)
    if q is None:
        return None
    return {"question": q, "skill_id": target_sid}


# ---------- streaks ----------

def apply_streak(user_id: int, today: date | None = None) -> tuple[int, int]:
    today = today or db.now_ist().date()
    row = db.query_one("SELECT current, best, last_day FROM streaks WHERE user_id=?", (user_id,))
    if row and row["last_day"] == today.isoformat():
        cur = int(row["current"])
    elif row and row["last_day"] == (today - timedelta(days=1)).isoformat():
        cur = int(row["current"]) + 1
    else:
        cur = 1
    best = max(cur, int(row["best"]) if row else 0)
    db.execute(
        """INSERT INTO streaks(user_id, current, best, last_day) VALUES(?,?,?,?)
           ON CONFLICT(user_id) DO UPDATE SET current=excluded.current,
             best=excluded.best, last_day=excluded.last_day""",
        (user_id, cur, best, today.isoformat()),
    )
    return cur, best


def get_streak(user_id: int) -> tuple[int, int]:
    row = db.query_one("SELECT current, best FROM streaks WHERE user_id=?", (user_id,))
    return (int(row["current"]), int(row["best"])) if row else (0, 0)


# ---------- weekly report payload (numbers only; wording lives in flows) ----------

def week_bounds(today: date | None = None) -> tuple[date, date]:
    """Monday..Sunday containing today."""
    today = today or db.now_ist().date()
    monday = today - timedelta(days=today.weekday())
    return monday, monday + timedelta(days=7)


def weekly_payload(user_id: int, today: date | None = None) -> dict:
    start, end = week_bounds(today)
    rows = db.query(
        "SELECT a.correct, a.skill_id FROM attempts a JOIN users u ON u.id=a.user_id "
        "WHERE a.user_id=? AND a.created_at>=? AND a.created_at<?",
        (user_id, start.isoformat(), end.isoformat()),
    )
    total = len(rows)
    correct = sum(1 for r in rows if r["correct"])
    acc = round(100.0 * correct / total, 1) if total else 0.0
    per_skill: dict[str, list[int]] = {}
    for r in rows:
        per_skill.setdefault(r["skill_id"], []).append(r["correct"])
    weak = []
    for sid, results in per_skill.items():
        acc_s = sum(results) / len(results)
        m = get_mastery(user_id).get(sid, {})
        weak.append((acc_s, sid))
    weak.sort()
    focus = [sid for _, sid in weak[:3]]
    cur, best = get_streak(user_id)
    return {
        "week_of": start.isoformat(),
        "attempts": total,
        "correct": correct,
        "accuracy": acc,
        "focus_skills": focus,
        "focus_names_hi": [graph.skill_name(s, "hi") for s in focus],
        "focus_names_en": [graph.skill_name(s, "en") for s in focus],
        "streak_current": cur,
        "streak_best": best,
    }


def store_report(user_id: int, payload: dict, sent: bool = False) -> int:
    return db.execute(
        "INSERT INTO reports(user_id, week_of, payload_json, sent) VALUES(?,?,?,?)",
        (user_id, payload["week_of"], json.dumps(payload, ensure_ascii=False),
         1 if sent else 0),
    )
