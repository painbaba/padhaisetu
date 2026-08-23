"""Judge dashboard: GET /dashboard one server-rendered dark page. Filled out in M5."""
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()


@router.get("/dashboard")
def dashboard():
    return HTMLResponse("<html><body><h1>PadhaiSetu dashboard (M5)</h1></body></html>")
