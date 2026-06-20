"""Logika bisnis dipakai bersama oleh routers JSON (/api/*) dan routers halaman
(Jinja2) -- supaya tidak ada duplikasi antara form HTML dan endpoint API."""

import json
from datetime import date
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.calculations import (
    get_jenjang_pada_tanggal,
    get_riwayat_jenjang_aktif,
    hitung_ak_bulanan,
    hitung_ak_kumulatif,
    hitung_kekurangan,
    hitung_potensi_tahun,
)
from app.models import (
    JenjangReferensi,
    NomorDokumen,
    PenetapanAk,
    PenetapanAkItem,
    Pegawai,
    PengaturanInstansi,
    PredikatKinerjaLog,
    PredikatReferensi,
    RiwayatJenjang,
    RiwayatPangkat,
    TembusanReferensi,
)


def get_pengaturan(db: Session) -> dict:
    return {row.key: row.value for row in db.query(PengaturanInstansi).all()}


def kop_context(data: dict) -> dict:
    """Normalisasi data kop (gambar kop surat utuh) dari `pengaturan` (live,
    dipakai Konversi/Akumulasi) atau `snap` (snapshot PAK) jadi context yang
    sama, supaya partial _kop.html bisa dipakai apa adanya di ketiga dokumen."""
    return {
        "kop_logo": data.get("logo_path"),
    }


def get_nomor_untuk_log(db: Session, predikat_kinerja_log_id: int) -> str | None:
    """Nomor dokumen baru ada setelah PAK benar-benar terbit (lihat 1.4l) --
    sebelum itu, preview Konversi/Akumulasi tampilkan placeholder."""
    item = (
        db.query(PenetapanAkItem)
        .join(PenetapanAk, PenetapanAk.id == PenetapanAkItem.penetapan_ak_id)
        .filter(PenetapanAkItem.predikat_kinerja_log_id == predikat_kinerja_log_id, PenetapanAk.status != "dibatalkan")
        .one_or_none()
    )
    if item is None:
        return None
    return item.penetapan_ak.nomor_dokumen.nomor


class ValidationError(Exception):
    """Kesalahan validasi domain -- router menangkap ini dan mengubahnya jadi HTTP 400."""


# ---------- Pegawai & riwayat ----------


def create_pegawai(db: Session, data: dict) -> Pegawai:
    pegawai = Pegawai(**data)
    db.add(pegawai)
    db.commit()
    return pegawai


def update_pegawai(db: Session, pegawai: Pegawai, data: dict) -> Pegawai:
    for key, value in data.items():
        if value is not None or key in ("nip", "jabatan_fungsional", "substansi"):
            setattr(pegawai, key, value)
    db.commit()
    return pegawai


def add_riwayat_jenjang(db: Session, pegawai_id: int, data: dict) -> RiwayatJenjang:
    aktif = get_riwayat_jenjang_aktif(db, pegawai_id)
    if aktif is not None:
        aktif.tanggal_selesai = data["tanggal_mulai"]
    baru = RiwayatJenjang(pegawai_id=pegawai_id, **data)
    db.add(baru)
    db.commit()
    return baru


def add_riwayat_pangkat(db: Session, pegawai_id: int, data: dict) -> RiwayatPangkat:
    aktif = (
        db.query(RiwayatPangkat)
        .filter(RiwayatPangkat.pegawai_id == pegawai_id, RiwayatPangkat.tanggal_selesai.is_(None))
        .one_or_none()
    )
    if aktif is not None:
        aktif.tanggal_selesai = data["tmt_pangkat"]
    baru = RiwayatPangkat(pegawai_id=pegawai_id, **data)
    db.add(baru)
    db.commit()
    return baru


def set_data_lengkap(db: Session, pegawai: Pegawai) -> Pegawai:
    """Admin set data_lengkap=1 manual setelah field wajib lengkap (lihat 1.4k)."""
    punya_pangkat = (
        db.query(RiwayatPangkat).filter(RiwayatPangkat.pegawai_id == pegawai.id).first()
        is not None
    )
    if not pegawai.nip or not pegawai.tanggal_lahir or not punya_pangkat:
        raise ValidationError(
            "NIP, tanggal lahir, dan minimal 1 riwayat pangkat harus diisi dulu "
            "sebelum data_lengkap bisa diset."
        )
    pegawai.data_lengkap = True
    db.commit()
    return pegawai


