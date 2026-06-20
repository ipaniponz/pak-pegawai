"""Login dasar + CSRF (lihat 1.4e dan 1.4o brief). Internal 1-admin -- tidak
perlu JWT/OAuth/multi-user, tapi tetap wajib login karena data berisi NIP &
tanggal lahir pegawai."""

import os
import secrets

from fastapi import Header, HTTPException, Request
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"])


class NotAuthenticatedRedirect(Exception):
    """Dilempar oleh require_login_page, ditangkap di main.py jadi redirect ke /login."""


def verify_credentials(username: str, password: str) -> bool:
    admin_username = os.environ["ADMIN_USERNAME"]
    admin_password_hash = os.environ["ADMIN_PASSWORD_HASH"]
    if username != admin_username:
        return False
    return pwd_context.verify(password, admin_password_hash)


def require_login(request: Request) -> None:
    """Dependency untuk endpoint JSON (/api/*) -- 401 polos kalau belum login."""
    if not request.session.get("user"):
        raise HTTPException(status_code=401, detail="Belum login")


def require_login_page(request: Request) -> None:
    """Dependency untuk halaman/dokumen print -- redirect ke /login kalau belum login."""
    if not request.session.get("user"):
        raise NotAuthenticatedRedirect()


def get_csrf_token(request: Request) -> str:
    token = request.session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        request.session["csrf_token"] = token
    return token


def verify_csrf(request: Request, x_csrf_token: str | None = Header(default=None)) -> None:
    """Dipakai endpoint JSON (/api/*) -- token dikirim lewat header X-CSRF-Token."""
    expected = request.session.get("csrf_token")
    if not expected or x_csrf_token != expected:
        raise HTTPException(status_code=400, detail="CSRF token tidak valid atau hilang")


async def verify_csrf_form(request: Request) -> None:
    """Dipakai route halaman (form HTML biasa) -- token dikirim lewat hidden field."""
    form = await request.form()
    token = form.get("csrf_token")
    expected = request.session.get("csrf_token")
    if not expected or token != expected:
        raise HTTPException(status_code=400, detail="CSRF token tidak valid atau hilang")
