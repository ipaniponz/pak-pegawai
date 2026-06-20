from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    event,
    text,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


@event.listens_for(Engine, "connect")
def _enable_sqlite_fk(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


class JenjangReferensi(Base):
    __tablename__ = "jenjang_referensi"

    id = Column(Integer, primary_key=True)
    kategori = Column(String, nullable=False)
    nama_jenjang = Column(String, nullable=False)
    golru = Column(String, nullable=False)
    koefisien_ak_tahun = Column(Numeric(6, 3), nullable=False)
    ak_kumulatif_minimal = Column(Numeric(6, 2))
    ak_pangkat_minimal = Column(Numeric(6, 2))
    urutan = Column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint("kategori", "nama_jenjang"),
        CheckConstraint("kategori IN ('Keahlian','Keterampilan')"),
    )


class Pegawai(Base):
    __tablename__ = "pegawai"

    id = Column(Integer, primary_key=True)
    nip = Column(String, unique=True)
    nama = Column(String, nullable=False)
    kategori_jf = Column(String, nullable=False)
    jabatan_fungsional = Column(String)
    substansi = Column(String)
    status = Column(String, nullable=False, default="aktif")
    data_lengkap = Column(Boolean, nullable=False, default=False)
    status_kepegawaian = Column(String, nullable=False, default="PNS")
    nomor_karpeg = Column(String)
    tempat_lahir = Column(String)
    tanggal_lahir = Column(Date)
    jenis_kelamin = Column(String)
    tmt_jabatan = Column(Date)
    unit_kerja = Column(String)
    created_at = Column(DateTime, server_default=func.now())

    riwayat_jenjang = relationship(
        "RiwayatJenjang", back_populates="pegawai", order_by="RiwayatJenjang.tanggal_mulai"
    )
    riwayat_pangkat = relationship(
        "RiwayatPangkat", back_populates="pegawai", order_by="RiwayatPangkat.tmt_pangkat"
    )
    predikat_kinerja_log = relationship("PredikatKinerjaLog", back_populates="pegawai")

    __table_args__ = (
        CheckConstraint("kategori_jf IN ('Keahlian','Keterampilan','Struktural')"),
        CheckConstraint("status IN ('aktif','non-aktif')"),
        CheckConstraint("status_kepegawaian IN ('CPNS','PNS')"),
    )


class RiwayatJenjang(Base):
    __tablename__ = "riwayat_jenjang"

    id = Column(Integer, primary_key=True)
    pegawai_id = Column(Integer, ForeignKey("pegawai.id"), nullable=False)
    jenjang_referensi_id = Column(Integer, ForeignKey("jenjang_referensi.id"), nullable=False)
    tanggal_mulai = Column(Date, nullable=False)
    tanggal_selesai = Column(Date)  # NULL = jenjang aktif saat ini
    ak_awal_jenjang = Column(Numeric(12, 6), default=0)
    sk_referensi = Column(Text)

    pegawai = relationship("Pegawai", back_populates="riwayat_jenjang")
    jenjang_referensi = relationship("JenjangReferensi")


class RiwayatPangkat(Base):
    """Append-only, sama prinsipnya dengan riwayat_jenjang (lihat 1.3a brief)."""

    __tablename__ = "riwayat_pangkat"

    id = Column(Integer, primary_key=True)
    pegawai_id = Column(Integer, ForeignKey("pegawai.id"), nullable=False)
    pangkat = Column(String, nullable=False)
    golongan_ruang = Column(String, nullable=False)
    tmt_pangkat = Column(Date, nullable=False)
    tanggal_selesai = Column(Date)  # NULL = pangkat aktif saat ini
    sk_referensi = Column(Text)

    pegawai = relationship("Pegawai", back_populates="riwayat_pangkat")


class PredikatReferensi(Base):
    __tablename__ = "predikat_referensi"

    id = Column(Integer, primary_key=True)
    nama = Column(String, unique=True, nullable=False)
    persentase = Column(Numeric(4, 2), nullable=False)
    urutan = Column(Integer, nullable=False)


class PredikatKinerjaLog(Base):
    """Unit atomik = 1 bulan kalender (lihat 1.5t brief). Koefisien & persentase
    di-snapshot saat input supaya histori tetap konsisten walau predikat_referensi/
    jenjang_referensi diedit admin di kemudian hari (lihat 1.5r/1.5s)."""

    __tablename__ = "predikat_kinerja_log"

    id = Column(Integer, primary_key=True)
    pegawai_id = Column(Integer, ForeignKey("pegawai.id"), nullable=False)
    tahun = Column(Integer, nullable=False)
    bulan = Column(Integer, nullable=False)
    predikat_referensi_id = Column(Integer, ForeignKey("predikat_referensi.id"), nullable=False)
    jenjang_referensi_id_snapshot = Column(
        Integer, ForeignKey("jenjang_referensi.id"), nullable=False
    )
    koefisien_terpakai = Column(Numeric(6, 3), nullable=False)
    persentase_terpakai = Column(Numeric(4, 2), nullable=False)
    # Skala diperlebar dari NUMERIC(8,3) di rancangan awal -- 8,3 membuat SQLite
    # membulatkan tiap baris bulanan ke 3 desimal sebelum dijumlahkan, sehingga
    # akumulasi 7+ baris meleset dari angka contoh nyata di brief 2.4 (7.294
    # bukan 7.292). Presisi penuh disimpan di sini; pembulatan 3 desimal hanya
    # di lapisan tampilan (lihat catatan "Kebijakan pembulatan tampilan" bagian 8).
    ak_terkonversi = Column(Numeric(12, 6), nullable=False)
    status = Column(String, nullable=False, default="draft")
    dibuat_oleh = Column(String, nullable=False)
    dibuat_pada = Column(DateTime, server_default=func.now())
    disetujui_oleh = Column(String)
    disetujui_pada = Column(DateTime)
    dibatalkan_oleh = Column(String)
    dibatalkan_pada = Column(DateTime)
    alasan_pembatalan = Column(Text)
    catatan = Column(Text)

    pegawai = relationship("Pegawai", back_populates="predikat_kinerja_log")
    predikat_referensi = relationship("PredikatReferensi")
    jenjang_referensi_snapshot = relationship("JenjangReferensi")

    __table_args__ = (
        CheckConstraint("bulan BETWEEN 1 AND 12"),
        CheckConstraint("status IN ('draft','disetujui','dibatalkan')"),
        Index(
            "uq_bulan_aktif",
            "pegawai_id",
            "tahun",
            "bulan",
            unique=True,
            sqlite_where=text("status != 'dibatalkan'"),
        ),
    )