# ---------- Predikat kinerja ----------


def input_predikat_kinerja(
    db: Session, pegawai_id: int, tahun: int, bulan: int, predikat_referensi_id: int, actor: str
) -> PredikatKinerjaLog:
    existing = (
        db.query(PredikatKinerjaLog)
        .filter(
            PredikatKinerjaLog.pegawai_id == pegawai_id,
            PredikatKinerjaLog.tahun == tahun,
            PredikatKinerjaLog.bulan == bulan,
            PredikatKinerjaLog.status != "dibatalkan",
        )
        .one_or_none()
    )
    if existing is not None:
        raise ValidationError(f"Sudah ada baris aktif untuk {bulan}/{tahun}.")

    jenjang_row = get_jenjang_pada_tanggal(db, pegawai_id, date(tahun, bulan, 1))
    if jenjang_row is None:
        raise ValidationError("Pegawai tidak punya riwayat_jenjang aktif pada bulan tersebut.")

    predikat = db.get(PredikatReferensi, predikat_referensi_id)
    if predikat is None:
        raise ValidationError("predikat_referensi_id tidak ditemukan.")
    jenjang_ref = db.get(JenjangReferensi, jenjang_row.jenjang_referensi_id)

    ak = hitung_ak_bulanan(float(jenjang_ref.koefisien_ak_tahun), float(predikat.persentase))

    log = PredikatKinerjaLog(
        pegawai_id=pegawai_id,
        tahun=tahun,
        bulan=bulan,
        predikat_referensi_id=predikat_referensi_id,
        jenjang_referensi_id_snapshot=jenjang_row.jenjang_referensi_id,
        koefisien_terpakai=jenjang_ref.koefisien_ak_tahun,
        persentase_terpakai=predikat.persentase,
        ak_terkonversi=Decimal(str(ak)),
        status="draft",
        dibuat_oleh=actor,
    )
    db.add(log)
    db.commit()
    return log


def update_predikat_status(
    db: Session, log: PredikatKinerjaLog, status: str, actor: str, alasan: str | None
) -> PredikatKinerjaLog:
    if status == "disetujui" and log.status != "draft":
        raise ValidationError("Hanya baris berstatus draft yang bisa disetujui.")
    if status == "dibatalkan" and not alasan:
        raise ValidationError("alasan wajib diisi untuk pembatalan.")

    if status == "disetujui":
        log.status = "disetujui"
        log.disetujui_oleh = actor
        log.disetujui_pada = func.now()
    elif status == "dibatalkan":
        log.status = "dibatalkan"
        log.dibatalkan_oleh = actor
        log.dibatalkan_pada = func.now()
        log.alasan_pembatalan = alasan
    db.commit()
    return log


# ---------- Dashboard ----------


def hitung_dashboard_row(db: Session, pegawai: Pegawai) -> dict:
    aktif = get_riwayat_jenjang_aktif(db, pegawai.id)
    if aktif is None:
        return {
            "pegawai_id": pegawai.id,
            "nama": pegawai.nama,
            "jabatan_fungsional": pegawai.jabatan_fungsional,
            "jenjang_aktif": None,
            "ak_kumulatif": None,
            "ak_target_jenjang": None,
            "kekurangan_jenjang": None,
            "keterangan": None,
            "potensi_tahun": None,
        }
    jenjang_ref = db.get(JenjangReferensi, aktif.jenjang_referensi_id)
    ak_kumulatif = hitung_ak_kumulatif(db, pegawai.id)
    kekurangan = hitung_kekurangan(ak_kumulatif, jenjang_ref.ak_kumulatif_minimal)
    skenario = {
        p.nama: p.persentase
        for p in db.query(PredikatReferensi)
        .filter(PredikatReferensi.nama.in_(["Sangat Baik", "Baik", "Butuh Perbaikan"]))
        .all()
    }
    potensi = hitung_potensi_tahun(kekurangan, jenjang_ref.koefisien_ak_tahun, skenario) if skenario else None
    return {
        "pegawai_id": pegawai.id,
        "nama": pegawai.nama,
        "jabatan_fungsional": pegawai.jabatan_fungsional,
        "jenjang_aktif": jenjang_ref.nama_jenjang,
        "ak_kumulatif": ak_kumulatif,
        "ak_target_jenjang": jenjang_ref.ak_kumulatif_minimal,
        "kekurangan_jenjang": kekurangan,
        "keterangan": "Cukup" if (kekurangan is not None and kekurangan <= 0) else (
            "Kekurangan" if kekurangan is not None else "-"
        ),
        "potensi_tahun": potensi,
    }


