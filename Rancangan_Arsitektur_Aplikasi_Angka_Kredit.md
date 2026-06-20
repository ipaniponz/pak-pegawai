# Rancangan Arsitektur — Aplikasi Monitoring & Penetapan Angka Kredit (AK)
**Biro Hukum — Internal, single-admin**
Versi 1.0

---

## 1. Latar Belakang & Masalah yang Dipecahkan

Spreadsheet saat ini menyimpan **nilai akhir** (Nilai PAK 2024, Nilai 2025, dst.) di sel yang **ditimpa ulang (replace)** setiap kali ada periode baru. Ini punya tiga risiko struktural:

1. **Tidak ada riwayat (no audit trail)** — begitu nilai lama ditimpa, tidak ada jejak siapa input, kapan, dan predikat kinerja apa yang jadi dasarnya.
2. **Rentan human error tanpa validasi** — contoh nyata yang saya temukan: sel `Nilai PAK 2024` milik salah satu pegawai (Polaris Siregar) berisi teks `"Belum Dihitung"` bukan angka, sehingga formula pengurangan menghasilkan `#VALUE!`. Tidak ada yang mencegah ini terjadi di Excel.
3. **Single source of truth ganda** — angka kredit kumulatif dan riwayat predikat kinerja tercampur jadi satu angka di satu sel, padahal seharusnya angka kumulatif itu **hasil hitung**, bukan input manual.

**Prinsip desain yang menjawab ini:**

> **Jangan pernah menyimpan angka kredit kumulatif sebagai kolom yang di-edit langsung. Simpan log periode (append-only), lalu angka kumulatif selalu dihitung (computed) dari log tersebut.**

Dengan begitu, kalau ada salah input di periode tertentu, kita cukup koreksi/batalkan baris log itu (dengan jejak siapa & kapan) — bukan mengubah angka akhir secara diam-diam.

---

## 2. Skema Database (ERD)

```
┌──────────────────────┐       ┌────────────────────────────┐
│  pegawai              │       │  jenjang_referensi          │
├──────────────────────┤       ├────────────────────────────┤
│ id (PK)               │       │ id (PK)                     │
│ nip                   │       │ kategori (Keahlian/         │
│ nama                  │       │   Keterampilan)             │
│ kategori_jf            │◄─────┤ nama_jenjang (Ahli Pertama,  │
│  (Keahlian/Keterampilan)│      │   Pemula, dst.)             │
│ jabatan_fungsional     │       │ golru                       │
│ substansi              │       │ koefisien_ak_tahun          │
│   (Perancang PUU /     │       │ ak_kumulatif_minimal        │
│    Analis Hukum / dst.)│       │ urutan (untuk next-jenjang) │
│ status (aktif/non-aktif)│      └────────────────────────────┘
└──────────┬────────────┘                  ▲
           │                                │ FK referensi
           │ 1                              │
           │                                │
           │ N                              │
┌──────────▼────────────────────┐  ┌────────┴────────────────────┐
│  riwayat_jenjang                │  │  predikat_kinerja_log         │
├────────────────────────────────┤  ├──────────────────────────────┤
│ id (PK)                         │  │ id (PK)                       │
│ pegawai_id (FK)                 │  │ pegawai_id (FK)                │
│ jenjang_referensi_id (FK)       │  │ periode_mulai (DATE)           │
│ tanggal_mulai                   │  │ periode_akhir (DATE)           │
│ tanggal_selesai (NULL=aktif)    │  │ predikat                       │
│ ak_awal_jenjang (saat naik)     │  │   (Sangat Baik/Baik/           │
│ sk_referensi                    │  │    Butuh Perbaikan/           │
└────────────────────────────────┘  │    Kurang/Sangat Kurang)      │
           ▲                        │ ak_terkonversi (computed,      │
           │                        │   = koefisien × persentase)    │
           │                        │ status                         │
           │                        │   (draft/disetujui/dibatalkan) │
           │                        │ dibuat_oleh                    │
           │                        │ dibuat_pada (timestamp)         │
           │                        │ catatan                        │
           │                        └──────────────┬─────────────────┘
           │                                       │
           │                                       │ 1
┌──────────┴────────────────────┐                  │ N
│  pejabat_penilai                │       ┌─────────▼────────────────┐
├────────────────────────────────┤       │  penetapan_ak (dokumen)    │
│ id (PK)                         │       ├──────────────────────────┤
│ nama                            │       │ id (PK)                   │
│ jabatan                         │       │ nomor_pak                 │
│ nip                             │       │ pegawai_id (FK)            │
└────────────────────────────────┘       │ tanggal_penetapan          │
           ▲                             │ periode_dicakup            │
           │                             │   (FK -> predikat_kinerja_  │
           └─────────────────────────────┤    log, bisa multi-baris   │
                                          │    via tabel pivot)        │
                                          │ ak_kumulatif_sebelum        │
                                          │   (snapshot, bukan live)   │
                                          │ ak_kumulatif_sesudah        │
                                          │   (snapshot, bukan live)   │
                                          │ pejabat_penilai_id (FK)     │
                                          │ file_pdf_path               │
                                          │ file_docx_path              │
                                          │ status                      │
                                          │   (terbit/dibatalkan)       │
                                          └────────────────────────────┘
```

