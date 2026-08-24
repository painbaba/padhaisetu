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

# Board-pattern session shape (official MPBSE 2026 sample papers, data/pyqs/paper2026_*)
BOARD_GRADE = 10
BOARD_SHAPE = [(5, 1), (12, 2), (3, 3), (3, 4)]   # (count, marks)
OBJECTIVE_QTYPES = ("mcq", "fill", "tf")
BOARD_SKILL_CAP = 4


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
    """Insert attempt + EWMA-update mastery + set due_after band.
    Diagnostic results are due immediately: gaps found by the placement quiz must be
    practicable the same day, otherwise SR would hide them until tomorrow."""
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
    due = db.iso(now) if mode == "diag" else due_after_from(ns, now)
    db.execute(
        """INSERT INTO mastery(user_id, skill_id, score, seen, last_seen, due_after)
           VALUES(?,?,?,?,?,?)
           ON CONFLICT(user_id, skill_id)
           DO UPDATE SET score=excluded.score, seen=excluded.seen,
                         last_seen=excluded.last_seen, due_after=excluded.due_after""",
        (user_id, sid, ns, seen, db.iso(now), due),
    )
    return {"attempt_id": aid, "score": ns, "due_after": due, "seen": seen}


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


def _mastery_score(mmap: dict, skill_id: str) -> float:
    row = mmap.get(skill_id)
    return float(row["score"]) if row else DEFAULT_SCORE


def _interleave_by_skill(rows: list) -> list:
    """Round-robin across skill groups (rank order preserved between groups)
    so a session doesn't serve several same-template items back-to-back."""
    groups: dict[str, list] = {}
    for r in rows:
        groups.setdefault(r["skill_id"], []).append(r)
    out: list = []
    while any(groups.values()):
        for g in groups.values():
            if g:
                out.append(g.pop(0))
    return out


def pick_board_set(user_id: int, subject: str, grade: int, now=None) -> list[dict] | None:
    """Grade-10 MPBSE board-pattern mix: 5 objective (MCQ/fill/tf), then
    12x2-mark, 3x3-mark, 3x4-mark — weakest skills first inside each bucket,
    never both members of an OR pair. Returns None when tagged items are short
    (caller falls back to pick_daily_set)."""
    if int(grade or 0) != BOARD_GRADE:
        return None
    now = now or db.now_ist()
    ranked = ranked_skills(user_id, subject, grade, now)
    rank = {e["skill_id"]: i for i, e in enumerate(ranked)}
    mmap = get_mastery(user_id)

    def bucket(marks: int) -> list:
        if marks == 1:
            qs = ",".join("?" * len(OBJECTIVE_QTYPES))
            where = f"marks<=1 AND qtype IN ({qs})"
            params: tuple = (subject, grade, *OBJECTIVE_QTYPES)
        else:
            where = "marks=?"
            params = (subject, grade, marks)
        rows = db.query(
            f"SELECT * FROM questions WHERE subject=? AND grade=? AND active=1 AND {where}",
            params)
        return _interleave_by_skill(sorted(rows, key=lambda r: (
            rank.get(r["skill_id"], len(rank)),
            _mastery_score(mmap, r["skill_id"]),
            r["id"],
        )))

    buckets = [bucket(m) for _, m in BOARD_SHAPE]
    if any(len(rows) < need for rows, (need, _) in zip(buckets, BOARD_SHAPE)):
        return None

    used_pairs: set[str] = set()
    used_qids: set[int] = set()
    skill_ct: dict[str, int] = {}
    picks: list[dict] = []
    for rows, (need, _marks) in zip(buckets, BOARD_SHAPE):
        taken = 0
        for r in rows:
            if taken >= need:
                break
            rid, sid = r["id"], r["skill_id"]
            if rid in used_qids or skill_ct.get(sid, 0) >= BOARD_SKILL_CAP:
                continue
            opair = None
            if r["gen_params_json"]:
                try:
                    opair = json.loads(r["gen_params_json"]).get("or_pair")
                except Exception:
                    opair = None
            if opair and opair in used_pairs:
                continue
            used_qids.add(rid)
            if opair:
                used_pairs.add(opair)
            skill_ct[sid] = skill_ct.get(sid, 0) + 1
            picks.append({"question": r, "skill_id": sid,
                          "score": _mastery_score(mmap, sid)})
            taken += 1
        if taken < need:
            return None  # cap/or-pair filtering starved this bucket
    return picks


# ---------- mock exam (M10) ----------

MOCK_SIZE = 23


def pick_mock_set(user_id: int, subject: str, grade: int, now=None) -> tuple[list[dict], bool]:
    """Full board-pattern mock paper. Primary path reuses pick_board_set (MPBSE mix,
    weakest-first per bucket, OR-pair dedupe; the bank's seeded generator varies items).
    Returns (picks, is_board_pattern); falls back to a daily-set-style paper when no
    tagged board items exist for this class/subject."""
    picks = pick_board_set(user_id, subject, grade, now)
    if picks:
        return picks, True
    return pick_daily_set(user_id, subject, grade, MOCK_SIZE, now), False


def mock_sections(records: list[dict]) -> list[dict]:
    """Section scores from per-question records ({marks, earned}):
    objective (<=1), short (==2), medium (==3), long (>=4), in that order."""
    defs = [("objective", lambda m: m <= 1), ("short", lambda m: m == 2),
            ("medium", lambda m: m == 3), ("long", lambda m: m >= 4)]
    out = []
    for name, pred in defs:
        got = sum(r["earned"] for r in records if pred(int(r["marks"])))
        mx = sum(int(r["marks"]) for r in records if pred(int(r["marks"])))
        out.append({"name": name, "got": got, "max": mx})
    return out


def weak_skills_from_records(records: list[dict], k: int = 3) -> list[str]:
    """Top-k weakest skills by marks earned / marks available (only imperfect ones),
    ties broken by more-attempted first then skill_id for determinism."""
    agg: dict[str, list[int]] = {}
    for r in records:
        a = agg.setdefault(r["skill_id"], [0, 0])
        a[0] += int(r["earned"])
        a[1] += int(r["marks"])
    scored = [(g / m, sid) for sid, (g, m) in agg.items() if m > 0 and g < m]
    scored.sort(key=lambda e: (e[0], -agg[e[1]][1], e[1]))
    return [sid for _, sid in scored[:k]]


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