# ---------- Penetapan AK ----------


def generate_nomor_dokumen(db: Session, pegawai_id: int, tahun: int) -> NomorDokumen:
    """Dibungkus retry untuk cegah nomor kembar kalau dua aksi nyaris bersamaan
    (lihat 1.4l brief)."""
    for _ in range(5):
        max_urutan = (
            db.query(func.max(NomorDokumen.urutan)).filter(NomorDokumen.tahun == tahun).scalar()
            or 0
        )
        urutan = max_urutan + 1
        nomor = f"{urutan}/ROKUM/{tahun}"
        nd = NomorDokumen(nomor=nomor, tahun=tahun, urutan=urutan, pegawai_id=pegawai_id)
        db.add(nd)
        try:
            db.commit()
            return nd
        except IntegrityError:
            db.rollback()
    raise ValidationError("Gagal generate nomor dokumen setelah beberapa percobaan.")


def cek_periode_belum_dipakai(db: Session, predikat_kinerja_log_ids: list[int]) -> None:
    dipakai = (
        db.query(PenetapanAkItem.predikat_kinerja_log_id)
        .join(PenetapanAk, PenetapanAk.id == PenetapanAkItem.penetapan_ak_id)
        .filter(
            PenetapanAkItem.predikat_kinerja_log_id.in_(predikat_kinerja_log_ids),
            PenetapanAk.status != "dibatalkan",
        )
        .all()
    )
    if dipakai:
        ids = ", ".join(str(d[0]) for d in dipakai)
        raise ValidationError(f"Periode (id: {ids}) sudah dipakai di PAK lain yang masih aktif.")


def build_snapshot_data(db: Session, pegawai: Pegawai, penetapan: PenetapanAk, items: list[PredikatKinerjaLog], pengaturan: dict) -> str:
    aktif_jenjang = get_riwayat_jenjang_aktif(db, pegawai.id)
    jenjang_ref = db.get(JenjangReferensi, aktif_jenjang.jenjang_referensi_id) if aktif_jenjang else None
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
    data = {
        "nama": pegawai.nama,
        "nip": pegawai.nip,
        "nomor_karpeg": pegawai.nomor_karpeg,
        "tempat_lahir": pegawai.tempat_lahir,
        "tanggal_lahir": pegawai.tanggal_lahir.isoformat() if pegawai.tanggal_lahir else None,
        "jenis_kelamin": pegawai.jenis_kelamin,
        "pangkat": pangkat_aktif.pangkat if pangkat_aktif else None,
        "golongan_ruang": pangkat_aktif.golongan_ruang if pangkat_aktif else None,
        "tmt_pangkat": pangkat_aktif.tmt_pangkat.isoformat() if pangkat_aktif else None,
        "jabatan_fungsional": pegawai.jabatan_fungsional,
        "jenjang": jenjang_ref.nama_jenjang if jenjang_ref else None,
        "tmt_jabatan": pegawai.tmt_jabatan.isoformat() if pegawai.tmt_jabatan else None,
        "unit_kerja": pegawai.unit_kerja,
        "koefisien_ak_tahun": str(jenjang_ref.koefisien_ak_tahun) if jenjang_ref else None,
        "ak_kumulatif_minimal": str(jenjang_ref.ak_kumulatif_minimal) if jenjang_ref and jenjang_ref.ak_kumulatif_minimal is not None else None,
        "ak_pangkat_minimal": str(jenjang_ref.ak_pangkat_minimal) if jenjang_ref and jenjang_ref.ak_pangkat_minimal is not None else None,
        "pejabat_penilai_nama": penetapan.pejabat_penilai.nama,
        "pejabat_penilai_nip": penetapan.pejabat_penilai.nip,
        "tembusan": [t.isi_tembusan for t in tembusan],
        "instansi": pengaturan.get("instansi"),
        "kota": pengaturan.get("kota"),
        "logo_path": pengaturan.get("logo_path"),
        "rincian_periode": [
            {
                "tahun": it.tahun,
                "bulan": it.bulan,
                "predikat": it.predikat_referensi.nama,
                "persentase": str(it.persentase_terpakai),
                "koefisien": str(it.koefisien_terpakai),
                "ak_terkonversi": str(it.ak_terkonversi),
            }
            for it in items
        ],
    }
    return json.dumps(data, ensure_ascii=False)


