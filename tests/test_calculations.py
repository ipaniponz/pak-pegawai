"""Test case wajib dari AGENT_BRIEF bagian 2.4 -- kalau angka ini tidak cocok,
ada bug di calculations.py, jangan lanjut ke fitur lain."""

from datetime import datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.calculations import hitung_ak_bulanan, hitung_ak_kumulatif, hitung_kekurangan, hitung_potensi_tahun
from app.database import Base
from app.models import JenjangReferensi, Pegawai, PredikatKinerjaLog, PredikatReferensi, RiwayatJenjang


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture()
def ahli_pertama(db):
    j = JenjangReferensi(
        kategori="Keahlian", nama_jenjang="Ahli Pertama", golru="III/a, III/b",
        koefisien_ak_tahun=Decimal("12.5"), ak_kumulatif_minimal=Decimal("100"),
        ak_pangkat_minimal=Decimal("50"), urutan=1,
    )
    db.add(j)
    db.commit()
    return j


@pytest.fixture()
def ahli_madya(db):
    j = JenjangReferensi(
        kategori="Keahlian", nama_jenjang="Ahli Madya", golru="IV/a, IV/b, IV/c",
        koefisien_ak_tahun=Decimal("37.5"), ak_kumulatif_minimal=Decimal("450"),
        ak_pangkat_minimal=Decimal("150"), urutan=3,
    )
    db.add(j)
    db.commit()
    return j


@pytest.fixture()
def predikat_baik(db):
    p = PredikatReferensi(nama="Baik", persentase=Decimal("1.00"), urutan=2)
    db.add(p)
    db.commit()
    return p


def buat_pegawai(db, jenjang, ak_awal=Decimal("0")):
    pegawai = Pegawai(nama="Test Pegawai", kategori_jf="Keahlian", status="aktif")
    db.add(pegawai)
    db.commit()
    db.add(
        RiwayatJenjang(
            pegawai_id=pegawai.id,
            jenjang_referensi_id=jenjang.id,
            tanggal_mulai=datetime(2020, 1, 1).date(),
            ak_awal_jenjang=ak_awal,
        )
    )
    db.commit()
    return pegawai


def tambah_log_bulanan(db, pegawai, jenjang, predikat, tahun, bulan, koefisien, persentase):
    ak = hitung_ak_bulanan(float(koefisien), float(persentase))
    db.add(
        PredikatKinerjaLog(
            pegawai_id=pegawai.id,
            tahun=tahun,
            bulan=bulan,
            predikat_referensi_id=predikat.id,
            jenjang_referensi_id_snapshot=jenjang.id,
            koefisien_terpakai=koefisien,
            persentase_terpakai=persentase,
            ak_terkonversi=Decimal(str(ak)),
            status="disetujui",
            dibuat_oleh="test",
        )
    )
    db.commit()


def test_hitung_ak_bulanan_ahli_madya_sangat_baik():
    assert hitung_ak_bulanan(37.5, 1.5) == pytest.approx(4.6875)


def test_12_bulan_ahli_madya_sangat_baik():
    total = sum(hitung_ak_bulanan(37.5, 1.5) for _ in range(12))
    assert total == pytest.approx(56.25)


def test_12_bulan_ahli_madya_baik():
    total = sum(hitung_ak_bulanan(37.5, 1.0) for _ in range(12))
    assert total == pytest.approx(37.5)


def test_12_bulan_ahli_madya_butuh_perbaikan():
    total = sum(hitung_ak_bulanan(37.5, 0.75) for _ in range(12))
    assert total == pytest.approx(28.125)


def test_7_bulan_ahli_pertama_baik():
    total = sum(hitung_ak_bulanan(12.5, 1.0) for _ in range(7))
    assert total == pytest.approx(7.291666666666667)


def test_3_bulan_ahli_pertama_baik():
    total = sum(hitung_ak_bulanan(12.5, 1.0) for _ in range(3))
    assert total == pytest.approx(3.125)


