from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth import require_login, require_login_page, verify_csrf_form
from app.database import get_db
from app.models import KalimatPenutupReferensi, Pegawai, PejabatPenilai, PenetapanAk, PredikatKinerjaLog
from app.schemas import (
    PejabatPenilaiCreate,
    PejabatPenilaiOut,
    PenetapanAkBatalkan,
    PenetapanAkCreate,
    PenetapanAkOut,
)
from app.services import ValidationError, batalkan_pak, get_pengaturan, terbitkan_pak
from app.templating import templates

router = APIRouter()


# ---------- Pejabat Penilai ----------


@router.get("/api/pejabat-penilai", response_model=list[PejabatPenilaiOut], dependencies=[Depends(require_login)])
def list_pejabat_penilai(db: Session = Depends(get_db)):
    return db.query(PejabatPenilai).order_by(PejabatPenilai.nama).all()


@router.post("/api/pejabat-penilai", response_model=PejabatPenilaiOut, dependencies=[Depends(require_login)])
def create_pejabat_penilai(data: PejabatPenilaiCreate, db: Session = Depends(get_db)):
    pp = PejabatPenilai(**data.model_dump())
    db.add(pp)
    db.commit()
    return pp


# ---------- Penetapan AK (JSON API) ----------


@router.post("/api/pegawai/{pegawai_id}/penetapan-ak", response_model=PenetapanAkOut, dependencies=[Depends(require_login)])
def api_terbitkan_pak(pegawai_id: int, data: PenetapanAkCreate, db: Session = Depends(get_db)):
    pegawai = db.get(Pegawai, pegawai_id)
    if pegawai is None:
        raise HTTPException(404, "Pegawai tidak ditemukan")
    try:
        return terbitkan_pak(
            db,
            pegawai,
            data.predikat_kinerja_log_ids,
            data.pejabat_penilai_id,
            data.tanggal_penetapan,
            data.ak_dasar,
            data.ak_jf_lama,
            data.ak_penyesuaian,
            data.kalimat_penutup,
            get_pengaturan(db),
        )
    except ValidationError as e:
        raise HTTPException(400, str(e))


@router.get("/api/penetapan-ak/{penetapan_id}", response_model=PenetapanAkOut, dependencies=[Depends(require_login)])
def get_penetapan_ak(penetapan_id: int, db: Session = Depends(get_db)):
    penetapan = db.get(PenetapanAk, penetapan_id)
    if penetapan is None:
        raise HTTPException(404, "Penetapan AK tidak ditemukan")
    return penetapan


@router.patch("/api/penetapan-ak/{penetapan_id}/batalkan", dependencies=[Depends(require_login)])
def api_batalkan_pak(penetapan_id: int, data: PenetapanAkBatalkan, db: Session = Depends(get_db)):
    penetapan = db.get(PenetapanAk, penetapan_id)
    if penetapan is None:
        raise HTTPException(404, "Penetapan AK tidak ditemukan")
    try:
        return batalkan_pak(db, penetapan, data.alasan, data.actor)
    except ValidationError as e:
        raise HTTPException(400, str(e))


# ---------- Halaman ----------


@router.get("/pegawai/{pegawai_id}/penetapan-ak/baru", dependencies=[Depends(require_login_page)])
def page_penetapan_baru(request: Request, pegawai_id: int, db: Session = Depends(get_db)):
    pegawai = db.get(Pegawai, pegawai_id)
    if pegawai is None:
        raise HTTPException(404, "Pegawai tidak ditemukan")
    periode_tersedia = (
        db.query(PredikatKinerjaLog)
        .filter(PredikatKinerjaLog.pegawai_id == pegawai_id, PredikatKinerjaLog.status == "disetujui")
        .order_by(PredikatKinerjaLog.tahun, PredikatKinerjaLog.bulan)
        .all()
    )
    sudah_dipakai_ids = {
        item.predikat_kinerja_log_id
        for pak in db.query(PenetapanAk).filter(PenetapanAk.pegawai_id == pegawai_id, PenetapanAk.status != "dibatalkan")
        for item in pak.items
    }
    periode_tersedia = [p for p in periode_tersedia if p.id not in sudah_dipakai_ids]
    pejabat_list = db.query(PejabatPenilai).order_by(PejabatPenilai.nama).all()
    kalimat_default = (
        db.query(KalimatPenutupReferensi)
        .filter(KalimatPenutupReferensi.kondisi == "pengangkatan_cpns_pns")
        .one_or_none()
    )
    kalimat_prefill = ""
    if pegawai.status_kepegawaian == "CPNS" and kalimat_default is not None:
        kalimat_prefill = kalimat_default.template
    return templates.TemplateResponse(
        "penetapan_form.html",
        {
            "request": request,
            "pegawai": pegawai,
            "periode_tersedia": periode_tersedia,
            "pejabat_list": pejabat_list,
            "kalimat_prefill": kalimat_prefill,
            "error": None,
        },
    )


@router.post(
    "/pegawai/{pegawai_id}/penetapan-ak/baru",
    dependencies=[Depends(require_login_page), Depends(verify_csrf_form)],
)
async def page_penetapan_baru_submit(request: Request, pegawai_id: int, db: Session = Depends(get_db)):
    pegawai = db.get(Pegawai, pegawai_id)
    if pegawai is None:
        raise HTTPException(404, "Pegawai tidak ditemukan")
    form = await request.form()
    periode_ids = [int(v) for v in form.getlist("periode_ids")]
    try:
        penetapan = terbitkan_pak(
            db,
            pegawai,
            periode_ids,
            int(form.get("pejabat_penilai_id")),
            date.fromisoformat(form.get("tanggal_penetapan")),
            Decimal(form.get("ak_dasar") or "0"),
            Decimal(form.get("ak_jf_lama") or "0"),
            Decimal(form.get("ak_penyesuaian") or "0"),
            form.get("kalimat_penutup"),
            get_pengaturan(db),
        )
    except ValidationError as e:
        raise HTTPException(400, str(e))
    return RedirectResponse(url=f"/dokumen/pak/{penetapan.id}/print", status_code=303)


@router.post(
    "/penetapan-ak/{penetapan_id}/batalkan",
    dependencies=[Depends(require_login_page), Depends(verify_csrf_form)],
)
def page_batalkan_pak(request: Request, penetapan_id: int, alasan: str = Form(...), db: Session = Depends(get_db)):
    penetapan = db.get(PenetapanAk, penetapan_id)
    if penetapan is None:
        raise HTTPException(404, "Penetapan AK tidak ditemukan")
    try:
        batalkan_pak(db, penetapan, alasan, "admin")
    except ValidationError as e:
        raise HTTPException(400, str(e))
    return RedirectResponse(url=f"/pegawai/{penetapan.pegawai_id}", status_code=303)
