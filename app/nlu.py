"""Rule-based Hindi + English intent router. No ML, fully deterministic."""
import re

GREET = "greet"
HELP = "help"
RESET = "reset"
SET_ENGLISH = "set_english"
SET_HINDI = "set_hindi"
EXPLAIN = "explain"
MOCK = "mock"
NONE = "none"

_GREET_RE = re.compile(
    r"^(hi|hello|hey|namaste|namaskar|namaskaram|helo|हैलो|नमस्ते|नमस्कार|हाय)[\s!.]*$", re.I
)
_HELP_RE = re.compile(r"\b(help|madad|sahayata|मदद|सहायता)\b", re.I)
_RESET_RE = re.compile(r"\b(reset|restart|रीसेट|रीस्टार्ट|फिर\s*से|नया)\b", re.I)
_EXPLAIN_RE = re.compile(
    r"\b(explain|why|how|kyun|kyu|kion|kaise|kese|samjhao|samjhaye?|batao|bataiye|what\s+is)\b"
    r"|समझाइए|समझाओ|समझा|क्यों|क्यो |कैसे|बताओ|बताइए|क्या\s*है",
    re.I,
)
_MOCK_RE = re.compile(r"\bmock\b|मॉक|पेपर", re.I)
_ENGLISH_RE = re.compile(r"\b(english|en)\b|अंग्रेज़ी|अंग्रेजी|अँग्रेज़ी", re.I)
_HINDI_RE = re.compile(r"\bhindi\b|हिंदी", re.I)

_DEV_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")

_ANSWER_MAP = {"1": 0, "2": 1, "3": 2, "4": 3, "a": 0, "b": 1, "c": 2, "d": 3}


def classify(text: str) -> str:
    t = (text or "").strip().translate(_DEV_DIGITS)
    if not t:
        return NONE
    if _ENGLISH_RE.search(t):
        return SET_ENGLISH
    if _HINDI_RE.search(t):
        return SET_HINDI
    if _RESET_RE.search(t):
        return RESET
    if _HELP_RE.search(t):
        return HELP
    if _MOCK_RE.search(t):
        return MOCK
    if _EXPLAIN_RE.search(t):
        return EXPLAIN
    if _GREET_RE.match(t):
        return GREET
    return NONE


def normalize_answer(text: str) -> int | None:
    """Return 0-based option index for 1-4 / a-d inputs, else None."""
    t = (text or "").strip().translate(_DEV_DIGITS).lower()
    m = re.match(r"^(?:option\s*)?([1-4a-d])[\).\s]*$", t)
    if m:
        return _ANSWER_MAP[m.group(1)]
    return None


def pick_grade(text: str) -> int | None:
    t = (text or "").translate(_DEV_DIGITS)
    m = re.search(r"(?:कक्षा|class)?\s*\b(8|9|10)\b", t, re.I)
    return int(m.group(1)) if m else None


def pick_subject(text: str) -> str | None:
    t = (text or "").lower()
    if re.search(r"\b(maths?|mathematics|ganit)\b|गणित|^1$|^\s*1\s*[\).]?", t):
        return "maths"
    if re.search(r"\b(science|vigyan)\b|विज्ञान|^2$|^\s*2\s*[\).]?", t):
        return "science"
    return None


def pick_menu_number(text: str) -> int | None:
    t = (text or "").strip().translate(_DEV_DIGITS)
    m = re.match(r"^([1-4])[\).]?$", t)
    return int(m.group(1)) if m else None


SUBJECT_NAMES = {
    "maths": {"hi": "गणित", "en": "Maths"},
    "science": {"hi": "विज्ञान", "en": "Science"},
}
