from datetime import date

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth import require_login, require_login_page, verify_csrf_form
from app.calculations import get_riwayat_jenjang_aktif, hitung_ak_kumulatif
from app.database import get_db
from app.models import JenjangReferensi, Pegawai, PenetapanAk, PredikatKinerjaLog, RiwayatJenjang, RiwayatPangkat
from app.schemas import PegawaiCreate, PegawaiOut, PegawaiUpdate, RiwayatJenjangCreate, RiwayatPangkatCreate
from app.services import ValidationError, add_riwayat_jenjang, add_riwayat_pangkat, create_pegawai, set_data_lengkap, update_pegawai
from app.templating import templates

router = APIRouter()


# ---------- JSON API ----------


@router.get("/api/pegawai", response_model=list[PegawaiOut], dependencies=[Depends(require_login)])
def list_pegawai(status: str | None = None, db: Session = Depends(get_db)):
    q = db.query(Pegawai)
    if status:
        q = q.filter(Pegawai.status == status)
    return q.order_by(Pegawai.nama).all()


@router.get("/api/pegawai/{pegawai_id}", dependencies=[Depends(require_login)])
def get_pegawai(pegawai_id: int, db: Session = Depends(get_db)):
    pegawai = db.get(Pegawai, pegawai_id)
    if pegawai is None:
        raise HTTPException(404, "Pegawai tidak ditemukan")
    ak = hitung_ak_kumulatif(db, pegawai_id)
    aktif = get_riwayat_jenjang_aktif(db, pegawai_id)
    jenjang_nama = None
    if aktif:
        jenjang_ref = db.get(JenjangReferensi, aktif.jenjang_referensi_id)
        jenjang_nama = jenjang_ref.nama_jenjang if jenjang_ref else None
    out = PegawaiOut.model_validate(pegawai).model_dump()
    out["ak_kumulatif"] = ak
    out["jenjang_aktif"] = jenjang_nama
    return out


@router.post("/api/pegawai", response_model=PegawaiOut, dependencies=[Depends(require_login)])
def api_create_pegawai(data: PegawaiCreate, db: Session = Depends(get_db)):
    return create_pegawai(db, data.model_dump())


@router.put("/api/pegawai/{pegawai_id}", response_model=PegawaiOut, dependencies=[Depends(require_login)])
def api_update_pegawai(pegawai_id: int, data: PegawaiUpdate, db: Session = Depends(get_db)):
    pegawai = db.get(Pegawai, pegawai_id)
    if pegawai is None:
        raise HTTPException(404, "Pegawai tidak ditemukan")
    return update_pegawai(db, pegawai, data.model_dump())


@router.post("/api/pegawai/{pegawai_id}/riwayat-jenjang", dependencies=[Depends(require_login)])
def api_add_riwayat_jenjang(pegawai_id: int, data: RiwayatJenjangCreate, db: Session = Depends(get_db)):
    if db.get(Pegawai, pegawai_id) is None:
        raise HTTPException(404, "Pegawai tidak ditemukan")
    return add_riwayat_jenjang(db, pegawai_id, data.model_dump())


@router.post("/api/pegawai/{pegawai_id}/riwayat-pangkat", dependencies=[Depends(require_login)])
def api_add_riwayat_pangkat(pegawai_id: int, data: RiwayatPangkatCreate, db: Session = Depends(get_db)):
    if db.get(Pegawai, pegawai_id) is None:
        raise HTTPException(404, "Pegawai tidak ditemukan")
    return add_riwayat_pangkat(db, pegawai_id, data.model_dump())


@router.patch("/api/pegawai/{pegawai_id}/data-lengkap", dependencies=[Depends(require_login)])
def api_set_data_lengkap(pegawai_id: int, db: Session = Depends(get_db)):
    pegawai = db.get(Pegawai, pegawai_id)
    if pegawai is None:
        raise HTTPException(404, "Pegawai tidak ditemukan")
    try:
        return set_data_lengkap(db, pegawai)
    except ValidationError as e:
        raise HTTPException(400, str(e))


# ---------- Halaman (Jinja2) ----------


