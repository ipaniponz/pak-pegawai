from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ---------- Pegawai ----------


class PegawaiCreate(BaseModel):
    nip: Optional[str] = None
    nama: str
    kategori_jf: str
    jabatan_fungsional: Optional[str] = None
    substansi: Optional[str] = None
    status_kepegawaian: str = "PNS"
    nomor_karpeg: Optional[str] = None
    tempat_lahir: Optional[str] = None
    tanggal_lahir: Optional[date] = None
    jenis_kelamin: Optional[str] = None
    tmt_jabatan: Optional[date] = None
    unit_kerja: Optional[str] = None

    @field_validator("kategori_jf")
    @classmethod
    def validate_kategori_jf(cls, v):
        if v not in ("Keahlian", "Keterampilan", "Struktural"):
            raise ValueError("kategori_jf harus Keahlian/Keterampilan/Struktural")
        return v


class PegawaiUpdate(PegawaiCreate):
    status: Optional[str] = None


class PegawaiOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nip: Optional[str]
    nama: str
    kategori_jf: str
    jabatan_fungsional: Optional[str]
    substansi: Optional[str]
    status: str
    data_lengkap: bool
    status_kepegawaian: str
    nomor_karpeg: Optional[str]
    tempat_lahir: Optional[str]
    tanggal_lahir: Optional[date]
    jenis_kelamin: Optional[str]
    tmt_jabatan: Optional[date]
    unit_kerja: Optional[str]


class PegawaiDetailOut(PegawaiOut):
    ak_kumulatif: Optional[Decimal] = None
    jenjang_aktif: Optional[str] = None


# ---------- Riwayat Jenjang ----------


class RiwayatJenjangCreate(BaseModel):
    jenjang_referensi_id: int
    tanggal_mulai: date
    ak_awal_jenjang: Decimal = Decimal("0")
    sk_referensi: Optional[str] = None


class RiwayatJenjangOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    pegawai_id: int
    jenjang_referensi_id: int
    tanggal_mulai: date
    tanggal_selesai: Optional[date]
    ak_awal_jenjang: Decimal
    sk_referensi: Optional[str]


# ---------- Riwayat Pangkat ----------


class RiwayatPangkatCreate(BaseModel):
    pangkat: str
    golongan_ruang: str
    tmt_pangkat: date
    sk_referensi: Optional[str] = None


class RiwayatPangkatOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    pegawai_id: int
    pangkat: str
    golongan_ruang: str
    tmt_pangkat: date
    tanggal_selesai: Optional[date]
    sk_referensi: Optional[str]


# ---------- Jenjang Referensi ----------


class JenjangReferensiOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kategori: str
    nama_jenjang: str
    golru: str
    koefisien_ak_tahun: Decimal
    ak_kumulatif_minimal: Optional[Decimal]
    ak_pangkat_minimal: Optional[Decimal]
    urutan: int


class JenjangReferensiUpdate(BaseModel):
    koefisien_ak_tahun: Decimal
    ak_kumulatif_minimal: Optional[Decimal] = None
    ak_pangkat_minimal: Optional[Decimal] = None


# ---------- Predikat Referensi ----------


class PredikatReferensiOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nama: str
    persentase: Decimal
    urutan: int


class PredikatReferensiUpdate(BaseModel):
    nama: str
    persentase: Decimal


# ---------- Predikat Kinerja Log ----------


class PredikatKinerjaInput(BaseModel):
    tahun: int
    bulan: int = Field(ge=1, le=12)
    predikat_referensi_id: int


class PredikatKinerjaLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    pegawai_id: int
    tahun: int
    bulan: int
    predikat_referensi_id: int
    jenjang_referensi_id_snapshot: int
    koefisien_terpakai: Decimal
    persentase_terpakai: Decimal
    ak_terkonversi: Decimal
    status: str
    dibuat_oleh: str
    dibuat_pada: Optional[datetime]
    disetujui_oleh: Optional[str]
    disetujui_pada: Optional[datetime]
    dibatalkan_oleh: Optional[str]
    dibatalkan_pada: Optional[datetime]
    alasan_pembatalan: Optional[str]
    catatan: Optional[str]


class PredikatKinerjaStatusUpdate(BaseModel):
    status: str
    alasan: Optional[str] = None
    actor: str = "admin"

    @field_validator("status")
    @classmethod
    def validate_status(cls, v):
        if v not in ("disetujui", "dibatalkan"):
            raise ValueError("status hanya boleh 'disetujui' atau 'dibatalkan'")
        return v


# ---------- Pejabat Penilai ----------


class PejabatPenilaiCreate(BaseModel):
    nama: str
    jabatan: str
    nip: Optional[str] = None


class PejabatPenilaiOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nama: str
    jabatan: str
    nip: Optional[str]


# ---------- Penetapan AK ----------


class PenetapanAkCreate(BaseModel):
    predikat_kinerja_log_ids: list[int]
    pejabat_penilai_id: int
    tanggal_penetapan: date
    ak_dasar: Decimal = Decimal("0")
    ak_jf_lama: Decimal = Decimal("0")
    ak_penyesuaian: Decimal = Decimal("0")
    kalimat_penutup: str


class PenetapanAkBatalkan(BaseModel):
    alasan: str
    actor: str = "admin"


class PenetapanAkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nomor_dokumen_id: int
    pegawai_id: int
    tanggal_penetapan: date
    ak_kumulatif_sebelum: Decimal
    ak_kumulatif_sesudah: Decimal
    ak_dasar: Decimal
    ak_jf_lama: Decimal
    ak_penyesuaian: Decimal
    pejabat_penilai_id: int
    kalimat_penutup: Optional[str]
    status: str


# ---------- Tembusan Referensi ----------


class TembusanReferensiCreate(BaseModel):
    jabatan_fungsional: str
    urutan: int
    isi_tembusan: str


class TembusanReferensiOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    jabatan_fungsional: str
    urutan: int
    isi_tembusan: str


# ---------- Kalimat Penutup Referensi ----------


class KalimatPenutupReferensiCreate(BaseModel):
    kondisi: str
    template: str


class KalimatPenutupReferensiOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kondisi: str
    template: str


# ---------- Dashboard ----------


class DashboardRow(BaseModel):
    pegawai_id: int
    nama: str
    jabatan_fungsional: Optional[str]
    jenjang_aktif: Optional[str]
    ak_kumulatif: Optional[Decimal]
    ak_target_jenjang: Optional[Decimal]
    kekurangan_jenjang: Optional[Decimal]
    keterangan: Optional[str]
    potensi_tahun: Optional[dict[str, Optional[int]]]
