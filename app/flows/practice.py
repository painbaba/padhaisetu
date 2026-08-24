"""Daily practice: 5 targeted MCQs, immediate feedback, prerequisite remediation,
streak update on set completion. Also serves the menu (practice/progress/report)."""
from .. import db, engine, graph
from . import t, render_question, normalize_answer, correct_option_text

SET_SIZE = 5
MAX_REMEDIATIONS = 2


# ---------- menu ----------

def handle(user_row, state: str, ctx: dict, intent: str, text: str):
    if state == "menu" or not ctx.get("mode"):
        return _menu(user_row, text, ctx)
    return _practice(user_row, ctx, intent, text)


def _menu(user_row, text: str, ctx: dict):
    from .. import nlu
    uid = user_row["id"]
    lang = user_row["lang"]
    choice = nlu.pick_menu_number(text)
    low = (text or "").lower()

    if choice == 1 or "practice" in low or "abhyas" in low or "अभ्यास" in text:
        subject = ctx.get("subject") or _infer_subject(uid)
        grade = user_row["grade"]
        focus = ctx.get("mock_focus") or []
        picks, board, intro = None, False, None
        if focus:
            # Post-mock handoff: a set targeting the mock's weakest skills first.
            picks = _focused_set(uid, subject, grade, focus)
            if picks:
                intro = t(lang, "practice_intro", total=len(picks))
        if not picks:
            board = engine.pick_board_set(uid, subject, grade)
            if board:
                picks = board
                intro = t(lang, "practice_intro_board", total=len(picks))
            else:
                picks = engine.pick_daily_set(uid, subject, grade, SET_SIZE)
                intro = t(lang, "practice_intro", total=len(picks))
        if not picks:
            return [t(lang, "unknown"), t(lang, "menu")], "menu", ctx
        newctx = {
            "greeted": True,
            "subject": subject,
            "mode": "practice",
            "board": bool(board),
            "queue": [{"qid": p["question"]["id"], "skill": p["skill_id"]} for p in picks],
            "idx": 0,
            "correct_ct": 0,
            "remediations_used": 0,
        }
        q0 = db.query_one("SELECT * FROM questions WHERE id=?", (newctx["queue"][0]["qid"],))
        return [intro, render_question(q0, 1, len(picks), lang)], "practice", _stamp(newctx)

    if choice == 4 or "mock" in low or "मॉक" in text or "पेपर" in text:
        from . import mock
        return mock.start(user_row, ctx)

    if choice == 2:
        return [_progress_message(uid, lang)], "menu", ctx

    if choice == 3:
        from .report import build_report_reply
        reply = build_report_reply(uid, lang)
        return [reply], "menu", ctx

    if ctx.get("just_diagnosed"):
        ctx.pop("just_diagnosed")
    return [t(lang, "menu")], "menu", ctx


def _focused_set(uid: int, subject: str, grade: int, focus: list) -> list:
    """Post-mock practice set: weakest mock skills first, padded from the daily
    ranking. Falls back to None when nothing usable is found (caller uses the
    normal board/daily path)."""
    picks, used_skills = [], set()
    for sid in focus:
        q = engine.pick_question_for_skill(sid, pref_diff=2)
        if q is not None:
            picks.append({"question": q, "skill_id": sid})
            used_skills.add(sid)
        if len(picks) >= SET_SIZE:
            return picks
    for entry in engine.ranked_skills(uid, subject, grade):
        if len(picks) >= SET_SIZE:
            break
        sid = entry["skill_id"]
        if sid in used_skills:
            continue
        q = engine.pick_question_for_skill(sid, engine.preferred_difficulty(entry["score"]))
        if q is None:
            continue
        used_skills.add(sid)
        picks.append({"question": q, "skill_id": sid})
    return picks


def _infer_subject(uid: int) -> str:
    row = db.query_one(
        """SELECT q.subject FROM attempts a JOIN questions q ON q.id=a.question_id
           WHERE a.user_id=? GROUP BY q.subject ORDER BY COUNT(*) DESC LIMIT 1""", (uid,))
    return row["subject"] if row else "maths"


def _progress_message(uid: int, lang: str) -> str:
    rows = db.query(
        "SELECT * FROM mastery WHERE user_id=? AND seen>0 ORDER BY score ASC LIMIT 5", (uid,))
    if not rows:
        return t(lang, "progress_empty")
    lines = [t(lang, "progress_head")]
    cur, best = engine.get_streak(uid)
    for r in rows:
        lines.append(t(lang, "progress_skill_line",
                       name=graph.skill_name(r["skill_id"], lang),
                       pct=round(100 * float(r["score"])), seen=int(r["seen"])))
    lines.append(t(lang, "streak_line", cur=cur, best=best))
    return "\n".join(lines)


# ---------- practice turn loop ----------

def current_question(ctx: dict):
    idx = int(ctx.get("idx", 0))
    queue = ctx.get("queue", [])
    if idx >= len(queue):
        return None
    return db.query_one("SELECT * FROM questions WHERE id=?", (queue[idx]["qid"],))