### Tabel pivot pendukung
```
penetapan_ak_items
  id (PK)
  penetapan_ak_id (FK)
  predikat_kinerja_log_id (FK)
```
Satu dokumen PAK bisa mencakup beberapa periode (misal kuartal Jan-Mar + Apr-Jun) — tabel pivot ini yang menjaga keterkaitannya, sekaligus mencegah satu periode dipakai dobel di dua dokumen PAK berbeda (lewat UNIQUE constraint).

### DDL referensi (PostgreSQL/SQLite-compatible)

```sql
CREATE TABLE jenjang_referensi (
    id SERIAL PRIMARY KEY,
    kategori TEXT NOT NULL CHECK (kategori IN ('Keahlian','Keterampilan')),
    nama_jenjang TEXT NOT NULL,
    golru TEXT NOT NULL,
    koefisien_ak_tahun NUMERIC(6,3) NOT NULL,
    ak_kumulatif_minimal NUMERIC(6,2),
    urutan INT NOT NULL,
    UNIQUE (kategori, nama_jenjang)
);

CREATE TABLE pegawai (
    id SERIAL PRIMARY KEY,
    nip TEXT UNIQUE NOT NULL,
    nama TEXT NOT NULL,
    kategori_jf TEXT NOT NULL CHECK (kategori_jf IN ('Keahlian','Keterampilan','Struktural')),
    jabatan_fungsional TEXT,
    substansi TEXT,
    status TEXT NOT NULL DEFAULT 'aktif' CHECK (status IN ('aktif','non-aktif')),
    created_at TIMESTAMP DEFAULT now()
);

CREATE TABLE riwayat_jenjang (
    id SERIAL PRIMARY KEY,
    pegawai_id INT NOT NULL REFERENCES pegawai(id),
    jenjang_referensi_id INT NOT NULL REFERENCES jenjang_referensi(id),
    tanggal_mulai DATE NOT NULL,
    tanggal_selesai DATE,                 -- NULL = jenjang aktif saat ini
    ak_awal_jenjang NUMERIC(8,3) DEFAULT 0,
    sk_referensi TEXT
);
-- Constraint aplikasi: hanya 1 baris per pegawai dengan tanggal_selesai IS NULL

CREATE TABLE predikat_kinerja_log (
    id SERIAL PRIMARY KEY,
    pegawai_id INT NOT NULL REFERENCES pegawai(id),
    periode_mulai DATE NOT NULL,
    periode_akhir DATE NOT NULL,
    predikat TEXT NOT NULL CHECK (predikat IN
        ('Sangat Baik','Baik','Butuh Perbaikan','Kurang','Sangat Kurang')),
    ak_terkonversi NUMERIC(8,3) NOT NULL,  -- dihitung di application layer, disimpan untuk histori
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','disetujui','dibatalkan')),
    dibuat_oleh TEXT NOT NULL,
    dibuat_pada TIMESTAMP DEFAULT now(),
    catatan TEXT,
    UNIQUE (pegawai_id, periode_mulai, periode_akhir)  -- cegah input dobel periode yg sama
);

CREATE TABLE pejabat_penilai (
    id SERIAL PRIMARY KEY,
    nama TEXT NOT NULL,
    jabatan TEXT NOT NULL,
    nip TEXT
);

CREATE TABLE penetapan_ak (
    id SERIAL PRIMARY KEY,
    nomor_pak TEXT UNIQUE NOT NULL,
    pegawai_id INT NOT NULL REFERENCES pegawai(id),
    tanggal_penetapan DATE NOT NULL,
    ak_kumulatif_sebelum NUMERIC(8,3) NOT NULL,   -- snapshot, BUKAN live reference
    ak_kumulatif_sesudah NUMERIC(8,3) NOT NULL,   -- snapshot, BUKAN live reference
    pejabat_penilai_id INT NOT NULL REFERENCES pejabat_penilai(id),
    file_pdf_path TEXT,   -- hasil "Save as PDF" manual dari render HTML (lihat bagian 6b)
    status TEXT NOT NULL DEFAULT 'terbit' CHECK (status IN ('terbit','dibatalkan')),
    created_at TIMESTAMP DEFAULT now()
);

CREATE TABLE penetapan_ak_items (
    id SERIAL PRIMARY KEY,
    penetapan_ak_id INT NOT NULL REFERENCES penetapan_ak(id),
    predikat_kinerja_log_id INT NOT NULL REFERENCES predikat_kinerja_log(id),
    UNIQUE (predikat_kinerja_log_id)  -- 1 periode hanya boleh muncul di 1 dokumen PAK
);
```

