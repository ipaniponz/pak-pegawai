import os

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.auth import NotAuthenticatedRedirect
from app.database import Base, engine
from app.routers import auth, dashboard, dokumen, jenjang, pegawai, pengaturan, penetapan, predikat_kinerja, tembusan

app = FastAPI(title="Monitoring & Penetapan Angka Kredit")

secret_key = os.environ.get("SECRET_KEY")
if not secret_key:
    raise RuntimeError(
        "SECRET_KEY belum diset di environment. Jangan hardcode -- set lewat .env "
        "(lihat README) sebelum menjalankan aplikasi."
    )
app.add_middleware(SessionMiddleware, secret_key=secret_key, https_only=False)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

Base.metadata.create_all(bind=engine)


@app.exception_handler(NotAuthenticatedRedirect)
async def _redirect_to_login(request, exc):
    return RedirectResponse(url="/login", status_code=303)


app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(pegawai.router)
app.include_router(jenjang.router)
app.include_router(predikat_kinerja.router)
app.include_router(penetapan.router)
app.include_router(tembusan.router)
app.include_router(pengaturan.router)
app.include_router(dokumen.router)
