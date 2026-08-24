import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import db, qbank  # noqa: E402


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("PADHAISETU_DB", str(tmp_path / "channels.db"))
    db.init_db()
    qbank.load_all(force=True)
    from app.channels import simulator as sim

    sim.reset_store()
    from app.main import app

    with TestClient(app) as c:
        yield c


# ---------- health ----------

def test_health_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


# ---------- simulator (M1 gate: scripted onboarding via /demo/send) ----------

def test_demo_page_renders_phone_mockup(client):
    r = client.get("/demo")
    assert r.status_code == 200
    html = r.text
    assert "PadhaiSetu" in html and "/demo/send" in html and "/demo/poll" in html


def test_demo_send_scripted_onboarding_roundtrip(client):
    phone = "+919000000001"
    r1 = client.post("/demo/send", json={"phone": phone, "text": "hello"})
    assert r1.status_code == 200
    body = r1.json()
    assert body["ok"] is True
    assert any("भाषा" in m or "language" in m.lower() for m in body["replies"])

    r2 = client.post("/demo/send", json={"phone": phone, "text": "1"})
    assert any("8" in m for m in r2.json()["replies"])          # grade asked

    r3 = client.post("/demo/send", json={"phone": phone, "text": "9"})
    assert any("विषय" in m or "subject" in m.lower() for m in r3.json()["replies"])

    r4 = client.post("/demo/send", json={"phone": phone, "text": "1"})
    replies = r4.json()["replies"]
    assert any("प्रश्न" in m or "Question" in m for m in replies)

    uid = int(db.scalar("SELECT id FROM users WHERE phone=?", (phone,)))
    state = db.scalar("SELECT state FROM chat_sessions WHERE user_id=?", (uid,))
    assert state == "diag"


def test_demo_poll_incremental(client):
    phone = "+919000000002"
    client.post("/demo/send", json={"phone": phone, "text": "hi"})
    first = client.get("/demo/poll", params={"phone": phone, "after": 0}).json()
    assert first["messages"]
    last = first["last"]
    second = client.get("/demo/poll", params={"phone": phone, "after": last}).json()
    assert second["messages"] == []


def test_demo_poll_isolated_per_phone(client):
    client.post("/demo/send", json={"phone": "+919000000003", "text": "hello"})
    out = client.get("/demo/poll", params={"phone": "+919999999999", "after": 0}).json()
    assert out["messages"] == []


def test_demo_send_rejects_empty(client):
    r = client.post("/demo/send", json={"phone": "", "text": ""})
    assert r.json()["ok"] is False


# ---------- whatsapp cloud api (M6 gate: verify echoes hub.challenge; mocked send) ----------

def test_whatsapp_verify_echoes_challenge(client, monkeypatch):
    monkeypatch.setenv("WHATSAPP_VERIFY_TOKEN", "tok123")
    from app import config
    config.WHATSAPP_VERIFY_TOKEN = "tok123"
    r = client.get("/whatsapp/webhook", params={
        "hub.mode": "subscribe", "hub.verify_token": "tok123",
        "hub.challenge": "998877"})
    assert r.status_code == 200
    assert r.text == "998877"
    config.WHATSAPP_VERIFY_TOKEN = "padhaisetu-verify"


def test_whatsapp_verify_wrong_token_403(client):
    r = client.get("/whatsapp/webhook", params={
        "hub.mode": "subscribe", "hub.verify_token": "WRONG",
        "hub.challenge": "42"})
    assert r.status_code == 403


def test_whatsapp_receive_dispatches_and_sends_mocked(client, monkeypatch):
    sent = []

    async def fake_send(phone, body):
        sent.append((phone, body))
        return True

    from app.channels import whatsapp
    monkeypatch.setattr(whatsapp, "send_whatsapp_text", fake_send)

    payload = {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "WABA",
            "changes": [{
                "value": {
                    "messaging_product": "whatsapp",
                    "messages": [{
                        "from": "919000000010",
                        "type": "text",
                        "text": {"body": "namaste"},
                    }],
                },
                "field": "messages",
            }],
        }],
    }
    r = client.post("/whatsapp/webhook", json=payload)
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    assert sent, "expected mocked outbound sends"
    assert sent[0][0] == "919000000010"
    assert any("भाषा" in b or "language" in b.lower() for _, b in sent)