@router.get("/pegawai", dependencies=[Depends(require_login_page)])
def page_list_pegawai(request: Request, db: Session = Depends(get_db)):
    pegawai_list = db.query(Pegawai).order_by(Pegawai.nama).all()
    return templates.TemplateResponse("pegawai_list.html", {"request": request, "pegawai_list": pegawai_list})


@router.get("/pegawai/baru", dependencies=[Depends(require_login_page)])
def page_pegawai_baru(request: Request):
    return templates.TemplateResponse("pegawai_form.html", {"request": request, "pegawai": None})


@router.post("/pegawai/baru", dependencies=[Depends(require_login_page), Depends(verify_csrf_form)])
def page_pegawai_baru_submit(
    request: Request,
    nama: str = Form(...),
    kategori_jf: str = Form(...),
    nip: str = Form(""),
    jabatan_fungsional: str = Form(""),
    substansi: str = Form(""),
    status_kepegawaian: str = Form("PNS"),
    unit_kerja: str = Form(""),
    db: Session = Depends(get_db),
):
    pegawai = create_pegawai(
        db,
        {
            "nama": nama,
            "kategori_jf": kategori_jf,
            "nip": nip or None,
            "jabatan_fungsional": jabatan_fungsional or None,
            "substansi": substansi or None,
            "status_kepegawaian": status_kepegawaian,
            "unit_kerja": unit_kerja or None,
        },
    )
    return RedirectResponse(url=f"/pegawai/{pegawai.id}", status_code=303)


@router.get("/pegawai/{pegawai_id}", dependencies=[Depends(require_login_page)])
def page_detail_pegawai(request: Request, pegawai_id: int, db: Session = Depends(get_db)):
    pegawai = db.get(Pegawai, pegawai_id)
    if pegawai is None:
        raise HTTPException(404, "Pegawai tidak ditemukan")
    ak_kumulatif = hitung_ak_kumulatif(db, pegawai_id)
    riwayat_jenjang = (
        db.query(RiwayatJenjang).filter(RiwayatJenjang.pegawai_id == pegawai_id).order_by(RiwayatJenjang.tanggal_mulai).all()
    )
    riwayat_pangkat = (
        db.query(RiwayatPangkat).filter(RiwayatPangkat.pegawai_id == pegawai_id).order_by(RiwayatPangkat.tmt_pangkat).all()
    )
    logs = (
        db.query(PredikatKinerjaLog)
        .filter(PredikatKinerjaLog.pegawai_id == pegawai_id)
        .order_by(PredikatKinerjaLog.tahun.desc(), PredikatKinerjaLog.bulan.desc())
        .all()
    )
    sudah_dipakai_ids = {
        item.predikat_kinerja_log_id
        for pak in db.query(PenetapanAk).filter(PenetapanAk.pegawai_id == pegawai_id, PenetapanAk.status != "dibatalkan")
        for item in pak.items
    }
    jumlah_periode_siap_pak = sum(
        1 for log in logs if log.status == "disetujui" and log.id not in sudah_dipakai_ids
    )
    bisa_terbitkan_pak = jumlah_periode_siap_pak > 0
    return templates.TemplateResponse(
        "pegawai_detail.html",
        {
            "request": request,
            "pegawai": pegawai,
            "ak_kumulatif": ak_kumulatif,
            "riwayat_jenjang": riwayat_jenjang,
            "riwayat_pangkat": riwayat_pangkat,
            "logs": logs,
            "bisa_terbitkan_pak": bisa_terbitkan_pak,
            "jumlah_periode_siap_pak": jumlah_periode_siap_pak,
            "jenjang_list": db.query(JenjangReferensi).order_by(JenjangReferensi.kategori, JenjangReferensi.urutan).all(),
        },
    )


@router.get("/pegawai/{pegawai_id}/edit", dependencies=[Depends(require_login_page)])
def page_edit_pegawai(request: Request, pegawai_id: int, db: Session = Depends(get_db)):
    pegawai = db.get(Pegawai, pegawai_id)
    if pegawai is None:
        raise HTTPException(404, "Pegawai tidak ditemukan")
    return templates.TemplateResponse("pegawai_form.html", {"request": request, "pegawai": pegawai})


