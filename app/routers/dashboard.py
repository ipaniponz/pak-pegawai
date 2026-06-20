from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.auth import require_login, require_login_page
from app.database import get_db
from app.models import Pegawai
from app.services import hitung_dashboard_row
from app.templating import templates

router = APIRouter()


@router.get("/api/dashboard", dependencies=[Depends(require_login)])
def api_dashboard(db: Session = Depends(get_db)):
    pegawai_aktif = db.query(Pegawai).filter(Pegawai.status == "aktif", Pegawai.kategori_jf != "Struktural").order_by(Pegawai.nama).all()
    return [hitung_dashboard_row(db, p) for p in pegawai_aktif]


@router.get("/", dependencies=[Depends(require_login_page)])
def page_dashboard(request: Request, db: Session = Depends(get_db)):
    pegawai_aktif = db.query(Pegawai).filter(Pegawai.status == "aktif").order_by(Pegawai.nama).all()
    rows = []
    for p in pegawai_aktif:
        if p.kategori_jf == "Struktural":
            continue
        rows.append(hitung_dashboard_row(db, p))
    return templates.TemplateResponse("dashboard.html", {"request": request, "rows": rows})
