"""Diagnostic: 5-question span quiz -> seeds mastery map -> weakest-topic summary."""
from .. import db, engine, graph, qbank
from . import t, render_question, normalize_answer, correct_option_text, stamp_sent

DIAG_SIZE = 5


def representative_questions(user_row, subject: str):
    """One question per major chapter (evenly spread), from skills that have questions."""
    grade = user_row["grade"]
    have_q = qbank.skills_with_questions(subject, grade)
    viable = []
    for ch in graph.chapters(subject, grade):
        sid = graph.representative_skill(ch, have_q)
        if sid:
            q = engine.pick_question_for_skill(sid, pref_diff=2)
            if q is not None:
                viable.append(q)
    if len(viable) <= DIAG_SIZE:
        return viable
    step = len(viable) / DIAG_SIZE
    return [viable[int(i * step)] for i in range(DIAG_SIZE)]


def _board_mini(board_picks: list[dict]) -> list[dict] | None:
    """5-question diagnostic slice of the full board mix:
    2 objective + 2 two-mark + 1 three-mark (objective first, ascending marks)."""
    obj = [p for p in board_picks if int(p["question"]["marks"] or 1) <= 1][:2]
    two = [p for p in board_picks if int(p["question"]["marks"] or 1) == 2][:2]
    three = [p for p in board_picks if int(p["question"]["marks"] or 1) == 3][:1]
    mini = obj + two + three
    return mini if len(mini) == DIAG_SIZE else None


def start(user_row, subject: str):
    lang = user_row["lang"]
    qs = None
    if int(user_row["grade"] or 0) == engine.BOARD_GRADE:
        board = engine.pick_board_set(user_row["id"], subject, user_row["grade"])
        if board:
            mini = _board_mini(board)
            if mini:
                qs = [{"id": p["question"]["id"], "skill_id": p["skill_id"]} for p in mini]
    if qs is None:
        qs = representative_questions(user_row, subject)
    if len(qs) < 3:
        return ([t(lang, "menu")], "menu", {"subject": subject})
    ctx = {
        "mode": "diag",
        "subject": subject,
        "queue": [{"qid": q["id"], "skill": q["skill_id"]} for q in qs],
        "idx": 0,
    }
    intro = t(lang, "diag_intro", count=len(qs),
              subject=nlu_subject_name(subject, lang), grade=user_row["grade"])
    first = db.query_one("SELECT * FROM questions WHERE id=?", (ctx["queue"][0]["qid"],))
    replies = [intro, render_question(first, 1, len(qs), lang)]
    return replies, "diag", stamp_sent(ctx)


def current_question(ctx: dict):
    idx = int(ctx.get("idx", 0))
    queue = ctx.get("queue", [])
    if idx >= len(queue):
        return None
    return db.query_one("SELECT * FROM questions WHERE id=?", (queue[idx]["qid"],))


def handle(user_row, ctx: dict, intent: str, text: str):
    uid = user_row["id"]
    lang = user_row["lang"]
    q = current_question(ctx)
    if q is None:
        return [t(lang, "menu")], "menu", {"subject": ctx.get("subject", "")}

    ans = normalize_answer(text)
    if ans is None:
        return [t(lang, "choose_answer")], "diag", stamp_sent(ctx)

    correct = ans == int(q["correct_idx"])
    result = engine.record_attempt(uid, q, correct, _elapsed_ms(ctx), "diag")
    feedback = t(lang, "diag_correct") if correct else \
        t(lang, "diag_wrong", ans=correct_option_text(q, lang))

    ctx["idx"] = int(ctx.get("idx", 0)) + 1
    total = len(ctx.get("queue", []))
    if ctx["idx"] >= total:
        summary = _summary(uid, ctx.get("subject", ""), lang)
        newctx = {"greeted": True, "subject": ctx.get("subject", ""), "just_diagnosed": True}
        return [feedback] + summary, "menu", newctx

    nxt = current_question(ctx)
    return [feedback, render_question(nxt, int(ctx["idx"]) + 1, total, lang)], \
        "diag", stamp_sent(ctx)


def _summary(uid: int, subject: str, lang: str) -> list[str]:
    mmap = engine.get_mastery(uid)
    lines = [t(lang, "diag_summary_head")]
    weak, ok = [], []
    for sid, row in sorted(mmap.items()):
        meta = graph.skill(sid) or {}
        if meta.get("subject") != subject:
            continue
        pct = round(100 * float(row["score"]))
        name = graph.skill_name(sid, lang)
        (weak if float(row["score"]) < engine.OK else ok).append((pct, name))
    weak.sort()
    for pct, name in weak[:3]:
        lines.append(t(lang, "diag_weak_line", name=name, pct=pct))
    for pct, name in ok[:2]:
        lines.append(t(lang, "diag_ok_line", name=name, pct=pct))
    if not weak and not ok:
        lines.append(t(lang, "diag_none_weak"))
    lines.append(t(lang, "diag_cta"))
    return lines


def nlu_subject_name(subject: str, lang: str):
    from .. import nlu
    return nlu.SUBJECT_NAMES.get(subject, {}).get(lang, subject)


def _elapsed_ms(ctx: dict) -> int:
    import time as _t
    ts = ctx.get("_sent_ts")
    if not ts:
        return 15000
    return max(500, min(int((_t.time() - ts) * 1000), 600000))
