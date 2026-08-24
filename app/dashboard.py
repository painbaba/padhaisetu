"""GET /dashboard - one server-rendered dark page for judges.
Truthful numbers only: every counter is a live SQL query."""
from datetime import timedelta
from html import escape
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from . import db, engine, graph, qbank, rag

router = APIRouter()

TEMPLATE_PATH = Path(__file__).resolve().parents[1] / "templates" / "dashboard.html"

BAND_COLORS = {"weak": "#e05252", "mid": "#e0a83a", "strong": "#3fae6a"}


def _band(score: float) -> str:
    if score < engine.WEAK:
        return "weak"
    if score < engine.OK:
        return "mid"
    return "strong"


def _counters() -> dict:
    users = int(db.scalar("SELECT COUNT(*) FROM users") or 0)
    questions = qbank.count()
    attempts = int(db.scalar("SELECT COUNT(*) FROM attempts") or 0)
    attempts_24h = int(db.scalar(
        "SELECT COUNT(*) FROM attempts WHERE created_at >= ?",
        (db.iso(db.now_ist() - timedelta(hours=24)),)) or 0)
    correct = int(db.scalar("SELECT COUNT(*) FROM attempts WHERE correct=1") or 0)
    accuracy = round(100.0 * correct / attempts, 1) if attempts else 0.0
    active = int(db.scalar(
        "SELECT COUNT(DISTINCT user_id) FROM attempts WHERE created_at >= ?",
        (db.iso(db.now_ist() - timedelta(days=7)),)) or 0)
    reports = int(db.scalar("SELECT COUNT(*) FROM reports") or 0)
    return {
        "USERS": users,
        "QUESTIONS": questions,
        "ATTEMPTS": attempts,
        "ATTEMPTS_24H": attempts_24h,
        "ACCURACY": f"{accuracy}%",
        "ACTIVE": active,
        "REPORTS": reports,
        "RAG_CHUNKS": rag.total_chunks(),
    }


def _student_card(user_row) -> str:
    uid = user_row["id"]
    name = user_row["name"] or ("Student " + str(uid))
    phone = str(user_row["phone"])[-4:].rjust(4, "*")
    grade = user_row["grade"] or "-"
    lang = "हिंदी" if user_row["lang"] == "hi" else "English"
    cur, best = engine.get_streak(uid)

    rows = db.query(
        """SELECT * FROM mastery WHERE user_id=? AND seen>0
           ORDER BY last_seen DESC LIMIT 8""", (uid,))
    cells = []
    for r in rows:
        score = float(r["score"])
        band = _band(score)
        title = graph.skill_name(r["skill_id"], "en")
        pct = round(100 * score)
        cells.append(
            f'<div class="cell {band}" title="{escape(title)} — {pct}%">{pct}</div>')
    grid = "".join(cells) or '<div class="nocells">no attempts yet</div>'
    last_seen = db.scalar(
        "SELECT MAX(created_at) FROM attempts WHERE user_id=?", (uid,)) or "-"

    total_att = int(db.scalar("SELECT COUNT(*) FROM attempts WHERE user_id=?", (uid,)) or 0)
    ok_att = int(db.scalar(
        "SELECT COUNT(*) FROM attempts WHERE user_id=? AND correct=1", (uid,)) or 0)
    acc = round(100.0 * ok_att / total_att) if total_att else 0

    return (
        '<div class="card">'
        f'<div class="cardhead"><b>{escape(name)}</b>'
        f'<span class="meta">*{escape(phone)} · class {escape(str(grade))} · {lang}</span></div>'
        f'<div class="stats">attempts <b>{total_att}</b> · accuracy <b>{acc}%</b> · '
        f'streak <b>{cur}</b>/best <b>{best}</b> · last <b>{escape(str(last_seen)[:10])}</b></div>'
        f'<div class="grid">{grid}</div>'
        '</div>'
    )


def _at_risk_list() -> str:
    items = []
    for u in db.query("SELECT * FROM users ORDER BY id"):
        uid = u["id"]
        weakest = db.query_one(
            "SELECT skill_id, score FROM mastery WHERE user_id=? AND seen>0 "
            "ORDER BY score ASC LIMIT 1", (uid,))
        last = db.scalar("SELECT MAX(created_at) FROM attempts WHERE user_id=?", (uid,))
        reasons = []
        if weakest and float(weakest["score"]) < 0.35:
            reasons.append(f"mastery {round(100*float(weakest['score']))}% on "
                           f"{graph.skill_name(weakest['skill_id'], 'en')}")
        if not last:
            continue
        if db.query_one("SELECT 1") and last < db.iso(db.now_ist() - timedelta(days=3)):
            reasons.append("inactive 3+ days")
        if reasons:
            name = u["name"] or f"Student {uid}"
            items.append(f"<li><b>{escape(name)}</b>: {escape('; '.join(reasons))}</li>")
    if not items:
        return "<li>No at-risk students right now.</li>"
    return "".join(items)


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard():
    tpl = TEMPLATE_PATH.read_text(encoding="utf-8")
    counters = _counters()
    for key, val in counters.items():
        tpl = tpl.replace("__" + key + "__", escape(str(val)))
    students = db.query("SELECT * FROM users ORDER BY id LIMIT 50")
    tpl = tpl.replace("__STUDENTS__",
                      "".join(_student_card(u) for u in students) or
                      "<div class='nocells'>Run <code>python data/seed.py</code> to populate.</div>")
    tpl = tpl.replace("__ATRISK__", _at_risk_list())
    tpl = tpl.replace("__GENERATED__", db.iso())
    return HTMLResponse(tpl)
