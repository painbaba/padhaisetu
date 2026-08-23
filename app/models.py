"""Pydantic domain models (brief section 4: User, Question, Attempt, MasteryState, PracticeSet, Report)."""
from pydantic import BaseModel, Field


class User(BaseModel):
    id: int
    phone: str
    lang: str = "hi"
    name: str | None = None
    grade: int | None = None
    created_at: str | None = None


class Question(BaseModel):
    id: int
    subject: str
    grade: int
    skill_id: str
    difficulty: int = Field(ge=1, le=3)
    text_hi: str
    text_en: str
    options: list[str]
    correct_idx: int
    hint_hi: str
    hint_en: str
    solution_hi: str
    solution_en: str
    gen_params: dict | None = None
    active: bool = True


class Attempt(BaseModel):
    user_id: int
    question_id: int
    correct: bool
    time_ms: int = 0
    mode: str  # diag | practice | remediate
    skill_id: str
    created_at: str | None = None


class MasteryState(BaseModel):
    user_id: int
    skill_id: str
    score: float = 0.5
    seen: int = 0
    last_seen: str | None = None
    due_after: str | None = None


class PracticeSet(BaseModel):
    user_id: int
    date: str
    subject: str
    grade: int
    question_ids: list[int]


class Report(BaseModel):
    id: int | None = None
    user_id: int
    week_of: str
    payload: dict
    sent: bool = False