@router.post("/pegawai/{pegawai_id}/edit", dependencies=[Depends(require_login_page), Depends(verify_csrf_form)])
def page_edit_pegawai_submit(
    request: Request,
    pegawai_id: int,
    nama: str = Form(...),
    kategori_jf: str = Form(...),
    nip: str = Form(""),
    jabatan_fungsional: str = Form(""),
    substansi: str = Form(""),
    status_kepegawaian: str = Form("PNS"),
    unit_kerja: str = Form(""),
    nomor_karpeg: str = Form(""),
    tempat_lahir: str = Form(""),
    tanggal_lahir: str = Form(""),
    jenis_kelamin: str = Form(""),
    db: Session = Depends(get_db),
):
    pegawai = db.get(Pegawai, pegawai_id)
    if pegawai is None:
        raise HTTPException(404, "Pegawai tidak ditemukan")
    update_pegawai(
        db,
        pegawai,
        {
            "nama": nama,
            "kategori_jf": kategori_jf,
            "nip": nip or None,
            "jabatan_fungsional": jabatan_fungsional or None,
            "substansi": substansi or None,
            "status_kepegawaian": status_kepegawaian,
            "unit_kerja": unit_kerja or None,
            "nomor_karpeg": nomor_karpeg or None,
            "tempat_lahir": tempat_lahir or None,
            "tanggal_lahir": date.fromisoformat(tanggal_lahir) if tanggal_lahir else None,
            "jenis_kelamin": jenis_kelamin or None,
        },
    )
    return RedirectResponse(url=f"/pegawai/{pegawai_id}", status_code=303)


@router.post("/pegawai/{pegawai_id}/riwayat-jenjang", dependencies=[Depends(require_login_page), Depends(verify_csrf_form)])
def page_add_riwayat_jenjang(
    request: Request,
    pegawai_id: int,
    jenjang_referensi_id: int = Form(...),
    tanggal_mulai: str = Form(...),
    ak_awal_jenjang: str = Form("0"),
    sk_referensi: str = Form(""),
    db: Session = Depends(get_db),
):
    add_riwayat_jenjang(
        db,
        pegawai_id,
        {
            "jenjang_referensi_id": jenjang_referensi_id,
            "tanggal_mulai": date.fromisoformat(tanggal_mulai),
            "ak_awal_jenjang": ak_awal_jenjang or "0",
            "sk_referensi": sk_referensi or None,
        },
    )
    return RedirectResponse(url=f"/pegawai/{pegawai_id}", status_code=303)


@router.post("/pegawai/{pegawai_id}/riwayat-pangkat", dependencies=[Depends(require_login_page), Depends(verify_csrf_form)])
def page_add_riwayat_pangkat(
    request: Request,
    pegawai_id: int,
    pangkat: str = Form(...),
    golongan_ruang: str = Form(...),
    tmt_pangkat: str = Form(...),
    sk_referensi: str = Form(""),
    db: Session = Depends(get_db),
):
    add_riwayat_pangkat(
        db,
        pegawai_id,
        {
            "pangkat": pangkat,
            "golongan_ruang": golongan_ruang,
            "tmt_pangkat": date.fromisoformat(tmt_pangkat),
            "sk_referensi": sk_referensi or None,
        },
    )
    return RedirectResponse(url=f"/pegawai/{pegawai_id}", status_code=303)


@router.post("/pegawai/{pegawai_id}/data-lengkap", dependencies=[Depends(require_login_page), Depends(verify_csrf_form)])
def page_set_data_lengkap(request: Request, pegawai_id: int, db: Session = Depends(get_db)):
    pegawai = db.get(Pegawai, pegawai_id)
    if pegawai is None:
        raise HTTPException(404, "Pegawai tidak ditemukan")
    try:
        set_data_lengkap(db, pegawai)
    except ValidationError as e:
        raise HTTPException(400, str(e))
    return RedirectResponse(url=f"/pegawai/{pegawai_id}", status_code=303)
