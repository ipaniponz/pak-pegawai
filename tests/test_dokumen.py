"""Test untuk logika pengelompokan baris Akumulasi AK (lihat _group_baris_akumulasi
di app/routers/dokumen.py) -- harus menghasilkan rentang seperti 'JUNI-DESEMBER'
yang cocok dengan contoh nyata di Format sudah Rapih.xlsx, bukan 1 baris per bulan."""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.calculations import hitung_ak_bulanan
from app.database import Base
from app.models import JenjangReferensi, Pegawai, PredikatKinerjaLog, PredikatReferensi, RiwayatJenjang
from app.routers.dokumen import _group_baris_akumulasi


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def _setup_pegawai(db):
    jenjang = JenjangReferensi(
        kategori="Keahlian", nama_jenjang="Ahli Pertama", golru="III/a, III/b",
        koefisien_ak_tahun=Decimal("12.5"), ak_kumulatif_minimal=Decimal("100"),
        ak_pangkat_minimal=Decimal("50"), urutan=1,
    )
    baik = PredikatReferensi(nama="Baik", persentase=Decimal("1.00"), urutan=2)
    db.add_all([jenjang, baik])
    db.commit()
    pegawai = Pegawai(nama="Test", kategori_jf="Keahlian", status="aktif")
    db.add(pegawai)
    db.commit()
    db.add(RiwayatJenjang(pegawai_id=pegawai.id, jenjang_referensi_id=jenjang.id, tanggal_mulai=date(2020, 1, 1), ak_awal_jenjang=0))
    db.commit()
    return pegawai, jenjang, baik


def _tambah_log(db, pegawai, jenjang, predikat, tahun, bulan):
    ak = hitung_ak_bulanan(float(jenjang.koefisien_ak_tahun), float(predikat.persentase))
    log = PredikatKinerjaLog(
        pegawai_id=pegawai.id, tahun=tahun, bulan=bulan,
        predikat_referensi_id=predikat.id, jenjang_referensi_id_snapshot=jenjang.id,
        koefisien_terpakai=jenjang.koefisien_ak_tahun, persentase_terpakai=predikat.persentase,
        ak_terkonversi=Decimal(str(ak)), status="disetujui", dibuat_oleh="test",
    )
    db.add(log)
    db.commit()
    return log


def test_group_7_plus_3_bulan_sesuai_contoh_nyata(db):
    """Cocok dengan sheet AKUMULASI AK: Jun-Des 2025 (7 bulan) jadi 1 baris,
    Jan-Mar 2026 (3 bulan) jadi 1 baris terpisah (beda tahun)."""
    pegawai, jenjang, baik = _setup_pegawai(db)
    rows = []
    for bulan in range(6, 13):
        rows.append(_tambah_log(db, pegawai, jenjang, baik, 2025, bulan))
    for bulan in range(1, 4):
        rows.append(_tambah_log(db, pegawai, jenjang, baik, 2026, bulan))

    groups = _group_baris_akumulasi(rows)

    assert len(groups) == 2
    assert groups[0]["tahun"] == 2025
    assert groups[0]["bulan_awal"] == 6
    assert groups[0]["bulan_akhir"] == 12
    assert float(groups[0]["ak_total"]) == pytest.approx(7.291666666666667, abs=1e-3)

    assert groups[1]["tahun"] == 2026
    assert groups[1]["bulan_awal"] == 1
    assert groups[1]["bulan_akhir"] == 3
    assert float(groups[1]["ak_total"]) == pytest.approx(3.125, abs=1e-3)


def test_group_predikat_berbeda_tidak_digabung(db):
    pegawai, jenjang, baik = _setup_pegawai(db)
    sangat_baik = PredikatReferensi(nama="Sangat Baik", persentase=Decimal("1.50"), urutan=1)
    db.add(sangat_baik)
    db.commit()

    rows = [
        _tambah_log(db, pegawai, jenjang, baik, 2026, 1),
        _tambah_log(db, pegawai, jenjang, baik, 2026, 2),
        _tambah_log(db, pegawai, jenjang, sangat_baik, 2026, 3),
    ]
    groups = _group_baris_akumulasi(rows)

    assert len(groups) == 2
    assert groups[0]["bulan_awal"] == 1 and groups[0]["bulan_akhir"] == 2
    assert groups[1]["bulan_awal"] == 3 and groups[1]["bulan_akhir"] == 3


def test_group_bulan_terlewat_tidak_digabung(db):
    pegawai, jenjang, baik = _setup_pegawai(db)
    rows = [
        _tambah_log(db, pegawai, jenjang, baik, 2026, 1),
        _tambah_log(db, pegawai, jenjang, baik, 2026, 2),
        _tambah_log(db, pegawai, jenjang, baik, 2026, 5),  # lompat, Mar/Apr kosong
    ]
    groups = _group_baris_akumulasi(rows)

    assert len(groups) == 2
    assert groups[0]["bulan_awal"] == 1 and groups[0]["bulan_akhir"] == 2
    assert groups[1]["bulan_awal"] == 5 and groups[1]["bulan_akhir"] == 5