def test_akumulasi_7_plus_3_bulan_ahli_pertama_baik():
    total = sum(hitung_ak_bulanan(12.5, 1.0) for _ in range(10))
    assert total == pytest.approx(10.416666666666668)


def test_hitung_ak_kumulatif_akumulasi_7_plus_3_bulan(db, ahli_pertama, predikat_baik):
    pegawai = buat_pegawai(db, ahli_pertama)
    for bulan in range(6, 13):  # Jun-Des 2025
        tambah_log_bulanan(db, pegawai, ahli_pertama, predikat_baik, 2025, bulan, Decimal("12.5"), Decimal("1.00"))
    for bulan in range(1, 4):  # Jan-Mar 2026
        tambah_log_bulanan(db, pegawai, ahli_pertama, predikat_baik, 2026, bulan, Decimal("12.5"), Decimal("1.00"))

    sebagian = hitung_ak_kumulatif(db, pegawai.id, sampai_tahun_bulan=(2025, 12))
    assert float(sebagian) == pytest.approx(7.291666666666667, abs=1e-3)

    total = hitung_ak_kumulatif(db, pegawai.id, sampai_tahun_bulan=(2026, 3))
    assert float(total) == pytest.approx(10.416666666666668, abs=1e-3)


def test_hitung_ak_kumulatif_pegawai_tanpa_riwayat_jenjang(db):
    pegawai = Pegawai(nama="Struktural", kategori_jf="Struktural", status="aktif")
    db.add(pegawai)
    db.commit()
    assert hitung_ak_kumulatif(db, pegawai.id) is None


def test_hitung_ak_kumulatif_mengabaikan_jenjang_lama(db, ahli_pertama, ahli_madya, predikat_baik):
    """AK dari jenjang sebelumnya tidak boleh ikut tercampur ke kumulatif jenjang baru
    (lihat catatan filter jenjang di 2.3 brief)."""
    pegawai = buat_pegawai(db, ahli_pertama)
    tambah_log_bulanan(db, pegawai, ahli_pertama, predikat_baik, 2024, 1, Decimal("12.5"), Decimal("1.00"))

    # Naik jenjang ke Ahli Madya: tutup riwayat lama, buka riwayat baru dgn ak_awal_jenjang baru.
    lama = db.query(RiwayatJenjang).filter_by(pegawai_id=pegawai.id).one()
    lama.tanggal_selesai = datetime(2025, 1, 1).date()
    db.add(
        RiwayatJenjang(
            pegawai_id=pegawai.id,
            jenjang_referensi_id=ahli_madya.id,
            tanggal_mulai=datetime(2025, 1, 1).date(),
            ak_awal_jenjang=Decimal("0"),
        )
    )
    db.commit()
    tambah_log_bulanan(db, pegawai, ahli_madya, predikat_baik, 2025, 6, Decimal("37.5"), Decimal("1.00"))

    hasil = hitung_ak_kumulatif(db, pegawai.id, sampai_tahun_bulan=(2025, 12))
    assert float(hasil) == pytest.approx(hitung_ak_bulanan(37.5, 1.0), abs=1e-3)


def test_hitung_kekurangan_dan_potensi_tahun():
    kekurangan = hitung_kekurangan(Decimal("0"), Decimal("450"))
    assert kekurangan == Decimal("450")
    hasil = hitung_potensi_tahun(
        kekurangan,
        Decimal("37.5"),
        {"Sangat Baik": Decimal("1.5"), "Baik": Decimal("1.0"), "Butuh Perbaikan": Decimal("0.75")},
    )
    assert hasil == {"Sangat Baik": 8, "Baik": 12, "Butuh Perbaikan": 16}


def test_hitung_kekurangan_kelebihan_tidak_dipaksa_nol():
    assert hitung_kekurangan(Decimal("108.25"), Decimal("100")) == Decimal("-8.25")
