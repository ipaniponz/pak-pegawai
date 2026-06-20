from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth import require_login_page, verify_csrf_form
from app.database import get_db
from app.models import KalimatPenutupReferensi, PejabatPenilai, PengaturanInstansi
from app.templating import templates

router = APIRouter()

UPLOAD_DIR = Path("app/static/uploads")
ALLOWED_LOGO_EXT = {".png", ".jpg", ".jpeg", ".gif", ".svg"}
MAX_LOGO_SIZE = 5 * 1024 * 1024  # 5 MB


def _set_pengaturan(db: Session, key: str, value: str) -> None:
    row = db.get(PengaturanInstansi, key)
    if row is None:
        db.add(PengaturanInstansi(key=key, value=value))
    else:
        row.value = value


@router.get("/pengaturan/pejabat-penilai", dependencies=[Depends(require_login_page)])
def page_pejabat_penilai(request: Request, db: Session = Depends(get_db)):
    rows = db.query(PejabatPenilai).order_by(PejabatPenilai.nama).all()
    return templates.TemplateResponse("pengaturan_pejabat_penilai.html", {"request": request, "rows": rows})


@router.post(
    "/pengaturan/pejabat-penilai",
    dependencies=[Depends(require_login_page), Depends(verify_csrf_form)],
)
def page_pejabat_penilai_create(
    request: Request,
    nama: str = Form(...),
    jabatan: str = Form(...),
    nip: str = Form(""),
    db: Session = Depends(get_db),
):
    db.add(PejabatPenilai(nama=nama, jabatan=jabatan, nip=nip or None))
    db.commit()
    return RedirectResponse(url="/pengaturan/pejabat-penilai", status_code=303)


@router.get("/pengaturan/kalimat-penutup", dependencies=[Depends(require_login_page)])
def page_kalimat_penutup(request: Request, db: Session = Depends(get_db)):
    rows = db.query(KalimatPenutupReferensi).order_by(KalimatPenutupReferensi.kondisi).all()
    return templates.TemplateResponse("pengaturan_kalimat_penutup.html", {"request": request, "rows": rows})


@router.post("/pengaturan/kalimat-penutup", dependencies=[Depends(require_login_page), Depends(verify_csrf_form)])
def page_kalimat_penutup_create(
    request: Request, kondisi: str = Form(...), template: str = Form(...), db: Session = Depends(get_db)
):
    db.add(KalimatPenutupReferensi(kondisi=kondisi, template=template))
    db.commit()
    return RedirectResponse(url="/pengaturan/kalimat-penutup", status_code=303)


@router.post(
    "/pengaturan/kalimat-penutup/{kp_id}",
    dependencies=[Depends(require_login_page), Depends(verify_csrf_form)],
)
def page_kalimat_penutup_update(
    request: Request, kp_id: int, template: str = Form(...), db: Session = Depends(get_db)
):
    kp = db.get(KalimatPenutupReferensi, kp_id)
    if kp is None:
        raise HTTPException(404, "kalimat_penutup_referensi tidak ditemukan")
    kp.template = template
    db.commit()
    return RedirectResponse(url="/pengaturan/kalimat-penutup", status_code=303)


@router.get("/pengaturan/instansi", dependencies=[Depends(require_login_page)])
def page_instansi(request: Request, db: Session = Depends(get_db)):
    rows = {row.key: row.value for row in db.query(PengaturanInstansi).all()}
    return templates.TemplateResponse("pengaturan_instansi.html", {"request": request, "rows": rows})


@router.post("/pengaturan/instansi", dependencies=[Depends(require_login_page), Depends(verify_csrf_form)])
def page_instansi_update(
    request: Request,
    instansi: str = Form(""),
    kota: str = Form(""),
    instansi_pembina: str = Form(""),
    db: Session = Depends(get_db),
):
    for key, value in [
        ("instansi", instansi),
        ("kota", kota),
        ("instansi_pembina", instansi_pembina),
    ]:
        _set_pengaturan(db, key, value)
    db.commit()
    return RedirectResponse(url="/pengaturan/instansi", status_code=303)


@router.post("/pengaturan/instansi/logo", dependencies=[Depends(require_login_page), Depends(verify_csrf_form)])
async def page_instansi_logo_upload(request: Request, logo: UploadFile, db: Session = Depends(get_db)):
    ext = Path(logo.filename or "").suffix.lower()
    if ext not in ALLOWED_LOGO_EXT:
        raise HTTPException(400, f"Tipe file tidak didukung ({ext or 'tanpa ekstensi'}). Pakai PNG/JPG/GIF/SVG.")
    content = await logo.read()
    if len(content) > MAX_LOGO_SIZE:
        raise HTTPException(400, "Ukuran file logo maksimal 5 MB.")

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    dest = UPLOAD_DIR / f"kop_logo{ext}"
    # Hapus file logo lama dengan ekstensi berbeda supaya tidak ada logo "hantu" tersisa.
    for old in UPLOAD_DIR.glob("kop_logo.*"):
        old.unlink(missing_ok=True)
    dest.write_bytes(content)

    _set_pengaturan(db, "logo_path", f"/static/uploads/kop_logo{ext}")
    db.commit()
    return RedirectResponse(url="/pengaturan/instansi", status_code=303)
