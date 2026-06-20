from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth import require_login, require_login_page, verify_csrf_form
from app.calculations import get_riwayat_jenjang_aktif
from app.database import get_db
from app.models import JenjangReferensi, Pegawai, PredikatKinerjaLog, PredikatReferensi
from app.schemas import (
    PredikatKinerjaInput,
    PredikatKinerjaLogOut,
    PredikatKinerjaStatusUpdate,
    PredikatReferensiOut,
    PredikatReferensiUpdate,
)
from app.services import ValidationError, input_predikat_kinerja, update_predikat_status
from app.templating import templates

router = APIRouter()


# ---------- JSON API: predikat kinerja log ----------


@router.get(
    "/api/pegawai/{pegawai_id}/predikat-kinerja",
    response_model=list[PredikatKinerjaLogOut],
    dependencies=[Depends(require_login)],
)
def list_predikat_kinerja(pegawai_id: int, db: Session = Depends(get_db)):
    return (
        db.query(PredikatKinerjaLog)
        .filter(PredikatKinerjaLog.pegawai_id == pegawai_id)
        .order_by(PredikatKinerjaLog.tahun.desc(), PredikatKinerjaLog.bulan.desc())
        .all()
    )


@router.post("/api/pegawai/{pegawai_id}/predikat-kinerja", dependencies=[Depends(require_login)])
def api_input_predikat_kinerja(
    pegawai_id: int,
    data: PredikatKinerjaInput | list[PredikatKinerjaInput],
    db: Session = Depends(get_db),
):
    if db.get(Pegawai, pegawai_id) is None:
        raise HTTPException(404, "Pegawai tidak ditemukan")
    items = data if isinstance(data, list) else [data]
    hasil = []
    try:
        for item in items:
            hasil.append(
                input_predikat_kinerja(
                    db, pegawai_id, item.tahun, item.bulan, item.predikat_referensi_id, actor="admin"
                )
            )
    except ValidationError as e:
        raise HTTPException(400, str(e))
    return hasil


@router.patch("/api/predikat-kinerja/{log_id}/status", dependencies=[Depends(require_login)])
def api_update_status(log_id: int, data: PredikatKinerjaStatusUpdate, db: Session = Depends(get_db)):
    log = db.get(PredikatKinerjaLog, log_id)
    if log is None:
        raise HTTPException(404, "Baris predikat kinerja tidak ditemukan")
    try:
        return update_predikat_status(db, log, data.status, data.actor, data.alasan)
    except ValidationError as e:
        raise HTTPException(400, str(e))


# ---------- JSON API: predikat referensi (lihat 1.5s) ----------


@router.get("/api/predikat-referensi", response_model=list[PredikatReferensiOut], dependencies=[Depends(require_login)])
def list_predikat_referensi(db: Session = Depends(get_db)):
    return db.query(PredikatReferensi).order_by(PredikatReferensi.urutan).all()


@router.put("/api/predikat-referensi/{pr_id}", response_model=PredikatReferensiOut, dependencies=[Depends(require_login)])
def update_predikat_referensi(pr_id: int, data: PredikatReferensiUpdate, db: Session = Depends(get_db)):
    pr = db.get(PredikatReferensi, pr_id)
    if pr is None:
        raise HTTPException(404, "predikat_referensi tidak ditemukan")
    pr.nama = data.nama
    pr.persentase = data.persentase
    db.commit()
    return pr


# ---------- Halaman ----------


@router.get("/pegawai/{pegawai_id}/predikat-kinerja/baru", dependencies=[Depends(require_login_page)])
def page_predikat_kinerja_baru(request: Request, pegawai_id: int, db: Session = Depends(get_db)):
    pegawai = db.get(Pegawai, pegawai_id)
    if pegawai is None:
        raise HTTPException(404, "Pegawai tidak ditemukan")
    predikat_list = db.query(PredikatReferensi).order_by(PredikatReferensi.urutan).all()
    aktif = get_riwayat_jenjang_aktif(db, pegawai_id)
    koefisien_aktif = None
    if aktif:
        jenjang_ref = db.get(JenjangReferensi, aktif.jenjang_referensi_id)
        koefisien_aktif = jenjang_ref.koefisien_ak_tahun if jenjang_ref else None
    return templates.TemplateResponse(
        "predikat_kinerja_form.html",
        {
            "request": request,
            "pegawai": pegawai,
            "predikat_list": predikat_list,
            "koefisien_aktif": koefisien_aktif,
            "error": None,
        },
    )


