from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth import require_login, require_login_page, verify_csrf_form
from app.database import get_db
from app.models import TembusanReferensi
from app.schemas import TembusanReferensiCreate, TembusanReferensiOut
from app.templating import templates

router = APIRouter()


@router.get("/api/tembusan-referensi", response_model=list[TembusanReferensiOut], dependencies=[Depends(require_login)])
def list_tembusan(jabatan_fungsional: str | None = None, db: Session = Depends(get_db)):
    q = db.query(TembusanReferensi)
    if jabatan_fungsional:
        q = q.filter(TembusanReferensi.jabatan_fungsional == jabatan_fungsional)
    return q.order_by(TembusanReferensi.jabatan_fungsional, TembusanReferensi.urutan).all()


@router.post("/api/tembusan-referensi", response_model=TembusanReferensiOut, dependencies=[Depends(require_login)])
def create_tembusan(data: TembusanReferensiCreate, db: Session = Depends(get_db)):
    t = TembusanReferensi(**data.model_dump())
    db.add(t)
    db.commit()
    return t


@router.delete("/api/tembusan-referensi/{tembusan_id}", dependencies=[Depends(require_login)])
def delete_tembusan(tembusan_id: int, db: Session = Depends(get_db)):
    t = db.get(TembusanReferensi, tembusan_id)
    if t is None:
        raise HTTPException(404, "Tembusan tidak ditemukan")
    db.delete(t)
    db.commit()
    return {"ok": True}


@router.get("/pengaturan/tembusan", dependencies=[Depends(require_login_page)])
def page_tembusan(request: Request, db: Session = Depends(get_db)):
    rows = db.query(TembusanReferensi).order_by(TembusanReferensi.jabatan_fungsional, TembusanReferensi.urutan).all()
    return templates.TemplateResponse("pengaturan_tembusan.html", {"request": request, "rows": rows})


@router.post("/pengaturan/tembusan", dependencies=[Depends(require_login_page), Depends(verify_csrf_form)])
def page_tembusan_create(
    request: Request,
    jabatan_fungsional: str = Form(...),
    urutan: int = Form(...),
    isi_tembusan: str = Form(...),
    db: Session = Depends(get_db),
):
    db.add(TembusanReferensi(jabatan_fungsional=jabatan_fungsional, urutan=urutan, isi_tembusan=isi_tembusan))
    db.commit()
    return RedirectResponse(url="/pengaturan/tembusan", status_code=303)


@router.post(
    "/pengaturan/tembusan/{tembusan_id}/hapus",
    dependencies=[Depends(require_login_page), Depends(verify_csrf_form)],
)
def page_tembusan_delete(request: Request, tembusan_id: int, db: Session = Depends(get_db)):
    t = db.get(TembusanReferensi, tembusan_id)
    if t is not None:
        db.delete(t)
        db.commit()
    return RedirectResponse(url="/pengaturan/tembusan", status_code=303)
