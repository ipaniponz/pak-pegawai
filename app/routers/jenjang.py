from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth import require_login, require_login_page, verify_csrf_form
from app.database import get_db
from app.models import JenjangReferensi
from app.schemas import JenjangReferensiOut, JenjangReferensiUpdate
from app.templating import templates

router = APIRouter()


@router.get("/api/jenjang-referensi", response_model=list[JenjangReferensiOut], dependencies=[Depends(require_login)])
def list_jenjang_referensi(db: Session = Depends(get_db)):
    return db.query(JenjangReferensi).order_by(JenjangReferensi.kategori, JenjangReferensi.urutan).all()


@router.put("/api/jenjang-referensi/{jenjang_id}", response_model=JenjangReferensiOut, dependencies=[Depends(require_login)])
def update_jenjang_referensi(jenjang_id: int, data: JenjangReferensiUpdate, db: Session = Depends(get_db)):
    jenjang = db.get(JenjangReferensi, jenjang_id)
    if jenjang is None:
        raise HTTPException(404, "Jenjang referensi tidak ditemukan")
    jenjang.koefisien_ak_tahun = data.koefisien_ak_tahun
    jenjang.ak_kumulatif_minimal = data.ak_kumulatif_minimal
    jenjang.ak_pangkat_minimal = data.ak_pangkat_minimal
    db.commit()
    return jenjang


@router.get("/pengaturan/jenjang-referensi", dependencies=[Depends(require_login_page)])
def page_jenjang_referensi(request: Request, db: Session = Depends(get_db)):
    rows = db.query(JenjangReferensi).order_by(JenjangReferensi.kategori, JenjangReferensi.urutan).all()
    return templates.TemplateResponse("pengaturan_jenjang.html", {"request": request, "rows": rows})


@router.post("/pengaturan/jenjang-referensi/{jenjang_id}", dependencies=[Depends(require_login_page), Depends(verify_csrf_form)])
def page_jenjang_referensi_update(
    request: Request,
    jenjang_id: int,
    koefisien_ak_tahun: str = Form(...),
    ak_kumulatif_minimal: str = Form(""),
    ak_pangkat_minimal: str = Form(""),
    db: Session = Depends(get_db),
):
    jenjang = db.get(JenjangReferensi, jenjang_id)
    if jenjang is None:
        raise HTTPException(404, "Jenjang referensi tidak ditemukan")
    jenjang.koefisien_ak_tahun = koefisien_ak_tahun
    jenjang.ak_kumulatif_minimal = ak_kumulatif_minimal or None
    jenjang.ak_pangkat_minimal = ak_pangkat_minimal or None
    db.commit()
    return RedirectResponse(url="/pengaturan/jenjang-referensi", status_code=303)
