from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth import require_login_page, verify_csrf_form
from app.database import get_db
from app.models import KalimatPenutupReferensi, PengaturanInstansi
from app.templating import templates

router = APIRouter()


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
    for key, value in [("instansi", instansi), ("kota", kota), ("instansi_pembina", instansi_pembina)]:
        row = db.get(PengaturanInstansi, key)
        if row is None:
            db.add(PengaturanInstansi(key=key, value=value))
        else:
            row.value = value
    db.commit()
    return RedirectResponse(url="/pengaturan/instansi", status_code=303)