def current_prompt(user_row, ctx: dict, lang: str) -> str | None:
    q = current_question(ctx)
    if ctx.get("remediating"):
        rem_q = ctx.get("remedial_qid")
        if rem_q:
            rq = db.query_one("SELECT * FROM questions WHERE id=?", (rem_q,))
            if rq is not None:
                return render_question(rq, 0, 0, lang, label_key="remedial_label")
    if q is not None:
        return render_question(q, int(ctx["idx"]) + 1, len(ctx["queue"]), lang)
    return None


def _practice(user_row, ctx: dict, intent: str, text: str):
    uid = user_row["id"]
    lang = user_row["lang"]

    ans = normalize_answer(text)
    if ans is None:
        prompt = current_prompt(user_row, ctx, lang)
        return ([t(lang, "choose_answer")] + ([prompt] if prompt else [])), \
            "practice", _stamp(ctx)

    if ctx.get("remediating"):
        return _answer_remediation(user_row, ctx, ans)

    q = current_question(ctx)
    if q is None:
        return [t(lang, "menu")], "menu", {"subject": ctx.get("subject", "")}

    correct = ans == int(q["correct_idx"])
    engine.record_attempt(uid, q, correct, _elapsed_ms(ctx), "practice")
    ctx["correct_ct"] = int(ctx.get("correct_ct", 0)) + (1 if correct else 0)

    feedback = []
    if correct:
        ms = _last_ms(ctx)
        feedback.append(t(lang, "correct_fast" if ms < engine.FAST_MS else "correct_slow"))
    else:
        feedback.append(t(lang, "wrong_hint",
                          hint=(q["hint_hi"] if lang == "hi" else q["hint_en"])))
        remediation = None
        if int(ctx.get("remediations_used", 0)) < MAX_REMEDIATIONS:
            remediation = engine.remediation_target(
                uid, q["skill_id"], exclude={q["skill_id"]})
        if remediation is not None:
            topic = graph.skill_name(remediation["skill_id"], lang)
            feedback.append(t(lang, "bridge", topic=topic))
            rq = remediation["question"]
            ctx["remediating"] = True
            ctx["remedial_qid"] = rq["id"]
            ctx["remedial_skill"] = remediation["skill_id"]
            ctx["remediations_used"] = int(ctx.get("remediations_used", 0)) + 1
            feedback.append(render_question(rq, 0, 0, lang, label_key="remedial_label"))
            return feedback, "practice", _stamp(ctx)
        feedback.append(t(lang, "solution_prefix",
                          sol=(q["solution_hi"] if lang == "hi" else q["solution_en"])))

    more, newstate, newctx = _advance_or_finish(user_row, ctx)
    return feedback + more, newstate, newctx


def _answer_remediation(user_row, ctx: dict, ans: int):
    uid = user_row["id"]
    lang = user_row["lang"]
    rq = db.query_one("SELECT * FROM questions WHERE id=?", (ctx.get("remedial_qid"),))
    correct = rq is not None and ans == int(rq["correct_idx"])
    if rq is not None:
        engine.record_attempt(uid, rq, correct, _elapsed_ms(ctx), "remediate")
    feedback = [t(lang, "diag_correct" if correct else "diag_wrong")]
    ctx["remediating"] = False
    ctx.pop("remedial_qid", None)
    if not correct and rq is not None:
        feedback.append(t(lang, "solution_prefix",
                          sol=(rq["solution_hi"] if lang == "hi" else rq["solution_en"])))
    more, newstate, newctx = _advance_or_finish(user_row, ctx)
    return feedback + more, newstate, newctx


def _advance_or_finish(user_row, ctx: dict):
    uid = user_row["id"]
    lang = user_row["lang"]
    ctx["idx"] = int(ctx.get("idx", 0)) + 1
    total = len(ctx.get("queue", []))

    if ctx["idx"] >= total:
        cur, best = engine.apply_streak(uid)
        done = t(lang, "set_complete", k=int(ctx.get("correct_ct", 0)), total=total)
        streak_line = t(lang, "streak_line", cur=cur, best=best)
        newctx = {"greeted": True, "subject": ctx.get("subject", "")}
        return [done, streak_line], "menu", newctx

    nxt = current_question(ctx)
    if nxt is not None:
        return [render_question(nxt, int(ctx["idx"]) + 1, total, lang)], "practice", ctx
    return [], "practice", ctx


def _stamp(ctx: dict) -> dict:
    import time as _t
    ctx["_sent_ts"] = _t.time()
    return ctx


def _elapsed_ms(ctx: dict) -> int:
    import time as _t
    ts = ctx.get("_sent_ts")
    if not ts:
        return 15000
    return max(500, min(int((_t.time() - ts) * 1000), 600000))


def _last_ms(ctx: dict) -> int:
    return _elapsed_ms(ctx)