@router.post(
    "/pegawai/{pegawai_id}/predikat-kinerja/baru",
    dependencies=[Depends(require_login_page), Depends(verify_csrf_form)],
)
async def page_predikat_kinerja_baru_submit(request: Request, pegawai_id: int, db: Session = Depends(get_db)):
    pegawai = db.get(Pegawai, pegawai_id)
    if pegawai is None:
        raise HTTPException(404, "Pegawai tidak ditemukan")
    form = await request.form()
    mode = form.get("mode", "single")
    entries = []
    if mode == "batch":
        tahun = int(form.get("tahun_batch"))
        for bulan in range(1, 13):
            predikat_id = form.get(f"predikat_bulan_{bulan}")
            if predikat_id:
                entries.append((tahun, bulan, int(predikat_id)))
    else:
        entries.append((int(form.get("tahun")), int(form.get("bulan")), int(form.get("predikat_referensi_id"))))

    try:
        for tahun, bulan, predikat_id in entries:
            input_predikat_kinerja(db, pegawai_id, tahun, bulan, predikat_id, actor="admin")
    except ValidationError as e:
        predikat_list = db.query(PredikatReferensi).order_by(PredikatReferensi.urutan).all()
        aktif = get_riwayat_jenjang_aktif(db, pegawai_id)
        koefisien_aktif = None
        if aktif:
            jenjang_ref = db.get(JenjangReferensi, aktif.jenjang_referensi_id)
            koefisien_aktif = jenjang_ref.koefisien_ak_tahun if jenjang_ref else None
        return templates.TemplateResponse(
            "predikat_kinerja_form.html",
            {
                "request": request,
                "pegawai": pegawai,
                "predikat_list": predikat_list,
                "koefisien_aktif": koefisien_aktif,
                "error": str(e),
            },
            status_code=400,
        )
    return RedirectResponse(url=f"/pegawai/{pegawai_id}", status_code=303)


@router.post("/predikat-kinerja/{log_id}/status", dependencies=[Depends(require_login_page), Depends(verify_csrf_form)])
def page_update_status(
    request: Request,
    log_id: int,
    status: str = Form(...),
    alasan: str = Form(""),
    db: Session = Depends(get_db),
):
    log = db.get(PredikatKinerjaLog, log_id)
    if log is None:
        raise HTTPException(404, "Baris predikat kinerja tidak ditemukan")
    try:
        update_predikat_status(db, log, status, "admin", alasan or None)
    except ValidationError as e:
        raise HTTPException(400, str(e))
    return RedirectResponse(url=f"/pegawai/{log.pegawai_id}", status_code=303)


@router.get("/pengaturan/predikat-kinerja", dependencies=[Depends(require_login_page)])
def page_pengaturan_predikat(request: Request, db: Session = Depends(get_db)):
    rows = db.query(PredikatReferensi).order_by(PredikatReferensi.urutan).all()
    return templates.TemplateResponse("pengaturan_predikat.html", {"request": request, "rows": rows})


@router.post(
    "/pengaturan/predikat-kinerja/{pr_id}",
    dependencies=[Depends(require_login_page), Depends(verify_csrf_form)],
)
def page_pengaturan_predikat_update(
    request: Request, pr_id: int, nama: str = Form(...), persentase: str = Form(...), db: Session = Depends(get_db)
):
    pr = db.get(PredikatReferensi, pr_id)
    if pr is None:
        raise HTTPException(404, "predikat_referensi tidak ditemukan")
    pr.nama = nama
    pr.persentase = persentase
    db.commit()
    return RedirectResponse(url="/pengaturan/predikat-kinerja", status_code=303)
