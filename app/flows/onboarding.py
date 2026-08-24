"""Onboarding: greet -> language -> grade (8/9/10) -> subject pick -> diagnostic."""
from .. import db, nlu


def handle(user_row, state: str, ctx: dict, intent: str, text: str):
    uid = user_row["id"]
    lang = user_row["lang"]

    if state == "onb_lang":
        low = (text or "").lower()
        if "2" in low or "english" in low or "en" == low or "अंग्रेज" in text:
            lang = "en"
        elif "1" in low or "हिंदी" in text or "hindi" in low:
            lang = "hi"
        else:
            return [nlu_t(lang, "bad_choice"), nlu_t(lang, "ask_lang")], "onb_lang", ctx
        db.execute("UPDATE users SET lang=? WHERE id=?", (lang, uid))
        return [nlu_t(lang, "lang_ok"), nlu_t(lang, "ask_grade")], "onb_grade", ctx

    if state == "onb_grade":
        grade = nlu.pick_grade(text)
        if grade is None:
            return [nlu_t(lang, "bad_choice"), nlu_t(lang, "ask_grade")], "onb_grade", ctx
        db.execute("UPDATE users SET grade=? WHERE id=?", (grade, uid))
        fresh = db.query_one("SELECT * FROM users WHERE id=?", (uid,))
        return ([nlu_t(fresh["lang"], "ask_subject")], "onb_subject",
                {"subject": ctx.get("subject", "")})

    if state == "onb_subject":
        subject = nlu.pick_subject(text)
        if subject is None:
            return [nlu_t(lang, "bad_choice"), nlu_t(lang, "ask_subject")], "onb_subject", ctx
        fresh = db.query_one("SELECT * FROM users WHERE id=?", (uid,))
        from . import diagnostic
        replies, newstate, newctx = diagnostic.start(fresh, subject)
        newctx.setdefault("subject", subject)
        return replies, newstate, newctx

    return [nlu_t(lang, "menu")], "menu", {}


def nlu_t(lang, key, **kw):
    from . import t
    return t(lang, key, **kw)
