"""Question bank loader: reads data/qbank/*.json into SQLite idempotently."""
import json
from pathlib import Path

from . import db

QBANK_DIR = Path(__file__).resolve().parents[1] / "data" / "qbank"


def load_file(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    items = data["items"] if isinstance(data, dict) else data
    return items


def insert_item(conn, subject: str, grade: int, item: dict) -> None:
    conn.execute(
        """INSERT OR IGNORE INTO questions(
             subject, grade, skill_id, difficulty, text_hi, text_en,
             options_json, correct_idx, hint_hi, hint_en, solution_hi, solution_en,
             gen_params_json, marks, qtype, active)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)""",
        (
            subject,
            grade,
            item["skill_id"],
            int(item.get("difficulty", 1)),
            item["text_hi"],
            item["text_en"],
            "|".join(item["options"]),
            int(item["correct_idx"]),
            item.get("hint_hi", ""),
            item.get("hint_en", ""),
            item.get("solution_hi", ""),
            item.get("solution_en", ""),
            json.dumps(item["gen_params"], ensure_ascii=False) if item.get("gen_params") else None,
            int(item.get("marks", 1) or 1),
            item.get("qtype"),
        ),
    )


def load_all(force: bool = False) -> int:
    """Insert every bank item; unique index makes re-imports no-ops. Returns inserted count."""
    inserted = 0
    files = sorted(QBANK_DIR.glob("*.json"))
    with db.connect() as conn:
        if not force and conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0] > 0:
            return 0
        for path in files:
            parts = path.stem.split("_")  # e.g. maths_8 / science_10
            if len(parts) != 2 or not parts[1].isdigit():
                continue
            subject, grade = parts[0], int(parts[1])
            before = conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
            for item in load_file(path):
                insert_item(conn, subject, grade, item)
            after = conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
            inserted += after - before
    return inserted


def ensure_loaded() -> int:
    with db.connect() as conn:
        n = conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
    if n == 0:
        return load_all()
    return 0


def get_question(qid: int):
    return db.query_one("SELECT * FROM questions WHERE id=? AND active=1", (qid,))


def questions_for_skill(skill_id: str):
    return db.query(
        "SELECT * FROM questions WHERE skill_id=? AND active=1 ORDER BY difficulty, id",
        (skill_id,),
    )


def skills_with_questions(subject: str | None = None, grade: int | None = None) -> set[str]:
    sql = "SELECT DISTINCT skill_id FROM questions WHERE active=1"
    params: list = []
    if subject:
        sql += " AND subject=?"
        params.append(subject)
    if grade is not None:
        sql += " AND grade=?"
        params.append(grade)
    return {r[0] for r in db.query(sql, tuple(params))}


def count() -> int:
    return int(db.scalar("SELECT COUNT(*) FROM questions WHERE active=1") or 0)