**Mengapa `jenjang_referensi` jadi tabel master, bukan hardcode di kode?**
Karena tabel ini langsung merepresentasikan Pasal 37 PermenPANRB 1/2023 (koefisien per jenjang) — kalau suatu saat regulasi direvisi (pernah terjadi: konvensional → integrasi → konversi sejak 2019, 2022, 2023), admin tinggal update tabel ini tanpa ubah kode aplikasi.

**Mengapa `ak_kumulatif_sebelum/sesudah` di `penetapan_ak` disimpan sebagai snapshot, bukan dihitung ulang setiap saat?**
Karena dokumen PAK adalah **dokumen legal yang sudah diterbitkan** — begitu diterbitkan, isinya tidak boleh berubah lagi walau ada koreksi data di kemudian hari. Histori tetap utuh = sesuai prinsip audit trail. Kalkulasi *live* (untuk dashboard monitoring) tetap dihitung dari `predikat_kinerja_log`, terpisah dari snapshot ini.

---

## 3. Logika Kalkulasi (Application Layer)

```
AK_kumulatif(pegawai, sampai_tanggal) =
    ak_awal_jenjang (dari riwayat_jenjang aktif)
  + SUM(ak_terkonversi)
      FROM predikat_kinerja_log
      WHERE pegawai_id = X
        AND status = 'disetujui'
        AND periode_akhir <= sampai_tanggal
        AND periode berada dalam riwayat_jenjang aktif saat ini
```

```
ak_terkonversi = koefisien_ak_tahun(jenjang_saat_ini) × persentase(predikat) × (durasi_periode / 12 bulan)

persentase:
  Sangat Baik      → 150%
  Baik             → 100%
  Butuh Perbaikan  → 75%
  Kurang           → 50%
  Sangat Kurang    → 25%
```

Ini menggantikan kolom `Nilai 2025`, `Nilai 2026 (Jan-Mar)`, dst. yang sekarang manual diisi per kuartal — sistem otomatis menghitung dari `predikat` yang dipilih lewat dropdown (anti salah ketik).

**Kekurangan/Kelebihan & Potensi Tahun ke Jenjang Berikutnya** (kolom K, M, N, O di spreadsheet sekarang) tetap dipertahankan sebagai *view* turunan, dihitung on-the-fly dari `AK_kumulatif` vs `ak_kumulatif_minimal` jenjang target — tidak perlu disimpan di database.

---

## 4. Arsitektur Aplikasi

Karena skalanya **internal, 1 admin input**, saya sengaja merekomendasikan stack yang **ringan**, bukan arsitektur enterprise yang berlebihan:

