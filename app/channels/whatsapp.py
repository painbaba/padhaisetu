"""Meta WhatsApp Cloud API channel: webhook verify + receive -> flows -> Graph API send.
Wired but demo-critical NO; unit-tested with mocks only."""
import logging

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse

from .. import config, flows

router = APIRouter(prefix="/whatsapp")
log = logging.getLogger("padhaisetu.whatsapp")


@router.get("/webhook")
def verify(request: Request):
    """Meta subscription handshake: echo hub.challenge when the token matches."""
    qp = request.query_params
    mode = qp.get("hub.mode", "")
    token = qp.get("hub.verify_token", "")
    challenge = qp.get("hub.challenge", "")
    if mode == "subscribe" and token == config.WHATSAPP_VERIFY_TOKEN:
        return PlainTextResponse(challenge)
    return PlainTextResponse("forbidden", status_code=403)


def _extract_messages(payload: dict):
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            for msg in value.get("messages", []):
                phone = msg.get("from")
                text = (msg.get("text") or {}).get("body", "")
                mtype = msg.get("type")
                if phone and mtype == "text" and text.strip():
                    yield phone, text


async def send_whatsapp_text(phone: str, body: str) -> bool:
    """POST a text message through the Cloud API. No-op when unconfigured."""
    if not (config.WHATSAPP_TOKEN and config.WHATSAPP_PHONE_ID):
        log.warning("whatsapp not configured; dropping message to %s", phone)
        return False
    try:
        import httpx

        url = f"{config.GRAPH_API_BASE}/{config.WHATSAPP_PHONE_ID}/messages"
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(
                url,
                headers={"Authorization": f"Bearer {config.WHATSAPP_TOKEN}"},
                json={
                    "messaging_product": "whatsapp",
                    "to": phone,
                    "type": "text",
                    "text": {"body": body},
                },
            )
            return r.status_code < 400
    except Exception:
        log.exception("whatsapp send failed for %s", phone)
        return False


@router.post("/webhook")
async def receive(request: Request):
    try:
        payload = await request.json()
    except Exception:
        return {"ok": True}
    try:
        for phone, text in _extract_messages(payload):
            replies = flows.handle_message(phone, text)
            for reply in replies:
                await send_whatsapp_text(phone, reply)
    except Exception:
        log.exception("webhook processing error")
    return {"ok": True}
