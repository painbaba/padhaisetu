"""Chat flow orchestration: state machine over chat_sessions.
States: onb_lang -> onb_grade -> onb_subject -> diag -> menu <-> practice, menu -> mock."""
import json
import time
from pathlib import Path

from .. import db, nlu

STRINGS = json.loads((Path(__file__).parent / "strings.json").read_text(encoding="utf-8"))

DEFAULT_STATE = "onb_lang"


def t(lang: str, key: str, **kw) -> str:
    lang = "en" if lang == "en" else "hi"
    tpl = STRINGS.get(lang, {}).get(key) or STRINGS["hi"].get(key) or key
    try:
        return tpl.format(**kw)
    except Exception:
        return tpl


def get_or_create_user(phone: str):
    row = db.query_one("SELECT * FROM users WHERE phone=?", (phone,))
    if row:
        return row
    db.execute(
        "INSERT INTO users(phone, lang, created_at) VALUES(?,?,?)",
        (phone, "hi", db.iso()),
    )
    uid = db.scalar("SELECT id FROM users WHERE phone=?", (phone,))
    db.execute(
        "INSERT OR IGNORE INTO chat_sessions(user_id, state, context_json, updated_at)"
        " VALUES(?,?,?,?)",
        (uid, DEFAULT_STATE, "{}", db.iso()),
    )
    return db.query_one("SELECT * FROM users WHERE phone=?", (phone,))


def load_session(user_id: int):
    row = db.query_one("SELECT state, context_json FROM chat_sessions WHERE user_id=?", (user_id,))
    if not row:
        db.execute(
            "INSERT OR IGNORE INTO chat_sessions(user_id, state, context_json, updated_at)"
            " VALUES(?,?,?,?)",
            (user_id, DEFAULT_STATE, "{}", db.iso()),
        )
        return DEFAULT_STATE, {}
    try:
        ctx = json.loads(row["context_json"] or "{}")
    except Exception:
        ctx = {}
    return row["state"], (ctx if isinstance(ctx, dict) else {})


def save_session(user_id: int, state: str, ctx: dict) -> None:
    db.execute(
        """INSERT INTO chat_sessions(user_id, state, context_json, updated_at)
           VALUES(?,?,?,?)
           ON CONFLICT(user_id) DO UPDATE SET state=excluded.state,
             context_json=excluded.context_json, updated_at=excluded.updated_at""",
        (user_id, state, json.dumps(ctx, ensure_ascii=False), db.iso()),
    )


def option_block(options: list[str]) -> str:
    return "\n".join(f"{i+1}) {o}" for i, o in enumerate(options))


def render_question(qrow, idx: int, total: int, lang: str, label_key: str = "q_label") -> str:
    text = qrow["text_hi"] if lang == "hi" else qrow["text_en"]
    opts = option_block((qrow["options_json"] or "").split("|"))
    keys = set(qrow.keys()) if hasattr(qrow, "keys") else set()
    marks = int(qrow["marks"]) if "marks" in keys and qrow["marks"] is not None else 1
    qtype = qrow["qtype"] if "qtype" in keys else None
    # Board-pattern items carry a qtype tag -> show marks next to the number.
    if label_key == "q_label" and (qtype or marks != 1):
        head = t(lang, "q_label_marks", n=idx, total=total, marks=marks)
    else:
        head = t(lang, label_key, n=idx, total=total)
    return f"{head}\n{text}\n{opts}"


def normalize_answer(text: str) -> int | None:
    return nlu.normalize_answer(text)


def correct_option_text(qrow, lang: str) -> str:
    opts = (qrow["options_json"] or "").split("|")
    idx = int(qrow["correct_idx"])
    return opts[idx] if 0 <= idx < len(opts) else ""