class NomorDokumen(Base):
    """Satu nomor dipakai bersama oleh Konversi/Akumulasi/PAK dalam 1 batch
    penilaian (lihat 1.3b brief). Digenerate saat PAK benar-benar terbit,
    bukan saat preview (lihat 1.4l)."""

    __tablename__ = "nomor_dokumen"

    id = Column(Integer, primary_key=True)
    nomor = Column(String, unique=True, nullable=False)
    tahun = Column(Integer, nullable=False)
    urutan = Column(Integer, nullable=False)
    pegawai_id = Column(Integer, ForeignKey("pegawai.id"), nullable=False)
    dibuat_pada = Column(DateTime, server_default=func.now())


class PejabatPenilai(Base):
    __tablename__ = "pejabat_penilai"

    id = Column(Integer, primary_key=True)
    nama = Column(String, nullable=False)
    jabatan = Column(String, nullable=False)
    nip = Column(String)


class PenetapanAk(Base):
    __tablename__ = "penetapan_ak"

    id = Column(Integer, primary_key=True)
    nomor_dokumen_id = Column(Integer, ForeignKey("nomor_dokumen.id"), nullable=False)
    pegawai_id = Column(Integer, ForeignKey("pegawai.id"), nullable=False)
    tanggal_penetapan = Column(Date, nullable=False)
    ak_kumulatif_sebelum = Column(Numeric(12, 6), nullable=False)
    ak_kumulatif_sesudah = Column(Numeric(12, 6), nullable=False)
    ak_dasar = Column(Numeric(12, 6), nullable=False, default=0)
    ak_jf_lama = Column(Numeric(12, 6), nullable=False, default=0)
    ak_penyesuaian = Column(Numeric(12, 6), nullable=False, default=0)
    pejabat_penilai_id = Column(Integer, ForeignKey("pejabat_penilai.id"), nullable=False)
    kalimat_penutup = Column(Text)
    file_pdf_path = Column(String)
    status = Column(String, nullable=False, default="terbit")
    snapshot_data = Column(Text)  # JSON, diisi sekali saat status='terbit' (lihat 1.4g)
    dibatalkan_oleh = Column(String)
    dibatalkan_pada = Column(DateTime)
    alasan_pembatalan = Column(Text)
    created_at = Column(DateTime, server_default=func.now())

    nomor_dokumen = relationship("NomorDokumen")
    pegawai = relationship("Pegawai")
    pejabat_penilai = relationship("PejabatPenilai")
    items = relationship("PenetapanAkItem", back_populates="penetapan_ak")

    __table_args__ = (CheckConstraint("status IN ('terbit','dibatalkan')"),)


class PenetapanAkItem(Base):
    __tablename__ = "penetapan_ak_items"

    id = Column(Integer, primary_key=True)
    penetapan_ak_id = Column(Integer, ForeignKey("penetapan_ak.id"), nullable=False)
    predikat_kinerja_log_id = Column(
        Integer, ForeignKey("predikat_kinerja_log.id"), nullable=False
    )

    penetapan_ak = relationship("PenetapanAk", back_populates="items")
    predikat_kinerja_log = relationship("PredikatKinerjaLog")

    # Catatan (lihat 1.3d brief): TIDAK pakai UniqueConstraint biasa di sini --
    # itu akan mengunci predikat_kinerja_log_id permanen walau PAK induknya
    # dibatalkan. SQLite tidak mendukung partial unique index lintas tabel induk,
    # jadi validasi "periode belum dipakai PAK aktif" dilakukan di application
    # layer (routers/penetapan.py), bukan di constraint DB.


class TembusanReferensi(Base):
    __tablename__ = "tembusan_referensi"

    id = Column(Integer, primary_key=True)
    jabatan_fungsional = Column(String, nullable=False)
    urutan = Column(Integer, nullable=False)
    isi_tembusan = Column(String, nullable=False)


class KalimatPenutupReferensi(Base):
    __tablename__ = "kalimat_penutup_referensi"

    id = Column(Integer, primary_key=True)
    kondisi = Column(String, unique=True, nullable=False)
    template = Column(Text, nullable=False)


class PengaturanInstansi(Base):
    """Key-value config kecil: instansi, kota, instansi_pembina, dst.
    Diisi lewat halaman pengaturan, bukan diketik ulang di setiap dokumen."""

    __tablename__ = "pengaturan_instansi"

    key = Column(String, primary_key=True)
    value = Column(String)