```
┌─────────────────────────────────────────────┐
│  Browser (admin) — UI sederhana               │
│  • Form input predikat kinerja per periode    │
│  • Dashboard monitoring (mirror sheet skrg)   │
│  • Tombol "Terbitkan PAK" → generate PDF/DOCX │
└───────────────────┬───────────────────────────┘
                     │ HTTP
┌───────────────────▼───────────────────────────┐
│  Backend (Python — FastAPI)                    │
│  • Endpoint CRUD pegawai, predikat_kinerja_log │
│  • Service kalkulasi AK (logika di atas)       │
│  • Service generate dokumen (docxtpl + WeasyPrint/LibreOffice→PDF) │
└───────────────────┬───────────────────────────┘
                     │
┌───────────────────▼───────────────────────────┐
│  Database — SQLite (cukup untuk 1 admin,       │
│  puluhan pegawai) atau Postgres bila mau lebih │
│  aman untuk backup/concurrent access nanti     │
└─────────────────────────────────────────────────┘
```

**Kenapa stack ini cocok untuk Anda:**
- Anda sudah biasa "vibe coding" dan menyiapkan brief detail untuk Claude Code — FastAPI + SQLite/Postgres + template HTML (atau React ringan) adalah stack yang sangat mudah diserahkan ke Claude Code sebagai agent untuk implementasi, mirip pola yang Anda pakai di pipeline translasi jurnal.
- SQLite cukup untuk 1 admin & data puluhan-ratusan pegawai — tidak perlu server database terpisah, file `.db` bisa di-backup tinggal copy file (penting karena ini data legal pegawai).
- Tidak perlu autentikasi multi-user kompleks dulu — cukup 1 login admin sederhana (atau bahkan auth dasar di level aplikasi) karena ini internal use.

**Generate dokumen PDF + DOCX sekaligus:**
- Buat 1 template DOCX (placeholder pakai `docxtpl`/Jinja-style) sesuai format Penetapan Angka Kredit resmi yang sudah ada → isi otomatis dari data → simpan sebagai `.docx` (masih bisa diedit kalau perlu revisi manual sebelum tanda tangan).
- Convert DOCX yang sama ke PDF (lewat LibreOffice headless) untuk versi "siap cetak/tanda tangan" — jadi satu sumber template, dua output, tidak ada duplikasi logika.

---

## 5. Alur Kerja (Replace Bug → Append-Only Flow)

**Sebelum (sekarang, berisiko):**
```
Admin buka Excel → cari baris pegawai → timpa sel "Nilai 2025" dengan angka baru
→ histori sebelumnya hilang, tidak ada jejak
```

**Sesudah (diusulkan):**
```
1. Admin pilih pegawai → input periode (mis. Apr-Jun 2026) + predikat kinerja (dropdown)
2. Sistem hitung ak_terkonversi otomatis, simpan sebagai baris BARU di predikat_kinerja_log
   (status: draft)
3. Admin review → ubah status jadi "disetujui"
   (kalau salah input, baris ini di-set "dibatalkan" + buat baris koreksi baru — bukan diedit langsung)
4. Saat siap menetapkan: admin pilih satu/lebih periode "disetujui" yang belum pernah
   dipakai di PAK lain → klik "Terbitkan PAK"
5. Sistem snapshot AK sebelum/sesudah, generate nomor PAK, generate PDF + DOCX,
   simpan path file → dokumen siap cetak/tanda tangan
```

---

## 6. Lingkup MVP (disarankan)

| Fitur | Prioritas |
|---|---|
| Master data pegawai + jenjang referensi (dari sheet yang sudah ada) | Wajib |
| Input predikat kinerja per periode (append-only) | Wajib |
| Kalkulasi AK kumulatif otomatis + dashboard mirip "Monitoring AK" | Wajib |
| Generate PAK (PDF + DOCX) dari template | Wajib |
| Riwayat/jejak audit per pegawai (siapa input, kapan) | Wajib |
| Import data awal dari spreadsheet existing (migrasi 1x) | Wajib |
| Multi-user dengan role berbeda | Tidak perlu di MVP (1 admin) |
| Notifikasi otomatis (mis. AK hampir cukup naik jenjang) | Nice-to-have, fase 2 |

---

## 6b. Revisi: Jenis Dokumen, Tembusan, dan Keputusan Render HTML