def _prompt_for_state(user_row, state: str, ctx: dict, lang: str) -> list[str]:
    """Re-render the current state's prompt (used after help / language switch)."""
    subject = ctx.get("subject", "")
    subj_name = nlu.SUBJECT_NAMES.get(subject, {}).get(lang, subject)
    if state == "onb_lang":
        return [t(lang, "ask_lang")]
    if state == "onb_grade":
        return [t(lang, "ask_grade")]
    if state == "onb_subject":
        return [t(lang, "ask_subject")]
    if state == "menu":
        return [t(lang, "menu")]
    if state == "mock":
        cur = mock.current_prompt(ctx, lang)
        if cur:
            return [cur]
        return [t(lang, "menu")]
    if state == "diag" and ctx.get("queue"):
        q = diagnostic.current_question(ctx)
        if q is not None:
            return [render_question(q, int(ctx.get("idx", 0)) + 1,
                                    len(ctx["queue"]), lang)]
    if state == "practice":
        cur = practice.current_prompt(user_row, ctx, lang)
        if cur:
            return [cur]
        return [t(lang, "menu")]
    return [t(lang, "menu")]


def handle_message(phone: str, text: str) -> list[str]:
    """Single entry point for every channel. Never raises; always returns replies."""
    user_row = get_or_create_user(phone.strip())
    lang = user_row["lang"]
    try:
        text = (text or "").strip()
        state, ctx = load_session(user_row["id"])

        if state == "onb_lang" and not ctx.get("greeted"):
            ctx["greeted"] = True
            save_session(user_row["id"], state, ctx)
            return [t(lang, "greet_first"), t(lang, "ask_lang")]

        intent = nlu.classify(text)

        if intent == nlu.RESET:
            save_session(user_row["id"], "onb_lang", {"greeted": True})
            return [t(lang, "reset_done"), t(lang, "ask_lang")]

        if intent in (nlu.SET_ENGLISH, nlu.SET_HINDI):
            newlang = "en" if intent == nlu.SET_ENGLISH else "hi"
            db.execute("UPDATE users SET lang=? WHERE id=?", (newlang, user_row["id"]))
            fresh = db.query_one("SELECT * FROM users WHERE id=?", (user_row["id"],))
            return [t(newlang, "switched")] + _prompt_for_state(fresh, state, ctx, newlang)

        if intent == nlu.HELP:
            return [t(lang, "help")] + _prompt_for_state(user_row, state, ctx, lang)

        if intent == nlu.EXPLAIN and state in ("menu", "practice"):
            # Grounded free-chat answer; session state/ctx deliberately untouched.
            return ragflow.explain_reply(user_row, state, dict(ctx), text)

        if state in ("onb_lang", "onb_grade", "onb_subject"):
            replies, newstate, newctx = onboarding.handle(user_row, state, dict(ctx), intent, text)
        elif state == "diag":
            replies, newstate, newctx = diagnostic.handle(user_row, dict(ctx), intent, text)
        elif state == "mock":
            replies, newstate, newctx = mock.handle(user_row, dict(ctx), intent, text)
        elif state in ("menu", "practice"):
            replies, newstate, newctx = practice.handle(user_row, state, dict(ctx), intent, text)
        else:
            replies, newstate, newctx = [t(lang, "menu")], "menu", {}

        if newctx is not ctx and isinstance(newctx, dict):
            newctx.pop("_sent_ts", None)
        save_session(user_row["id"], newstate, newctx)
        return replies
    except Exception:
        import traceback
        traceback.print_exc()
        try:
            return [t(lang, "error_generic")]
        except Exception:
            return ["Kuch gadbad ho gayi. Dobara koshish kijiye."]


def stamp_sent(ctx: dict) -> dict:
    ctx["_sent_ts"] = time.time()
    return ctx


def elapsed_ms(ctx: dict) -> int:
    ts = ctx.get("_sent_ts")
    if not ts:
        return 15000
    ms = int((time.time() - ts) * 1000)
    return max(500, min(ms, 10 * 60 * 1000))


# Submodule imports at the bottom so shared helpers above are already defined
from . import onboarding, diagnostic, practice, ragflow, mock  # noqa: E402