def test_whatsapp_receive_malformed_payload_ok(client):
    r = client.post("/whatsapp/webhook", content=b"not-json",
                    headers={"Content-Type": "application/json"})
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_explain_endpoint_falls_back_without_api_key(client, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    from app import config
    old = config.OPENAI_API_KEY
    config.OPENAI_API_KEY = ""
    try:
        row = db.query_one("SELECT id FROM questions LIMIT 1")
        r = client.post("/explain", json={"question_id": row["id"], "lang": "hi"})
        assert r.status_code == 200
        data = r.json()
        assert data["source"] == "stored"
        assert data["hint"]
    finally:
        config.OPENAI_API_KEY = old


# ---------- M5: dashboard counters truthful + heat-grid for 3 students ----------

def _make_student(phone, name, grade, subject, n_attempts):
    from app import engine
    db.execute("INSERT INTO users(phone, lang, name, grade, created_at)"
               " VALUES(?,?,?,?,?)", (phone, "hi", name, grade, db.iso()))
    uid = int(db.scalar("SELECT id FROM users WHERE phone=?", (phone,)))
    skills = sorted(qbank.skills_with_questions(subject, grade))
    for i, sid in enumerate(skills[:n_attempts]):
        q = engine.pick_question_for_skill(sid, 2)
        if q is None:
            continue
        engine.record_attempt(uid, q, correct=(i % 2 == 0), time_ms=15000,
                              mode="practice")
    return uid


def test_dashboard_counters_match_db_exactly(client):
    _make_student("+919000000021", "आरती", 8, "maths", 4)
    _make_student("+919000000022", "Rahul", 10, "maths", 3)
    _make_student("+919000000023", "Sneha", 9, "science", 2)

    html = client.get("/dashboard").text
    assert "__USERS__" not in html and "__QUESTIONS__" not in html

    expected = {
        "users": int(db.scalar("SELECT COUNT(*) FROM users")),
        "attempts": int(db.scalar("SELECT COUNT(*) FROM attempts")),
    }
    assert f'<div class="n">{expected["users"]}</div>' in html
    assert f'<div class="n">{expected["attempts"]}</div>' in html
    qcount = int(db.scalar(
        "SELECT COUNT(*) FROM questions WHERE active=1"))
    assert f'<div class="n">{qcount}</div>' in html


def test_dashboard_heat_grid_renders_three_students(client):
    _make_student("+919000000031", "आरती", 8, "maths", 4)
    _make_student("+919000000032", "Rahul", 10, "maths", 3)
    _make_student("+919000000033", "Sneha", 9, "science", 2)
    html = client.get("/dashboard").text
    assert html.count('class="cardhead"') == 3
    assert 'class="cell weak"' in html or 'class="cell strong"' in html
    assert "Demo QR" in html and "At-risk students".lower() in html.lower()


def test_seed_script_populates_demo_data(tmp_path, monkeypatch):
    import subprocess
    env = dict(os.environ)
    env["PADHAISETU_DB"] = str(tmp_path / "seeded.db")
    root = Path(__file__).resolve().parents[1]
    r = subprocess.run([sys.executable, str(root / "data" / "seed.py")],
                       capture_output=True, text=True, env=env, cwd=str(root))
    assert r.returncode == 0, r.stderr

    os.environ["PADHAISETU_DB"] = env["PADHAISETU_DB"]
    try:
        users = db.scalar("SELECT COUNT(*) FROM users")
        attempts = db.scalar("SELECT COUNT(*) FROM attempts")
        reports = db.scalar("SELECT COUNT(*) FROM reports")
        streaks = db.scalar("SELECT COUNT(*) FROM streaks")
        assert users == 3 and attempts >= 15 and reports == 3 and streaks == 3
    finally:
        os.environ.pop("PADHAISETU_DB", None)
