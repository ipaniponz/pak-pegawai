"""Logika kalkulasi AK (lihat bagian 2 AGENT_BRIEF). Semua persentase predikat
dan koefisien jenjang diterima sebagai parameter dari caller (sudah di-lookup
dari predikat_referensi / jenjang_referensi) -- tidak ada konstanta hardcode
di sini, supaya admin bisa edit angka lewat halaman pengaturan tanpa redeploy
kode (lihat 1.5r/1.5s brief)."""

import math
from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.models import PredikatKinerjaLog, RiwayatJenjang

SKENARIO_POTENSI = ("Sangat Baik", "Baik", "Butuh Perbaikan")


def hitung_ak_bulanan(koefisien_ak_tahun: float, persentase: float) -> float:
    """ak = (koefisien_ak_tahun / 12) * persentase. Satu baris = persis 1 bulan kalender."""
    return (koefisien_ak_tahun / 12) * persentase


def get_riwayat_jenjang_aktif(db: Session, pegawai_id: int) -> Optional[RiwayatJenjang]:
    return (
        db.query(RiwayatJenjang)
        .filter(
            RiwayatJenjang.pegawai_id == pegawai_id,
            RiwayatJenjang.tanggal_selesai.is_(None),
        )
        .one_or_none()
    )


def get_jenjang_pada_tanggal(
    db: Session, pegawai_id: int, tanggal: date
) -> Optional[RiwayatJenjang]:
    """Jenjang yang aktif pada tanggal tertentu -- dipakai untuk menentukan
    jenjang_referensi_id_snapshot otomatis saat admin input predikat kinerja
    bulan tertentu (lihat 1.5t brief)."""
    return (
        db.query(RiwayatJenjang)
        .filter(
            RiwayatJenjang.pegawai_id == pegawai_id,
            RiwayatJenjang.tanggal_mulai <= tanggal,
            or_(
                RiwayatJenjang.tanggal_selesai.is_(None),
                RiwayatJenjang.tanggal_selesai >= tanggal,
            ),
        )
        .one_or_none()
    )


def hitung_ak_kumulatif(
    db: Session,
    pegawai_id: int,
    sampai_tahun_bulan: Optional[tuple[int, int]] = None,
) -> Optional[Decimal]:
    """
    AK_kumulatif = ak_awal_jenjang (dari riwayat_jenjang aktif)
                 + SUM(ak_terkonversi) dari predikat_kinerja_log berstatus 'disetujui',
                   dalam jenjang yang sama dengan riwayat_jenjang aktif saat ini,
                   sampai (tahun, bulan) tertentu (default: bulan ini).

    Return None kalau pegawai tidak punya riwayat_jenjang aktif (mis. kategori
    Struktural) -- caller wajib skip kasus ini, bukan menganggapnya error
    (lihat bagian 8 brief).
    """
    aktif = get_riwayat_jenjang_aktif(db, pegawai_id)
    if aktif is None:
        return None

    if sampai_tahun_bulan is None:
        today = date.today()
        sampai_tahun_bulan = (today.year, today.month)
    tahun_s, bulan_s = sampai_tahun_bulan

    rows = (
        db.query(PredikatKinerjaLog)
        .filter(
            PredikatKinerjaLog.pegawai_id == pegawai_id,
            PredikatKinerjaLog.status == "disetujui",
            PredikatKinerjaLog.jenjang_referensi_id_snapshot == aktif.jenjang_referensi_id,
            or_(
                PredikatKinerjaLog.tahun < tahun_s,
                and_(
                    PredikatKinerjaLog.tahun == tahun_s,
                    PredikatKinerjaLog.bulan <= bulan_s,
                ),
            ),
        )
        .all()
    )
    total = sum((Decimal(str(row.ak_terkonversi)) for row in rows), Decimal("0"))
    return Decimal(str(aktif.ak_awal_jenjang or 0)) + total


def hitung_kekurangan(
    ak_kumulatif: Decimal, ambang: Optional[Decimal]
) -> Optional[Decimal]:
    """Selisih ambang - ak_kumulatif. Positif = kekurangan, negatif = kelebihan.
    None kalau jenjang ini tidak punya ambang (mis. jenjang puncak)."""
    if ambang is None:
        return None
    return Decimal(str(ambang)) - Decimal(str(ak_kumulatif))


def hitung_potensi_tahun(
    kekurangan: Optional[Decimal],
    koefisien_ak_tahun: Decimal,
    skenario_persentase: dict[str, Decimal],
) -> dict[str, Optional[int]]:
    """Estimasi tahun mencukupi untuk beberapa skenario predikat (mengganti
    kolom M/N/O di spreadsheet lama). `skenario_persentase` di-lookup caller
    dari predikat_referensi -- JANGAN hardcode 150/100/75% di sini (lihat 1.4p:
    jangan replikasi bug pembulatan /28.15 dari spreadsheet lama, hitung ulang
    dari koefisien_ak_tahun x persentase langsung)."""
    if kekurangan is None:
        return {label: None for label in skenario_persentase}
    if kekurangan <= 0:
        return {label: 0 for label in skenario_persentase}
    hasil: dict[str, Optional[int]] = {}
    for label, persentase in skenario_persentase.items():
        rate_tahun = Decimal(str(koefisien_ak_tahun)) * Decimal(str(persentase))
        hasil[label] = math.ceil(kekurangan / rate_tahun) if rate_tahun > 0 else None
    return hasil
