import json
from datetime import date, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.auth import require_login_page
from app.calculations import get_riwayat_jenjang_aktif, hitung_kekurangan
from app.database import get_db
from app.models import JenjangReferensi, PenetapanAk, PredikatKinerjaLog, RiwayatPangkat, TembusanReferensi
from app.services import get_nomor_untuk_log, get_pengaturan
from app.templating import templates

router = APIRouter()

BULAN_NAMA = [
    "", "Januari", "Februari", "Maret", "April", "Mei", "Juni",
    "Juli", "Agustus", "September", "Oktober", "November", "Desember",
]


def _konteks_pak_untuk_log(db: Session, log: PredikatKinerjaLog):
    from app.models import PenetapanAkItem

    item = (
        db.query(PenetapanAkItem)
        .join(PenetapanAk, PenetapanAk.id == PenetapanAkItem.penetapan_ak_id)
        .filter(PenetapanAkItem.predikat_kinerja_log_id == log.id, PenetapanAk.status != "dibatalkan")
        .one_or_none()
    )
    return item.penetapan_ak if item else None


def _identitas_pegawai(db: Session, pegawai):
    aktif = get_riwayat_jenjang_aktif(db, pegawai.id)
    jenjang_ref = db.get(JenjangReferensi, aktif.jenjang_referensi_id) if aktif else None
    pangkat_aktif = (
        db.query(RiwayatPangkat)
        .filter(RiwayatPangkat.pegawai_id == pegawai.id, RiwayatPangkat.tanggal_selesai.is_(None))
        .one_or_none()
    )
    tembusan = (
        db.query(TembusanReferensi)
        .filter(TembusanReferensi.jabatan_fungsional == pegawai.jabatan_fungsional)
        .order_by(TembusanReferensi.urutan)
        .all()
    )
    return {
        "pegawai": pegawai,
        "jenjang_ref": jenjang_ref,
        "pangkat_aktif": pangkat_aktif,
        "tembusan": tembusan,
    }


@router.get("/dokumen/konversi-periode/{log_id}/print", dependencies=[Depends(require_login_page)])
def print_konversi_periode(request: Request, log_id: int, db: Session = Depends(get_db)):
    log = db.get(PredikatKinerjaLog, log_id)
    if log is None:
        raise HTTPException(404, "Baris predikat kinerja tidak ditemukan")
    ident = _identitas_pegawai(db, log.pegawai)
    pak = _konteks_pak_untuk_log(db, log)
    pengaturan = get_pengaturan(db)
    return templates.TemplateResponse(
        "dokumen_konversi_periode.html",
        {
            "request": request,
            "log": log,
            "bulan_nama": BULAN_NAMA[log.bulan],
            "pak": pak,
            "pengaturan": pengaturan,
            **ident,
        },
    )


@router.get("/dokumen/akumulasi/{pegawai_id}/print", dependencies=[Depends(require_login_page)])
def print_akumulasi(
    request: Request,
    pegawai_id: int,
    dari_tahun: int,
    dari_bulan: int,
    sampai_tahun: int,
    sampai_bulan: int,
    db: Session = Depends(get_db),
):
    rows = (
        db.query(PredikatKinerjaLog)
        .filter(
            PredikatKinerjaLog.pegawai_id == pegawai_id,
            PredikatKinerjaLog.status == "disetujui",
        )
        .order_by(PredikatKinerjaLog.tahun, PredikatKinerjaLog.bulan)
        .all()
    )
    rows = [
        r for r in rows
        if (dari_tahun, dari_bulan) <= (r.tahun, r.bulan) <= (sampai_tahun, sampai_bulan)
    ]
    if not rows:
        raise HTTPException(404, "Tidak ada baris disetujui dalam rentang tersebut")
    ident = _identitas_pegawai(db, rows[0].pegawai)
    pak = _konteks_pak_untuk_log(db, rows[0])
    total = sum((Decimal(str(r.ak_terkonversi)) for r in rows), Decimal("0"))
    pengaturan = get_pengaturan(db)
    return templates.TemplateResponse(
        "dokumen_akumulasi_ak.html",
        {
            "request": request,
            "rows": rows,
            "bulan_nama": BULAN_NAMA,
            "total": total,
            "pak": pak,
            "pengaturan": pengaturan,
            **ident,
        },
    )


@router.get("/dokumen/pak/{penetapan_id}/print", dependencies=[Depends(require_login_page)])
def print_pak(request: Request, penetapan_id: int, db: Session = Depends(get_db)):
    penetapan = db.get(PenetapanAk, penetapan_id)
    if penetapan is None:
        raise HTTPException(404, "Penetapan AK tidak ditemukan")
    if not penetapan.snapshot_data:
        raise HTTPException(409, "snapshot_data belum diisi -- PAK ini tidak valid untuk dicetak")
    snap = json.loads(penetapan.snapshot_data)

    ambang_pangkat = Decimal(snap["ak_pangkat_minimal"]) if snap.get("ak_pangkat_minimal") else None
    ambang_jenjang = Decimal(snap["ak_kumulatif_minimal"]) if snap.get("ak_kumulatif_minimal") else None
    kekurangan_pangkat = hitung_kekurangan(penetapan.ak_kumulatif_sesudah, ambang_pangkat)
    kekurangan_jenjang = hitung_kekurangan(penetapan.ak_kumulatif_sesudah, ambang_jenjang)

    return templates.TemplateResponse(
        "dokumen_pak.html",
        {
            "request": request,
            "penetapan": penetapan,
            "snap": snap,
            "ambang_pangkat": ambang_pangkat,
            "ambang_jenjang": ambang_jenjang,
            "kekurangan_pangkat": kekurangan_pangkat,
            "kekurangan_jenjang": kekurangan_jenjang,
            "bulan_nama": BULAN_NAMA,
            "now": datetime.now(),
        },
    )
