from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse

from app.auth import verify_credentials, verify_csrf_form
from app.templating import templates

router = APIRouter(tags=["auth"])


@router.get("/login")
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@router.post("/login")
def login_submit(request: Request, username: str = Form(...), password: str = Form(...)):
    if not verify_credentials(username, password):
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Username atau password salah."},
            status_code=400,
        )
    request.session["user"] = username
    return RedirectResponse(url="/", status_code=303)


@router.post("/logout", dependencies=[Depends(verify_csrf_form)])
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)
