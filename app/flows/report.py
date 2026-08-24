"""Weekly parent report: builds payload from real attempt history, stores a row,
renders the chat message (Hindi/English)."""
from datetime import timedelta

from .. import db, engine, graph
from . import t


def build_report_payload(uid: int, today=None) -> dict:
    return engine.weekly_payload(uid, today)


def render_report(lang: str, payload: dict) -> str:
    names = payload.get("focus_names_hi" if lang == "hi" else "focus_names_en") or []
    lines = [
        t(lang, "report_head", week=payload["week_of"]),
        t(lang, "report_attempts_line", attempts=payload["attempts"],
          correct=payload["correct"], acc=payload["accuracy"]),
    ]
    if names:
        lines.append(t(lang, "report_weak_line", names=", ".join(names)))
    lines.append(t(lang, "report_streak_line", cur=payload["streak_current"]))
    lines.append(t(lang, "report_footer"))
    return "\n".join(lines)


def generate_report(uid: int, today=None) -> tuple[int | None, str]:
    """Build + store report row; returns (row_id, rendered_message)."""
    user = db.query_one("SELECT * FROM users WHERE id=?", (uid,))
    if not user:
        return None, ""
    payload = engine.weekly_payload(uid, today)
    rid = engine.store_report(uid, payload)
    return rid, render_report(user["lang"], payload)


def build_report_reply(uid: int, lang: str) -> str:
    rid, msg = generate_report(uid)
    if not rid:
        return t(lang, "progress_empty")
    db.execute("UPDATE reports SET sent=1 WHERE id=?", (rid,))
    return msg
