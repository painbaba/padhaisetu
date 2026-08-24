"""M10 mock board exam: a full paper under exam rules — no hints, no remediation,
no per-answer feedback; SKIP scores zero; bilingual scorecard at the end plus a
handoff into the existing practice flow targeting this mock's weakest skills."""
import json

from .. import db, engine, graph
from . import t, render_question, normalize_answer, stamp_sent

SKIP_WORDS = {"skip", "छोड़ें", "छोड़े", "छोडो", "छोड़ दें", "chhod do", "chhodo"}


def _infer_subject(uid: int) -> str:
    row = db.query_one(
        """SELECT q.subject FROM attempts a JOIN questions q ON q.id=a.question_id
           WHERE a.user_id=? GROUP BY q.subject ORDER BY COUNT(*) DESC LIMIT 1""", (uid,))
    return row["subject"] if row else "maths"


def current_question(ctx: dict):
    idx = int(ctx.get("idx", 0))
    queue = ctx.get("queue", [])
    if idx >= len(queue):
        return None
    return db.query_one("SELECT * FROM questions WHERE id=?", (queue[idx]["qid"],))


def start(user_row, ctx: dict):
    uid = user_row["id"]
    lang = user_row["lang"]
    subject = ctx.get("subject") or _infer_subject(uid)
    picks, board = engine.pick_mock_set(uid, subject, user_row["grade"])
    if not picks:
        return ([t(lang, "unknown"), t(lang, "menu")],
                "menu", {"greeted": True, "subject": subject})
    max_marks = sum(int(p["question"]["marks"] or 1) for p in picks)
    mctx = {
        "greeted": True,
        "subject": subject,
        "grade": user_row["grade"],
        "mode": "mock",
        "board": board,
        "queue": [{"qid": p["question"]["id"], "skill": p["skill_id"]} for p in picks],
        "idx": 0,
        "earned": 0,
        "max_marks": max_marks,
        "records": [],
        "started_at": db.iso(),
    }
    key = "mock_intro" if board else "mock_intro_plain"
    intro = t(lang, key, total=len(picks), marks=max_marks)
    q0 = db.query_one("SELECT * FROM questions WHERE id=?", (mctx["queue"][0]["qid"],))
    return [intro, render_question(q0, 1, len(picks), lang)], "mock", stamp_sent(mctx)


def handle(user_row, ctx: dict, intent: str, text: str):
    uid = user_row["id"]
    lang = user_row["lang"]

    if (text or "").strip().lower() in SKIP_WORDS:
        q = current_question(ctx)
        if q is not None:
            engine.record_attempt(uid, q, False, _elapsed_ms(ctx), "mock")
            _record(ctx, q, earned=0, skipped=True)
        return _advance(user_row, ctx)

    ans = normalize_answer(text)
    if ans is None:
        prompt = current_prompt(ctx, lang)
        return ([t(lang, "mock_choose_or_skip")] + ([prompt] if prompt else [])), \
            "mock", stamp_sent(ctx)

    q = current_question(ctx)
    if q is None:
        return [t(lang, "menu")], "menu", {"greeted": True, "subject": ctx.get("subject", "")}

    marks = int(q["marks"] or 1)
    correct = ans == int(q["correct_idx"])
    earned = marks if correct else 0
    engine.record_attempt(uid, q, correct, _elapsed_ms(ctx), "mock")
    _record(ctx, q, earned=earned, skipped=False)
    ctx["earned"] = int(ctx.get("earned", 0)) + earned
    # Exam rule: no correctness feedback mid-paper — straight to the next question.
    return _advance(user_row, ctx)


def current_prompt(ctx: dict, lang: str) -> str | None:
    q = current_question(ctx)
    if q is None:
        return None
    return render_question(q, int(ctx.get("idx", 0)) + 1, len(ctx.get("queue", [])), lang)


def _record(ctx: dict, q, earned: int, skipped: bool) -> None:
    ctx.setdefault("records", []).append({
        "qid": q["id"],
        "skill_id": q["skill_id"],
        "marks": int(q["marks"] or 1),
        "earned": earned,
        "skipped": skipped,
    })


def _advance(user_row, ctx: dict):
    uid = user_row["id"]
    lang = user_row["lang"]
    ctx["idx"] = int(ctx.get("idx", 0)) + 1
    total = len(ctx.get("queue", []))

    if ctx["idx"] >= total:
        scorecard = _finish(uid, ctx, lang)
        newctx = {"greeted": True, "subject": ctx.get("subject", ""),
                  "mock_focus": engine.weak_skills_from_records(ctx.get("records", []))}
        return scorecard, "menu", newctx

    prompt = current_prompt(ctx, lang)
    return ([prompt] if prompt else []), "mock", stamp_sent(ctx)


def _finish(uid: int, ctx: dict, lang: str) -> list[str]:
    records = ctx.get("records", [])
    got, mx = int(ctx.get("earned", 0)), int(ctx.get("max_marks", 0))
    pct = round(100.0 * got / mx, 1) if mx else 0.0
    db.execute(
        """INSERT INTO mock_attempts(user_id, subject, grade, started_at, finished_at,
           total_marks, earned_marks, pct, detail_json) VALUES(?,?,?,?,?,?,?,?,?)""",
        (uid, ctx.get("subject", ""), int(ctx.get("grade") or 0), ctx.get("started_at"),
         db.iso(), mx, got, pct, json.dumps(records, ensure_ascii=False)),
    )
    engine.apply_streak(uid)

    lines = [t(lang, "mock_score_head")]
    for sec in engine.mock_sections(records):
        if sec["max"] <= 0:
            continue  # section not present in this paper (e.g. plain fallback sets)
        lines.append(t(lang, "mock_section_line",
                       name=t(lang, f"mock_sec_{sec['name']}"),
                       got=sec["got"], mx=sec["max"]))
    lines.append(t(lang, "mock_total_line", got=got, mx=mx, pct=pct))
    weak = engine.weak_skills_from_records(records)
    if weak:
        lines.append(t(lang, "mock_weak_head"))
        for sid in weak:
            lines.append(t(lang, "mock_weak_line", name=graph.skill_name(sid, lang)))
    else:
        lines.append(t(lang, "mock_weak_none"))
    lines.append(t(lang, "mock_handoff"))
    return lines


def _elapsed_ms(ctx: dict) -> int:
    import time as _t
    ts = ctx.get("_sent_ts")
    if not ts:
        return 15000
    return max(500, min(int((_t.time() - ts) * 1000), 600000))