def terbitkan_pak(
    db: Session,
    pegawai: Pegawai,
    predikat_kinerja_log_ids: list[int],
    pejabat_penilai_id: int,
    tanggal_penetapan: date,
    ak_dasar: Decimal,
    ak_jf_lama: Decimal,
    ak_penyesuaian: Decimal,
    ak_pendidikan: Decimal,
    kalimat_penutup: str,
    pengaturan: dict,
) -> PenetapanAk:
    if not kalimat_penutup:
        raise ValidationError("kalimat_penutup tidak boleh kosong saat PAK diterbitkan.")
    if not pegawai.data_lengkap:
        raise ValidationError("Data pegawai belum lengkap (data_lengkap=0), PAK tidak bisa diterbitkan.")

    items = (
        db.query(PredikatKinerjaLog)
        .filter(PredikatKinerjaLog.id.in_(predikat_kinerja_log_ids))
        .order_by(PredikatKinerjaLog.tahun, PredikatKinerjaLog.bulan)
        .all()
    )
    if len(items) != len(predikat_kinerja_log_ids):
        raise ValidationError("Sebagian predikat_kinerja_log_ids tidak ditemukan.")
    for it in items:
        if it.pegawai_id != pegawai.id:
            raise ValidationError(f"Periode id={it.id} bukan milik pegawai ini.")
        if it.status != "disetujui":
            raise ValidationError(f"Periode id={it.id} belum berstatus disetujui.")
    cek_periode_belum_dipakai(db, predikat_kinerja_log_ids)

    periode_pertama = (items[0].tahun, items[0].bulan)
    bulan_sebelum = periode_pertama[1] - 1
    tahun_sebelum = periode_pertama[0] if bulan_sebelum >= 1 else periode_pertama[0] - 1
    bulan_sebelum = 12 if bulan_sebelum < 1 else bulan_sebelum

    ak_konversi_sebelum = hitung_ak_kumulatif(db, pegawai.id, sampai_tahun_bulan=(tahun_sebelum, bulan_sebelum)) or Decimal("0")
    sum_periode_ini = sum((Decimal(str(it.ak_terkonversi)) for it in items), Decimal("0"))

    ak_kumulatif_sebelum = ak_dasar + ak_jf_lama + ak_penyesuaian + ak_konversi_sebelum
    ak_kumulatif_sesudah = ak_kumulatif_sebelum + sum_periode_ini + ak_pendidikan

    nomor = generate_nomor_dokumen(db, pegawai.id, tanggal_penetapan.year)

    penetapan = PenetapanAk(
        nomor_dokumen_id=nomor.id,
        pegawai_id=pegawai.id,
        tanggal_penetapan=tanggal_penetapan,
        ak_kumulatif_sebelum=ak_kumulatif_sebelum,
        ak_kumulatif_sesudah=ak_kumulatif_sesudah,
        ak_dasar=ak_dasar,
        ak_jf_lama=ak_jf_lama,
        ak_penyesuaian=ak_penyesuaian,
        ak_pendidikan=ak_pendidikan,
        pejabat_penilai_id=pejabat_penilai_id,
        kalimat_penutup=kalimat_penutup,
        status="terbit",
    )
    db.add(penetapan)
    db.flush()

    for it in items:
        db.add(PenetapanAkItem(penetapan_ak_id=penetapan.id, predikat_kinerja_log_id=it.id))
    db.commit()

    penetapan.snapshot_data = build_snapshot_data(db, pegawai, penetapan, items, pengaturan)
    db.commit()
    return penetapan


def batalkan_pak(db: Session, penetapan: PenetapanAk, alasan: str, actor: str) -> PenetapanAk:
    if not alasan:
        raise ValidationError("alasan wajib diisi untuk pembatalan.")
    penetapan.status = "dibatalkan"
    penetapan.dibatalkan_oleh = actor
    penetapan.dibatalkan_pada = func.now()
    penetapan.alasan_pembatalan = alasan
    db.commit()
    return penetapan