Setelah melihat contoh format asli (`Format_sudah_Rapih.xlsx`), ada 3 jenis dokumen turunan yang harus bisa dihasilkan dari data yang sama, bukan cuma satu "PAK":

1. **Konversi Predikat Kinerja** — per satu periode/kuartal (1 baris di `predikat_kinerja_log`)
2. **Akumulasi AK** — rekap beberapa periode dalam satu masa penilaian (n baris di `predikat_kinerja_log`, dijumlahkan)
3. **PAK (Penetapan Angka Kredit)** — dokumen resmi dengan breakdown AK Lama/Baru/Jumlah + kalimat penetapan jenjang/pangkat (snapshot final)

Ketiganya berbagi data yang sama (pegawai, periode, predikat, AK terkonversi) — hanya *tata letak* dan *narasi penutup* yang beda. Ini menguatkan keputusan untuk pakai **1 set data + beberapa template render**, bukan 3 alur input terpisah.

### Tabel tambahan: `tembusan_referensi`

Tembusan berbeda per jabatan fungsional / instansi pembina (mis. Perancang PUU → tembusan ke Ditjen PP Kementerian Hukum; Analis Hukum mungkin ke instansi pembina lain). Ini bukan hasil hitung, jadi disimpan sebagai data konfigurasi yang **diisi manual lewat aplikasi**, bukan hardcode di kode/template:

```sql
CREATE TABLE tembusan_referensi (
    id SERIAL PRIMARY KEY,
    jabatan_fungsional TEXT NOT NULL,   -- mis. 'Perancang PUU', 'Analis Hukum'
    urutan INT NOT NULL,
    isi_tembusan TEXT NOT NULL          -- mis. 'Ditjen PP Kementerian Hukum'
);
```
Admin bisa tambah/edit/hapus baris tembusan per jabatan fungsional lewat halaman pengaturan sederhana — begitu jenjang fungsional baru muncul (atau instansi pembina ganti aturan tembusan), tidak perlu sentuh kode.

### Keputusan: render HTML, bukan DOCX/PDF generation

Saya merevisi rekomendasi dari draf sebelumnya. Untuk kasus 1 admin internal dengan kebutuhan "isi, lalu print", **HTML print-ready lebih tepat daripada pipeline DOCX→PDF**:

- Satu sumber template (HTML+CSS `@media print`) untuk ketiga jenis dokumen — bukan dua sumber (docx template + hasil convert) yang bisa drift.
- Admin bisa koreksi kecil langsung di browser sebelum print, tanpa buka Word.
- Cetak fisik atau simpan PDF cukup lewat dialog print browser (`Ctrl+P → Save as PDF`) — hasilnya pasti identik dengan yang dilihat di layar.
- Tidak perlu dependency `docxtpl` + LibreOffice headless untuk convert; cukup template HTML per jenis dokumen + data dari API.
- Kalau nanti butuh arsip PDF otomatis (bukan manual save), baru ditambah render PDF di backend (mis. headless Chrome print-to-pdf) — tetap dari sumber HTML yang sama, jadi tidak ada duplikasi format.

Jadi arsitektur di bagian 4 disederhanakan: hapus kebutuhan `file_docx_path` + service `docxtpl`/LibreOffice. Kolom `file_pdf_path` di `penetapan_ak` tetap dipakai, tapi isinya hasil simpan manual ("Save as PDF" dari browser) — bukan generated otomatis di MVP awal.

---

## 7. Langkah Selanjutnya

Setelah desain ini disetujui, urutan implementasi yang saya sarankan:
1. Saya buatkan template DOCX Penetapan AK (kalau Anda punya contoh format PAK resmi yang biasa dipakai, unggah agar saya tiru formatnya persis).
2. Saya tulis script migrasi dari spreadsheet `Monitoring AK` ke skema di atas (termasuk *flagging* baris bermasalah seperti kasus "Belum Dihitung" untuk direview manual, bukan diimpor mentah).
3. Brief lengkap (skema ini + spesifikasi endpoint) bisa langsung diserahkan ke Claude Code untuk implementasi FastAPI + frontend-nya.

Beri tahu saya kalau ada bagian skema yang mau disesuaikan, atau kalau Anda mau saya lanjut ke pembuatan template dokumen PAK / script migrasi.