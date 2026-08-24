"""Explain flow: turns RAG retrieval results into chat bubbles / API payloads.
Citation line always follows the user's chosen language (hi/en)."""
from .. import rag
from . import t


def compose(res: dict, lang: str) -> tuple[str, str]:
    """(answer_text, citation) from an app.rag.explain() result."""
    if not res.get("excerpt"):
        return t(lang, "explain_none"), ""
    parts = []
    if res.get("synth"):
        parts.append(t(lang, "explain_gpt_head"))
        parts.append(res["synth"])
    parts.append(res["excerpt"])
    cite = t(lang, "explain_cite", src=res["citation"])
    return "\n".join(parts) + "\n" + cite, res["citation"]


def explain_reply(user_row, state: str, ctx: dict, text: str) -> list[str]:
    """Free-chat / mid-practice explain intent. State and ctx are untouched."""
    lang = user_row["lang"]
    res = rag.explain(
        text,
        cls=user_row["grade"] or None,
        subj=ctx.get("subject") or None,
        lang=lang,
    )
    if not res["excerpt"]:
        replies = [t(lang, "explain_none")]
    else:
        replies = [compose(res, lang)[0]]
    if state == "practice":
        from . import practice
        prompt = practice.current_prompt(user_row, ctx, lang)
        if prompt:
            replies.append(prompt)
    return replies
