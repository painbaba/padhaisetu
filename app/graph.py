"""Knowledge-graph loader + prerequisite walker (brief section 6)."""
import json
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
WEAK_THRESHOLD = 0.45


@lru_cache(maxsize=1)
def _raw() -> dict:
    out: dict[str, list] = {"maths": [], "science": []}
    for subject in ("maths", "science"):
        path = DATA_DIR / f"graph_{subject}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        graphs = data["classes"] if isinstance(data, dict) else data
        for g in graphs:
            g["subject"] = subject
            out[subject].append(g)
    return out


@lru_cache(maxsize=1)
def skills_index() -> dict:
    """skill_id -> {id,name_hi,name_en,prereqs,weight,class,subject,chapter_id}"""
    idx: dict = {}
    for subject, graphs in _raw().items():
        for g in graphs:
            for ch in g["chapters"]:
                for sk in ch["skills"]:
                    idx[sk["id"]] = {
                        "id": sk["id"],
                        "name_hi": sk["name_hi"],
                        "name_en": sk["name_en"],
                        "prereqs": list(sk.get("prereqs", [])),
                        "weight": float(sk.get("weight", 1.0)),
                        "class": int(g["class"]),
                        "subject": subject,
                        "chapter_id": ch["id"],
                    }
    return idx


def skill(skill_id: str) -> dict | None:
    return skills_index().get(skill_id)


def skill_name(skill_id: str, lang: str) -> str:
    s = skills_index().get(skill_id)
    if not s:
        return skill_id
    return s["name_hi"] if lang == "hi" else s["name_en"]


def chapters(subject: str, grade: int) -> list[dict]:
    for g in _raw()[subject]:
        if int(g["class"]) == int(grade):
            return g["chapters"]
    return []


def chapter_name(chapter: dict, lang: str) -> str:
    return chapter["name_hi"] if lang == "hi" else chapter["name_en"]


def diagnostic_chapters(subject: str, grade: int, k: int = 5) -> list[dict]:
    """k chapters evenly spread across the class syllabus, deterministic."""
    chs = chapters(subject, grade)
    if not chs:
        return []
    k = min(k, len(chs))
    if k == 1:
        return [chs[0]]
    idx = [round(i * (len(chs) - 1) / (k - 1)) for i in range(k)]
    seen: set[int] = set()
    picked = []
    for i in idx:
        if i not in seen:
            seen.add(i)
            picked.append(chs[i])
    return picked


def representative_skill(chapter: dict, have_questions: set[str]) -> str | None:
    for sk in chapter["skills"]:
        if sk["id"] in have_questions:
            return sk["id"]
    return None


def walker(start_skill_id: str, mastery_score, threshold: float = WEAK_THRESHOLD) -> str | None:
    """DFS over prerequisites; first skill whose mastery < threshold wins.
    mastery_score: callable(skill_id)->float (default 0.5 for unseen)."""
    visited = {start_skill_id}
    stack = list(reversed(list(skills_index().get(start_skill_id, {}).get("prereqs", []))))
    while stack:
        sid = stack.pop()
        if sid in visited:
            continue
        visited.add(sid)
        if mastery_score(sid) < threshold:
            return sid
        stack.extend(reversed(skills_index().get(sid, {}).get("prereqs", [])))
    return None


def all_skills(subject: str | None = None, grade: int | None = None) -> list[str]:
    out = []
    for sid, s in skills_index().items():
        if subject and s["subject"] != subject:
            continue
        if grade is not None and s["class"] != int(grade):
            continue
        out.append(sid)
    return sorted(out)
