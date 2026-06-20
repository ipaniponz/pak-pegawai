# AGENT BRIEF — Aplikasi Monitoring & Penetapan Angka Kredit (AK)
Biro Hukum — Internal, 1 admin. Brief ini ditulis untuk dieksekusi langsung oleh AI coding
agent (Claude Code). Baca juga `Rancangan_Arsitektur_Aplikasi_Angka_Kredit.md` untuk konteks
keputusan desain; dokumen ini berisi spesifikasi konkret yang harus diimplementasikan apa
adanya, bukan ditebak ulang.

---

## 0. Environment & Setup

- Python 3.11+
- `requirements.txt`:
  ```
  fastapi==0.115.*
  uvicorn[standard]==0.30.*
  sqlalchemy==2.0.*
  pydantic==2.*
  jinja2==3.1.*
  python-multipart
  ```
- Database: SQLite, file `data/angka_kredit.db` (folder `data/` di-gitignore isinya kecuali `.gitkeep`).
- Jalankan lokal: `uvicorn app.main:app --reload --port 8000`
- Jangan pakai library tambahan di luar daftar ini tanpa alasan kuat (footprint harus tetap kecil — 1 admin, bukan aplikasi besar).

### Struktur folder (WAJIB diikuti, jangan direorganisasi)
```
angka-kredit-app/
├── app/
│   ├── main.py                 # FastAPI app + route registration
│   ├── database.py             # SQLAlchemy engine/session setup
│   ├── models.py                # SQLAlchemy ORM models (sesuai skema di bagian 1)
│   ├── schemas.py               # Pydantic request/response schemas
│   ├── calculations.py          # Logika kalkulasi AK (bagian 2 brief ini)
│   ├── routers/
│   │   ├── pegawai.py
│   │   ├── jenjang.py
│   │   ├── predikat_kinerja.py
│   │   ├── penetapan.py
│   │   └── tembusan.py
│   ├── templates/
│   │   ├── base.html                       # layout dasar (nav, CSS umum)
│   │   ├── pegawai_list.html
│   │   ├── pegawai_form.html
│   │   ├── predikat_kinerja_form.html
│   │   ├── dashboard.html
│   │   ├── dokumen_konversi_periode.html    # jenis dokumen 1
│   │   ├── dokumen_akumulasi_ak.html        # jenis dokumen 2
│   │   └── dokumen_pak.html                 # jenis dokumen 3
│   └── static/
│       └── print.css            # CSS @media print, dipakai 3 template dokumen
├── scripts/
│   └── migrate_spreadsheet.py   # sudah ada, salin dari deliverable sebelumnya
├── seed/
│   ├── jenjang_referensi.sql    # data master koefisien (bagian 1.1)
│   └── seed_data.sql            # hasil migrate_spreadsheet.py
├── requirements.txt
└── README.md
```

---

## 1. Skema Database — Final (salin persis dari rancangan, jangan diubah)

Gunakan DDL yang ada di `Rancangan_Arsitektur_Aplikasi_Angka_Kredit.md` bagian 2, dengan tambahan tabel `tembusan_referensi` dari bagian 6b, kolom tambahan pada `pegawai` di bagian 5 brief ini, DAN 4 perbaikan kritis di bagian 1.3 di bawah. Implementasikan sebagai SQLAlchemy models di `app/models.py`.

### 1.3 Perbaikan kritis terhadap rancangan awal (WAJIB, ditemukan setelah review ulang)

**(a) `riwayat_pangkat` — append-only, sama prinsipnya dengan `riwayat_jenjang`**
Rancangan awal salah taruh `pangkat`/`golongan_ruang` sebagai kolom tunggal di `pegawai` yang bisa di-edit langsung — itu mengulang bug "replace" yang justru ingin kita hindari. PAK butuh kolom Lama vs Baru untuk pangkat (lihat tabel II sheet "PAK"), jadi pangkat HARUS riwayat, bukan kolom statis.
```sql
CREATE TABLE riwayat_pangkat (
    id SERIAL PRIMARY KEY,
    pegawai_id INT NOT NULL REFERENCES pegawai(id),
    pangkat TEXT NOT NULL,
    golongan_ruang TEXT NOT NULL,
    tmt_pangkat DATE NOT NULL,
    tanggal_selesai DATE,          -- NULL = pangkat aktif saat ini
    sk_referensi TEXT
);
```
Hapus kolom `pangkat`, `golongan_ruang`, `tmt_pangkat` dari tabel `pegawai` (bagian 5.0) — pindahkan semua ke sini. Pangkat "saat ini" = baris dengan `tanggal_selesai IS NULL`. Pangkat "lama" untuk PAK = pangkat yang aktif tepat sebelum `tanggal_penetapan`.

**(b) Penomoran dokumen bersama satu batch — bukan per jenis dokumen**
Di `Format_sudah_Rapih.xlsx`, dokumen Konversi Periode, Akumulasi AK, dan PAK dalam satu proses penilaian **memakai nomor yang sama** (contoh: `034/ROKUM/2026`). Rancangan awal hanya generate nomor di `penetapan_ak`, padahal nomor itu harus dibuat duluan dan dipakai bersama oleh ketiga jenis dokumen.
```sql
CREATE TABLE nomor_dokumen (
    id SERIAL PRIMARY KEY,
    nomor TEXT UNIQUE NOT NULL,      -- format '{urutan}/ROKUM/{tahun}'
    tahun INT NOT NULL,
    urutan INT NOT NULL,
    pegawai_id INT NOT NULL REFERENCES pegawai(id),
    dibuat_pada TIMESTAMP DEFAULT now()
);
```
`penetapan_ak.nomor_pak` diganti jadi FK `nomor_dokumen_id`. Endpoint render dokumen Konversi Periode & Akumulasi AK (bagian 3, "Render Dokumen") juga ambil nomor dari `nomor_dokumen` yang sama dengan PAK terkait — generate nomor baru hanya terjadi sekali per batch, saat admin pertama kali membuka preview dokumen untuk periode/pegawai itu (bukan saat PAK diterbitkan; nomor harus sama persis di ketiga dokumen sejak awal).

**(c) [DIHAPUS -- lihat 1.5(t)]** Validasi "periode tidak boleh melintasi pergantian jenjang" tidak relevan lagi setelah unit predikat kinerja diubah jadi 1 bulan kalender per baris (1.5t) -- jenjang ditentukan otomatis per bulan, tidak ada lagi periode yang bisa "melintasi" pergantian jenjang.

**(d) Pembatalan PAK harus melepas periode yang dipakai**
Constraint `UNIQUE(predikat_kinerja_log_id)` di `penetapan_ak_items` (rancangan bagian 2) akan mengunci periode itu selamanya walau PAK-nya dibatalkan. Perbaikan:
```sql
-- Ganti UNIQUE constraint biasa dengan partial unique index (PostgreSQL) atau
-- cek manual di application layer (SQLite tidak full support partial index lama):
-- index unik HANYA berlaku untuk penetapan_ak_items yang penetapan_ak induknya status != 'dibatalkan'
```
Endpoint `PATCH /api/penetapan-ak/{id}/batalkan`: set `penetapan_ak.status = 'dibatalkan'`, dan periode-periode terkait otomatis jadi tersedia lagi untuk dipilih di PAK baru (cukup filter di query "periode yang belum dipakai" agar mengecualikan item dari PAK berstatus dibatalkan).

**(e) Login dasar — wajib, bukan opsional**
Data berisi NIP, tanggal lahir, dan dokumen legal pegawai. Walau "hanya 1 admin", aplikasi TIDAK BOLEH bisa diakses siapa saja yang punya link/akses jaringan kantor. Tambahkan:
- 1 username/password disimpan sebagai env var (`ADMIN_USERNAME`, `ADMIN_PASSWORD_HASH` — hash dengan `passlib`/`bcrypt`, jangan plain text).
- Session cookie sederhana (FastAPI `SessionMiddleware` + cookie httponly) — tidak perlu JWT/OAuth, ini bukan multi-user.
- Semua route di bagian 3 & 4 (kecuali `/login`) wajib login. Endpoint `/dokumen/.../print` JUGA wajib login walau dibuka di tab baru.

---

### 1.4 Perbaikan kritis tambahan (hasil red-team review Claude Opus, WAJIB)

**(f) `ak_pangkat_minimal` -- PAK butuh DUA ambang (pangkat & jenjang), bukan satu**
Sheet "PAK" menampilkan dua baris berbeda: kekurangan AK untuk kenaikan pangkat DAN untuk kenaikan jenjang. `jenjang_referensi` hanya punya satu kolom (`ak_kumulatif_minimal` = ambang jenjang). Tambahkan:
```sql
ALTER TABLE jenjang_referensi ADD COLUMN ak_pangkat_minimal NUMERIC(6,2);
```
Reseed dengan pasangan AK Pangkat/AK Jenjang per jenjang (Ahli Pertama 50/100, Ahli Muda 100/200, Ahli Madya 150/450, Ahli Utama 200/-, Terampil 20/40, Mahir 50/100, Penyelia 100/-) -- TAPI lihat bagian 8 (C3): angka ini perlu diverifikasi dulu ke Lampiran PermenPANRB 1/2023, jangan langsung dianggap benar. Tabel II PAK harus menampilkan dua baris kekurangan terpisah (pangkat vs jenjang), bukan digabung jadi satu.

**(g) Snapshot PAK harus lengkap, bukan cuma 2 angka**
`ak_kumulatif_sebelum/sesudah` dan `kalimat_penutup` sudah di-snapshot, tapi field lain (pangkat, jabatan, koefisien, nama pejabat penilai, tembusan) masih dirender live dari tabel master. Konsekuensi: kalau koefisien/tembusan/nama pejabat diedit di kemudian hari, PAK lama yang di-print ulang akan menampilkan data baru -- melanggar prinsip dokumen legal immutable. Tambahkan:
```sql
ALTER TABLE penetapan_ak ADD COLUMN snapshot_data TEXT;  -- JSON, semua field tampil di dokumen
```
Diisi SEKALI saat status menjadi 'terbit'. Render PAK baca dari `snapshot_data`, bukan join ke tabel live. Isi minimal: identitas perorangan, pangkat+golru+tmt, jabatan+jenjang+tmt, koefisien, kedua ambang AK (lihat poin f), nama+NIP pejabat penilai, daftar tembusan terurut, instansi+kota, rincian per periode.

**(h) PAK tidak boleh editable saat print -- beda kelas dengan Konversi/Akumulasi**
Rancangan awal mengizinkan "koreksi kecil di browser sebelum print" secara umum. Untuk PAK (dokumen legal bernomor & ditandatangani), ini berbahaya -- kertas yang ditandatangani bisa berbeda dari record di database tanpa jejak. Aturan baru:
- Dokumen Konversi Periode & Akumulasi AK: boleh `contenteditable` (dokumen kerja).
- Dokumen PAK: render strict dari `snapshot_data`, TIDAK editable. Tambahkan footer otomatis: `Dokumen dihasilkan sistem -- No. {nomor} -- dicetak {timestamp} -- ref #{penetapan_ak_id}`.

**(i) Audit trail untuk approval & pembatalan (bukan cuma untuk input data)**
Transisi status (`draft->disetujui`, `*->dibatalkan`, PAK `terbit->dibatalkan`) saat ini mengubah kolom in-place tanpa mencatat siapa/kapan/kenapa -- padahal ini aksi paling kritis secara hukum. Tambahkan:
```sql
ALTER TABLE predikat_kinerja_log ADD COLUMN disetujui_oleh TEXT;
ALTER TABLE predikat_kinerja_log ADD COLUMN disetujui_pada TIMESTAMP;
ALTER TABLE predikat_kinerja_log ADD COLUMN dibatalkan_oleh TEXT;
ALTER TABLE predikat_kinerja_log ADD COLUMN dibatalkan_pada TIMESTAMP;
ALTER TABLE predikat_kinerja_log ADD COLUMN alasan_pembatalan TEXT;

ALTER TABLE penetapan_ak ADD COLUMN dibatalkan_oleh TEXT;
ALTER TABLE penetapan_ak ADD COLUMN dibatalkan_pada TIMESTAMP;
ALTER TABLE penetapan_ak ADD COLUMN alasan_pembatalan TEXT;
```
`PATCH .../status` dan `PATCH .../batalkan`: wajib body `{alasan}` untuk pembatalan (400 kalau kosong), isi timestamp+actor otomatis di server.

**(j) Perbaiki constraint unik di `predikat_kinerja_log` -- bug yang sama dengan 1.3(d)**
`UNIQUE(pegawai_id, periode_mulai, periode_akhir)` biasa membuat admin TIDAK BISA membuat baris koreksi dengan periode yang sama persis setelah baris lama dibatalkan (kuncinya masih terpakai). **[SUDAH DIGANTI -- lihat 1.5(t)]** skema final `predikat_kinerja_log` sudah pakai `tahun`+`bulan` (bukan periode_mulai/periode_akhir), dan partial unique index `uq_bulan_aktif` di 1.5(t) sudah menerapkan pola yang sama (mengecualikan baris berstatus 'dibatalkan').

**(k) `pegawai.nip` harus nullable + flag kelengkapan data -- data sumber tidak punya NIP/tgl lahir/pangkat sama sekali**
Skema sebelumnya mewajibkan `nip UNIQUE NOT NULL`, tapi sheet "Monitoring AK" sumber TIDAK punya kolom NIP, tanggal lahir, karpeg, atau pangkat -- migrasi akan gagal kalau constraint ini dipertahankan ketat. Perbaikan:
```sql
ALTER TABLE pegawai ADD COLUMN data_lengkap BOOLEAN NOT NULL DEFAULT 0;
```
`migrate_spreadsheet.py` impor dengan `nip=NULL`, `data_lengkap=0` untuk semua 34 pegawai (karena memang belum ada datanya). Tambahkan validasi keras: endpoint terbit PAK tolak (400) kalau `data_lengkap=0` -- dokumen legal tidak boleh terbit dengan field perorangan kosong. Admin set `data_lengkap=1` manual setelah field wajib (NIP, tgl lahir, pangkat via `riwayat_pangkat`) diisi lengkap.

**(l) Generate nomor dokumen saat PAK terbit, BUKAN saat preview dibuka**
1.3(b) menyuruh generate nomor "saat preview pertama dibuka" -- risikonya: kalau admin batal/urung setelah preview, nomor itu sudah terpakai (hangus), bikin register nomor bolong (034, 036, ... tanpa 035) yang akan dipertanyakan auditor. Perbaikan:
- Generate nomor di endpoint `POST .../penetapan-ak` (saat PAK benar-benar diajukan/terbit), bukan saat preview.
- Sebelum PAK terbit, preview dokumen Konversi/Akumulasi menampilkan placeholder `(nomor akan diberikan saat penetapan)`.
- Bungkus increment nomor dalam transaksi DB untuk cegah nomor kembar kalau dua aksi nyaris bersamaan.

**(m) Pisahkan nama jabatan fungsional dari jenjang -- tiga ejaan berbeda di data akan membuat lookup tembusan gagal**
Data sumber: `jabatan_fungsional = "Perancang PUU Ahli Madya"` (gabung nama+jenjang). Judul dokumen butuh nama lengkap tanpa jenjang ("Perancang Peraturan Perundang-undangan"). Seed tembusan (1.2) pakai ejaan itu juga. Kalau dibiarkan gabung, pencarian tembusan berdasarkan `jabatan_fungsional` pegawai TIDAK AKAN PERNAH cocok -> tembusan selalu kosong. Perbaikan:
```
pegawai.jabatan_fungsional menyimpan NAMA DASAR resmi saja (tanpa jenjang),
mis. 'Perancang Peraturan Perundang-undangan'. Jenjang aktif diambil dari
riwayat_jenjang -> jenjang_referensi.nama_jenjang, JANGAN digabung di kolom yang sama.
```
`migrate_spreadsheet.py` (`parse_jabatan`) harus dipetakan ke nama dasar resmi: "Perancang PUU" -> "Perancang Peraturan Perundang-undangan", "Analis Hukum" tetap "Analis Hukum", dst. -- bukan disimpan apa adanya dari teks sumber.

**(n) Tambah `status_kepegawaian` (CPNS/PNS) -- kondisi pemicu kalimat penutup CPNS hilang setelah refactor**
Brief 5.5 menyuruh cek `jenjang_target == 'CPNS'`, tapi field itu sudah tidak ada di skema final (jenjang berikutnya diturunkan dari urutan `jenjang_referensi`). CPNS bukan "jenjang", tapi status kepegawaian terpisah. Tambahkan:
```sql
ALTER TABLE pegawai ADD COLUMN status_kepegawaian TEXT NOT NULL DEFAULT 'PNS'
    CHECK (status_kepegawaian IN ('CPNS','PNS'));
```
Pemilihan template kalimat penutup pakai `status_kepegawaian = 'CPNS'`, bukan field jenjang.

**(o) Keamanan tambahan: CSRF, secret key, transport**
- Tambahkan CSRF token (disimpan di session + hidden field form) divalidasi di semua endpoint mutasi (POST/PATCH/DELETE).
- `SECRET_KEY` untuk `SessionMiddleware` WAJIB dari environment variable acak, JANGAN hardcode/commit ke repo.
- Catat di README: jalankan di belakang reverse proxy HTTPS, atau batasi akses ke `127.0.0.1`/jaringan internal saja -- jangan expose tanpa TLS karena data berisi NIP & tanggal lahir.

**(p) Jangan replikasi bug pembulatan dari spreadsheet lama**
Spreadsheet sumber memakai pembagi yang sedikit salah (`/28.15` padahal seharusnya `37.5 x 0.75 = 28.125`). Dashboard (bagian 3) yang "replikasi kolom M/N/O" harus menghitung ulang dari `koefisien_ak_tahun x persentase(predikat)` langsung via `calculations.py` -- JANGAN menyalin pembagi lama yang sudah diketahui keliru.

---

### 1.5 Revisi setelah konfirmasi C1, C3, C5: jadikan konfigurasi via UI, bukan hardcode/SQL manual

Setelah dikonfirmasi ke pihak HR, tiga hal berikut TERNYATA perlu lebih fleksibel dari yang direncanakan semula (kebijakan/angka ini bisa berubah, dan HR butuh kontrol langsung tanpa minta developer ubah kode):

**(q) AK Dasar / AK JF Lama / AK Penyesuaian -- input manual per PAK, BUKAN hardcode 0**
C1 terkonfirmasi: ada jalur selain CPNS (perpindahan jabatan) di mana HR sudah tahu angka dasarnya. Brief 5.4 sebelumnya men-hardcode baris 1-3 Tabel II = 0. Perbaikan:
```sql
ALTER TABLE penetapan_ak ADD COLUMN ak_dasar NUMERIC(8,3) NOT NULL DEFAULT 0;
ALTER TABLE penetapan_ak ADD COLUMN ak_jf_lama NUMERIC(8,3) NOT NULL DEFAULT 0;
ALTER TABLE penetapan_ak ADD COLUMN ak_penyesuaian NUMERIC(8,3) NOT NULL DEFAULT 0;
```
Form "Terbitkan PAK" (bagian 4) menampilkan 3 input angka ini dengan default 0 (cocok untuk jalur CPNS, tinggal submit apa adanya), TAPI admin bisa isi manual untuk jalur perpindahan jabatan. `ak_kumulatif_sebelum` di Tabel II = `ak_dasar + ak_jf_lama + ak_penyesuaian` (bukan murni dari `hitung_ak_kumulatif` riwayat konversi saja).

**(r) `jenjang_referensi` -- HARUS bisa diedit lewat UI, bukan cuma seed SQL**
C3 terkonfirmasi sudah benar nilainya, TAPI kebijakan bisa berubah (revisi regulasi). Batalkan keputusan di bagian 6 ("edit jenjang_referensi tidak perlu di MVP, cukup SQL manual") -- ganti jadi:
- Tambah halaman `/pengaturan/jenjang-referensi` -- tabel CRUD sederhana: edit `koefisien_ak_tahun`, `ak_kumulatif_minimal`, `ak_pangkat_minimal` per baris. TIDAK perlu hapus/tambah baris jenjang baru di MVP (jumlah jenjang sudah final per kategori), cukup edit angka.
- Tambah endpoint: `GET /api/jenjang-referensi` (sudah ada) + `PUT /api/jenjang-referensi/{id}`.
- PENTING: ini hanya mengubah angka untuk **PAK yang akan diterbitkan setelah perubahan** -- PAK yang sudah terbit tetap aman karena sudah di-snapshot (lihat 1.4g). Konsistensi snapshot inilah yang membuat fitur edit ini aman dilakukan kapan saja tanpa merusak dokumen lama.

**(s) Label & persentase predikat kinerja -- tabel referensi yang bisa diedit, bukan hardcode di kode**
C5 terkonfirmasi: aturan persentase (150/100/75/50/25%) sudah diatur Permendikdasmen, TAPI sebutan/labelnya bisa berubah. Ganti `PERSENTASE_PREDIKAT` dict hardcode di `calculations.py` (bagian 2.1) jadi tabel database:
```sql
CREATE TABLE predikat_referensi (
    id SERIAL PRIMARY KEY,
    nama TEXT UNIQUE NOT NULL,        -- mis. 'Sangat Baik' (bisa diedit jadi sebutan lain)
    persentase NUMERIC(4,2) NOT NULL, -- mis. 1.50
    urutan INT NOT NULL
);
INSERT INTO predikat_referensi (nama, persentase, urutan) VALUES
('Sangat Baik', 1.50, 1),
('Baik', 1.00, 2),
('Butuh Perbaikan', 0.75, 3),
('Kurang', 0.50, 4),
('Sangat Kurang', 0.25, 5);
```
- `predikat_kinerja_log.predikat` jadi FK ke `predikat_referensi.id` (bukan `TEXT CHECK(...)` hardcode lagi).
- Dropdown predikat di form input (bagian 4) ambil opsi dari tabel ini, bukan list statis di kode -- tetap dropdown (BUKAN free text), jadi prinsip anti-typo tetap terjaga.
- Tambah halaman `/pengaturan/predikat-kinerja` -- CRUD sederhana (boleh ubah `nama` & `persentase`, peringatan kalau persentase diubah karena berlaku ke semua perhitungan baru setelahnya, BUKAN yang sudah terbit/disetujui sebelumnya -- `ak_terkonversi` yang sudah dihitung tidak dihitung ulang otomatis).

**(t) REVISI LANJUTAN (setelah klarifikasi tambahan dari user): unit dasar predikat kinerja adalah 1 BULAN KALENDER, bukan date-range bebas**

Klarifikasi: kadensa bulanan berlaku untuk **SEMUA pegawai** (bukan cuma CPNS), dan kadensa akan bervariasi per pegawai (sekarang tahunan, nanti triwulanan/bulanan). Solusi paling fleksibel: jadikan **1 bulan kalender sebagai unit atomik**, lalu triwulanan/tahunan tinggal "gabungan beberapa baris bulanan" -- bukan field kadensa terpisah.

**Ini MENGGANTIKAN seluruh desain `periode_mulai`/`periode_akhir` bebas di rancangan & brief sebelumnya.** Skema `predikat_kinerja_log` final:
```sql
CREATE TABLE predikat_kinerja_log (
    id SERIAL PRIMARY KEY,
    pegawai_id INT NOT NULL REFERENCES pegawai(id),
    tahun INT NOT NULL,
    bulan INT NOT NULL CHECK (bulan BETWEEN 1 AND 12),
    predikat_referensi_id INT NOT NULL REFERENCES predikat_referensi(id),
    jenjang_referensi_id_snapshot INT NOT NULL REFERENCES jenjang_referensi(id),  -- jenjang yang aktif bulan itu, di-snapshot saat input
    koefisien_terpakai NUMERIC(6,3) NOT NULL,   -- snapshot koefisien_ak_tahun saat input (lihat alasan immutability di bawah)
    persentase_terpakai NUMERIC(4,2) NOT NULL,  -- snapshot persentase predikat saat input
    ak_terkonversi NUMERIC(8,3) NOT NULL,       -- = (koefisien_terpakai/12) * persentase_terpakai
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','disetujui','dibatalkan')),
    dibuat_oleh TEXT NOT NULL,
    dibuat_pada TIMESTAMP DEFAULT now(),
    disetujui_oleh TEXT, disetujui_pada TIMESTAMP,
    dibatalkan_oleh TEXT, dibatalkan_pada TIMESTAMP, alasan_pembatalan TEXT,
    catatan TEXT
);
CREATE UNIQUE INDEX uq_bulan_aktif
  ON predikat_kinerja_log (pegawai_id, tahun, bulan)
  WHERE status != 'dibatalkan';
```

**Kenapa `koefisien_terpakai`/`persentase_terpakai` di-snapshot per baris (bukan join live ke `jenjang_referensi`/`predikat_referensi` saat hitung):**
Sejak 1.5(r) dan 1.5(s), kedua tabel referensi itu BISA diedit admin kapan saja. Kalau `predikat_kinerja_log` join live, maka mengedit koefisien tahun depan akan **mengubah angka AK bulan-bulan yang sudah disetujui tahun ini** -- melanggar prinsip immutable yang sama dengan alasan snapshot PAK (1.4g). Snapshot di titik input menjaga histori tetap konsisten apa pun perubahan referensi di masa depan.

**Cara penentuan `jenjang_referensi_id_snapshot` otomatis:** ambil jenjang dari `riwayat_jenjang` pegawai yang aktif pada bulan tsb (cek `tanggal_mulai <= tanggal_1_bulan_itu` dan `tanggal_selesai IS NULL OR tanggal_selesai >= tanggal_akhir_bulan_itu`). Edge case langka (jenjang berubah di tengah bulan): pakai jenjang yang aktif pada **tanggal 1 bulan tersebut** -- cukup untuk kasus nyata, jangan over-engineer proporsi harian dalam 1 bulan.

**Formula (`calculations.py` 2.2, REVISI):**
```python
def hitung_ak_bulanan(koefisien_ak_tahun: float, persentase: float) -> float:
    return (koefisien_ak_tahun / 12) * persentase
```
Lebih sederhana dari formula range-tanggal sebelumnya -- tidak perlu hitung selisih bulan lagi, karena setiap baris memang persis 1 bulan.

**Test case 2.4 perlu disesuaikan:** baris "7 bulan -> 7.292" dan "3 bulan -> 3.125" sekarang dihasilkan dari **menjumlahkan 7 baris bulanan** dan **3 baris bulanan** masing-masing (bukan 1 baris dengan range tanggal). Hasil akhirnya tetap harus sama (7 x 1.0417 = 7.2917, dst.) -- tambahkan test "SUM 7 baris bulanan Ahli Pertama Baik = 7.292" sebagai pengganti test range-tanggal.

**Form input (bagian 4, REVISI):** ganti date-range picker jadi **dropdown Bulan + Tahun + Predikat** (3 dropdown, bukan 2 date picker) -- 1 submit = 1 bulan. Untuk efisiensi input banyak bulan sekaligus (mis. input setahun penuh saat migrasi/awal pakai), sediakan juga mode "isi beberapa bulan sekaligus" (tabel 12 baris per tahun, isi predikat per bulan, submit semua sekaligus sebagai batch -- tetap insert 1 baris per bulan di belakang).

**Render Akumulasi AK & PAK (bagian 5.3/5.4, REVISI):** "Masa Penilaian" = bulan-tahun paling awal s.d. paling akhir dari baris-baris bulanan yang dipilih admin (boleh 1 bulan/bulanan, 3 bulan/triwulanan, 12 bulan/tahunan -- fleksibel per pegawai, tidak perlu field kadensa eksplisit). Tabel rincian di dokumen Akumulasi tetap 1 baris per bulan seperti sebelumnya, hanya sumbernya sekarang `tahun`+`bulan` bukan `periode_mulai`+`periode_akhir`.

**1.3(c) (validasi periode lintas jenjang) DIHAPUS/tidak relevan lagi** -- karena unit sudah pasti 1 bulan, tidak ada lagi periode yang "melintasi" pergantian jenjang.

---

### 1.1 Seed wajib: `jenjang_referensi`
Data ini HARUS di-seed sebelum apa pun lain jalan (foreign key dari `riwayat_jenjang`).

```sql
INSERT INTO jenjang_referensi (kategori, nama_jenjang, golru, koefisien_ak_tahun, ak_kumulatif_minimal, urutan) VALUES
('Keahlian', 'Ahli Pertama', 'III/a, III/b', 12.5, 100, 1),
('Keahlian', 'Ahli Muda',    'III/c, III/d', 25,   200, 2),
('Keahlian', 'Ahli Madya',   'IV/a, IV/b, IV/c', 37.5, 450, 3),
('Keahlian', 'Ahli Utama',   'IV/d, IV/e', 50,   NULL, 4),
('Keterampilan', 'Pemula',    'II/a', 3.75, 15,  1),
('Keterampilan', 'Terampil',  'II/b, II/c, II/d', 5,  40, 2),
('Keterampilan', 'Mahir',     'III/a, III/b', 12.5, 100, 3),
('Keterampilan', 'Penyelia',  'III/c, III/d', 25,  NULL, 4);
```

### 1.2 Seed awal: `tembusan_referensi`
Isi minimal berikut (boleh ditambah/diedit lewat aplikasi nanti):

```sql
INSERT INTO tembusan_referensi (jabatan_fungsional, urutan, isi_tembusan) VALUES
('Perancang Peraturan Perundang-undangan', 1, 'Pejabat Fungsional yang bersangkutan'),
('Perancang Peraturan Perundang-undangan', 2, 'Kepala Biro Hukum'),
('Perancang Peraturan Perundang-undangan', 3, 'Direktorat Jenderal Peraturan Perundang-undangan, Kementerian Hukum'),
('Analis Hukum', 1, 'Pejabat Fungsional yang bersangkutan'),
('Analis Hukum', 2, 'Kepala Biro Hukum');
```
(Sumber: tembusan di `Format_sudah_Rapih.xlsx`. Tembusan untuk jabatan fungsional lain — Perencana, Analis SDM Aparatur, Arsiparis — belum ada contoh formatnya; biarkan kosong dan admin isi manual lewat halaman pengaturan tembusan saat dibutuhkan. JANGAN ditebak/diisi otomatis dengan asumsi.)

---

## 2. Logika Kalkulasi — `app/calculations.py`

### 2.1 Sumber persentase predikat — DARI DATABASE, bukan konstanta hardcode

**Revisi (lihat 1.5s):** jangan buat dict `PERSENTASE_PREDIKAT` hardcode di Python. Baca dari tabel `predikat_referensi` (query sekali, cache in-memory per request kalau perlu performa). Ini supaya admin bisa ubah label/persentase lewat halaman `/pengaturan/predikat-kinerja` tanpa redeploy kode. Fungsi di `calculations.py` menerima `persentase: float` sebagai parameter (sudah di-lookup oleh caller dari `predikat_referensi`), bukan menerima string `predikat` lalu lookup dict internal.

### 2.2 Fungsi konversi predikat → AK
```python
# [SUPERSEDED -- lihat 1.5(t)] Fungsi ini awalnya berbasis range tanggal bebas.
# Setelah revisi unit-per-bulan, gunakan fungsi sederhana ini:
def hitung_ak_bulanan(koefisien_ak_tahun: float, persentase: float) -> float:
    """ak = (koefisien_ak_tahun / 12) * persentase. Satu baris = persis 1 bulan kalender."""
    return (koefisien_ak_tahun / 12) * persentase
```

### 2.3 Fungsi AK kumulatif pegawai
```python
def hitung_ak_kumulatif(pegawai_id: int, sampai_tahun_bulan: tuple[int, int] | None = None) -> float:
    """
    = ak_awal_jenjang dari riwayat_jenjang yang aktif (tanggal_selesai IS NULL)
    + SUM(ak_terkonversi) dari predikat_kinerja_log
        WHERE status = 'disetujui'
        AND (tahun, bulan) <= sampai_tahun_bulan (default: bulan ini)
        AND jenjang_referensi_id_snapshot = jenjang yang sama dengan riwayat_jenjang aktif saat ini
    (filter jenjang dipakai supaya AK dari jenjang sebelumnya, kalau ada, tidak otomatis
    tercampur ke kumulatif jenjang baru -- konsisten dengan ak_awal_jenjang sebagai baseline)
    """
```

### 2.4 Test case wajib (tulis sebagai unit test, `tests/test_calculations.py`)
Gunakan angka ini untuk verifikasi — kalau hasil kode tidak cocok, ada bug. **(Direvisi untuk model per-bulan, lihat 1.5t.)**

| Input | Hasil yang benar |
|---|---|
| `hitung_ak_bulanan(koefisien=37.5, persentase=1.5)` — 1 baris bulanan Ahli Madya, Sangat Baik | **4.6875** (= 56.25/12) |
| 12 baris bulanan Ahli Madya, Sangat Baik, dijumlahkan | **56.25** |
| 12 baris bulanan Ahli Madya, Baik, dijumlahkan | **37.5** |
| 12 baris bulanan Ahli Madya, Butuh Perbaikan, dijumlahkan | **28.125** |
| 7 baris bulanan (Jun–Des) Ahli Pertama, Baik, dijumlahkan | **7.291666...** (≈7.292) — cocok dengan contoh nyata di `Format_sudah_Rapih.xlsx` sheet "KONVERSI PREDIKAT KINERJA1" |
| 3 baris bulanan (Jan–Mar) Ahli Pertama, Baik, dijumlahkan | **3.125** — cocok dengan sheet "KONVERSI PREDIKAT KINERJA 2" |
| Akumulasi kedua kelompok di atas (7+3 = 10 baris bulanan, semua Baik) | **10.4166...** (≈10.417) — cocok dengan sheet "AKUMULASI AK" |

Kalau angka-angka contoh nyata ini tidak persis cocok, JANGAN lanjut ke fitur lain — perbaiki dulu `calculations.py`.

---

## 3. API Endpoints

Semua response JSON kecuali endpoint dengan suffix `/print` (HTML).

### Pegawai
- `GET /api/pegawai` — list semua pegawai (query param `status=aktif` optional filter)
- `GET /api/pegawai/{id}` — detail + AK kumulatif terkini (panggil `hitung_ak_kumulatif`)
- `POST /api/pegawai` — body: `{nip, nama, kategori_jf, jabatan_fungsional, substansi}`
- `PUT /api/pegawai/{id}`
- `POST /api/pegawai/{id}/riwayat-jenjang` — naik jenjang baru, body: `{jenjang_referensi_id, tanggal_mulai, ak_awal_jenjang, sk_referensi}`. Tutup `tanggal_selesai` riwayat jenjang sebelumnya otomatis.

### Jenjang Referensi
- `GET /api/jenjang-referensi` — read-only di MVP (edit manual lewat SQL kalau regulasi berubah, tidak perlu UI edit)

### Predikat Kinerja
- `GET /api/pegawai/{id}/predikat-kinerja` — list riwayat periode pegawai tsb
- `POST /api/pegawai/{id}/predikat-kinerja` — body: `{tahun, bulan, predikat_referensi_id}` (lihat 1.5t -- unit per bulan, bukan range tanggal). Mendukung body berupa array untuk input batch banyak bulan sekaligus.
  - Validasi: tolak (400) kalau `(tahun, bulan)` sudah ada baris aktif (bukan 'dibatalkan') untuk pegawai yang sama.
  - Tentukan `jenjang_referensi_id_snapshot` otomatis dari `riwayat_jenjang` aktif pada tanggal 1 bulan tsb.
  - Snapshot `koefisien_terpakai` & `persentase_terpakai` dari tabel referensi saat ini, hitung `ak_terkonversi` pakai `hitung_ak_bulanan()`, simpan dengan `status='draft'`.
- `PATCH /api/predikat-kinerja/{id}/status` — body: `{status: "disetujui"|"dibatalkan"}`. Hanya draft→disetujui atau apapun→dibatalkan yang diizinkan; tolak transisi lain (400).

### Penetapan AK (PAK)
- `POST /api/pegawai/{id}/penetapan-ak` — body: `{predikat_kinerja_log_ids: [int], pejabat_penilai_id, tanggal_penetapan}`.
  - Validasi: semua id berstatus 'disetujui' dan belum dipakai di `penetapan_ak_items` manapun (cek constraint).
  - Hitung `ak_kumulatif_sebelum` = `hitung_ak_kumulatif(pegawai_id, sampai_tahun_bulan=bulan tepat sebelum bulan paling awal yang dipilih)`,
    `ak_kumulatif_sesudah` = `hitung_ak_kumulatif(pegawai_id, sampai_tahun_bulan=bulan paling akhir yang dipilih)`.
  - Generate `nomor_pak` otomatis: format `{urutan}/ROKUM/{tahun}` (urutan = auto-increment per tahun, mulai dari 1).
- `GET /api/penetapan-ak/{id}` — detail lengkap termasuk item-item periode yang dicakup

### Tembusan
- `GET /api/tembusan-referensi?jabatan_fungsional=...`
- `POST /api/tembusan-referensi` — body: `{jabatan_fungsional, urutan, isi_tembusan}`
- `DELETE /api/tembusan-referensi/{id}`

### Render Dokumen (HTML, untuk print)
- `GET /dokumen/konversi-periode/{predikat_kinerja_log_id}/print` → render `dokumen_konversi_periode.html`
- `GET /dokumen/akumulasi/{pegawai_id}/print?dari_tahun=...&dari_bulan=...&sampai_tahun=...&sampai_bulan=...` → render `dokumen_akumulasi_ak.html`, agregasi semua baris bulanan berstatus disetujui dalam rentang tsb
- `GET /dokumen/pak/{penetapan_ak_id}/print` → render `dokumen_pak.html`

### Dashboard
- `GET /api/dashboard` — list semua pegawai aktif dengan kolom: AK kumulatif saat ini, AK target jenjang berikutnya, kekurangan/kelebihan, estimasi tahun mencukupi (replikasi kolom M/N/O di spreadsheet lama, dihitung on-the-fly, TIDAK disimpan di DB)

---

## 4. Halaman UI (frontend server-rendered Jinja2 + sedikit JS untuk interaktivitas, TIDAK perlu React/SPA)

| Halaman | Route | Isi |
|---|---|---|
| Dashboard | `/` | Tabel mirip sheet "Monitoring AK": nama, jabatan, AK kumulatif, kekurangan, status. Klik nama → ke detail pegawai. |
| Daftar Pegawai | `/pegawai` | Tabel + tombol "Tambah Pegawai" |
| Form Pegawai | `/pegawai/baru`, `/pegawai/{id}/edit` | Form sesuai field `pegawai` (termasuk field tambahan bagian 5) |
| Detail Pegawai | `/pegawai/{id}` | Info pegawai + riwayat jenjang + tabel riwayat predikat kinerja (dengan status badge draft/disetujui/dibatalkan) + tombol "Input Predikat Kinerja Baru" + tombol "Terbitkan PAK" (muncul kalau ada minimal 1 periode disetujui yang belum dipakai PAK) |
| Form Input Predikat Kinerja | `/pegawai/{id}/predikat-kinerja/baru` | Dropdown Bulan + Tahun + Predikat (3 dropdown, BUKAN free text/date-range — lihat 1.5t), preview AK terkonversi real-time. Sediakan juga mode batch: tabel 12 baris (Jan–Des) untuk isi setahun sekaligus. |
| Form Terbitkan PAK | `/pegawai/{id}/penetapan-ak/baru` | Checkbox list periode disetujui yang belum dipakai, pilih pejabat penilai, tanggal penetapan → submit → redirect ke halaman print |
| Halaman Pengaturan Tembusan | `/pengaturan/tembusan` | CRUD sederhana per jabatan fungsional |
| Halaman Pengaturan Kalimat Penutup | `/pengaturan/kalimat-penutup` | CRUD sederhana per kondisi (lihat bagian 5.5) |
| Halaman Pengaturan Jenjang Referensi | `/pengaturan/jenjang-referensi` | Edit koefisien & ambang AK per jenjang (lihat 1.5r) |
| Halaman Pengaturan Predikat Kinerja | `/pengaturan/predikat-kinerja` | Edit label & persentase predikat (lihat 1.5s) |

Setiap halaman dokumen print (`/dokumen/.../print`) dibuka di tab baru, **tidak punya nav/header aplikasi** (supaya saat di-print bersih, hanya isi dokumen) — gunakan layout terpisah, bukan `base.html`.

---

## 5. Template Dokumen HTML (3 jenis, isi konkret)

Acuan isi dan tata letak **harus identik** dengan `Format_sudah_Rapih.xlsx` (nama field, urutan, kalimat baku). Tiga sheet acuan: "KONVERSI PREDIKAT KINERJA1/2", "AKUMULASI AK", "PAK".

### 5.0 Kolom tambahan WAJIB di tabel `pegawai` sebelum bagian ini bisa jalan
Field berikut ADA di format dokumen tapi BELUM ADA di skema database sebelumnya. Tambahkan ke `pegawai` (semua nullable, admin isi manual lewat form edit pegawai), JANGAN diasumsikan sudah tersedia:
`nomor_karpeg`, `tempat_lahir`, `tanggal_lahir`, `jenis_kelamin`, `tmt_jabatan`, `unit_kerja`. (Field `pangkat`/`golongan_ruang`/`tmt_pangkat` TIDAK masuk di sini — lihat `riwayat_pangkat` di bagian 1.3(a), karena harus berupa riwayat append-only, bukan kolom statis di `pegawai`.)

**Ingat juga 3 perbaikan dari bagian 1.4 yang berdampak ke tabel `pegawai`:** `nip` jadi nullable + kolom `data_lengkap` (1.4k), `jabatan_fungsional` hanya berisi nama dasar TANPA jenjang (1.4m), dan tambahan kolom `status_kepegawaian` CPNS/PNS (1.4n).

`instansi` dan `kota` (untuk "Ditetapkan di ...") konstan untuk semua dokumen — simpan di tabel kecil baru `pengaturan_instansi (key TEXT PRIMARY KEY, value TEXT)`, BUKAN diketik ulang manual setiap generate dokumen. Tambahkan juga `instansi_pembina` terpisah (lihat B9 — beda dengan `instansi` pemberi kerja, dipakai untuk redaksi tembusan).

### 5.1 `static/print.css` (dipakai semua 3 template)
```css
@media print {
  @page { size: A4; margin: 2cm; }
  body { font-family: 'Times New Roman', serif; font-size: 12pt; }
}
body { font-family: 'Times New Roman', serif; font-size: 12pt; max-width: 21cm; margin: auto; }
table { width: 100%; border-collapse: collapse; margin: 1em 0; }
table, th, td { border: 1px solid #000; padding: 4px 8px; }
.no-border td, .no-border th { border: none; }
.center { text-align: center; }
.signature-block { margin-top: 3em; text-align: right; }
.header-title { text-align: center; font-weight: bold; text-transform: uppercase; }
```

### 5.2 `dokumen_konversi_periode.html` — struktur field (ikuti urutan exact dari sheet "KONVERSI PREDIKAT KINERJA1")
```
KONVERSI PREDIKAT KINERJA KE ANGKA KREDIT
{jabatan_fungsional pegawai, UPPERCASE}
NOMOR {nomor_dokumen}
Instansi: {instansi}                          Periode: {bulan_nama} {tahun}

PEJABAT FUNGSIONAL YANG DINILAI
1. Nama                          : {nama}
2. NIP                           : {nip}
3. Nomor Seri Karpeg             : {nomor_karpeg, boleh kosong}
4. Tempat / Tanggal Lahir        : {tempat_lahir}, {tanggal_lahir}
5. Jenis Kelamin                 : {jenis_kelamin}
6. Pangkat / Golongan Ruang / TMT: {pangkat} ({golongan_ruang}) / {tmt_pangkat}
7. Jabatan/TMT                   : {jabatan_fungsional} / {tmt_jabatan}
8. Unit Kerja                    : {unit_kerja}

KONVERSI PREDIKAT KINERJA KE ANGKA KREDIT
| Hasil Penilaian Kinerja (Predikat) | Prosentase | Koefisien per tahun | AK yang didapat |
| {predikat}                          | {persentase_terpakai} | {koefisien_terpakai} | {ak_terkonversi} |

                                          Ditetapkan di {kota}
                                          Pada tanggal {tanggal_penetapan}

                                          Pejabat Penilai Kinerja,

                                          {nama_pejabat_penilai}
                                          NIP {nip_pejabat_penilai}

Tembusan disampaikan kepada:
{loop tembusan_referensi sesuai jabatan_fungsional pegawai, urut sesuai field `urutan`}
```

### 5.3 `dokumen_akumulasi_ak.html` — sesuai sheet "AKUMULASI AK"
Sama seperti di atas tapi bagian tabel jadi multi-baris (1 baris per `predikat_kinerja_log` dalam rentang masa penilaian) + baris total:
```
| Tahun | Periodik (Bulan) | Predikat | Prosentase | Koefisien/Tahun | AK Diperoleh |
{loop per baris predikat_kinerja_log bulanan, urut (tahun, bulan) ascending}
JUMLAH ANGKA KREDIT YANG DIPEROLEH: {sum semua ak_terkonversi}
```
Header pakai "Masa Penilaian: {bulan_nama+tahun paling awal} s.d {bulan_nama+tahun paling akhir}" dari baris-baris bulanan yang dipilih -- ini otomatis fleksibel untuk kadensa bulanan/triwulanan/tahunan tanpa field kadensa terpisah.

### 5.4 `dokumen_pak.html` — sesuai sheet "PAK", bagian paling kompleks
```
PENETAPAN ANGKA KREDIT
{jabatan_fungsional}
NOMOR {nomor_pak}
Instansi: {instansi}                    Masa Penilaian: {bulan_nama+tahun paling awal} s.d {bulan_nama+tahun paling akhir}

I. KETERANGAN PERORANGAN
   (8 baris field sama seperti 5.2)

II. PENETAPAN ANGKA KREDIT
| No | Uraian                                      | Lama | Baru | Jumlah |
| 1  | AK Dasar yang diberikan                     | 0    |      | 0      |
| 2  | AK JF lama                                  | 0    |      | 0      |
| 3  | AK Penyesuaian/Penyetaraan                  | 0    |      | 0      |
| 4  | AK Konversi                                 | {ak_kumulatif_sebelum} | {sum ak periode ini} | {ak_kumulatif_sesudah} |
| 5  | AK dari peningkatan pendidikan              | 0    |      | 0      |
JUMLAH ANGKA KREDIT KUMULATIF: {ak_kumulatif_sesudah}

                              | Pangkat | Jenjang Jabatan |
AK Minimal untuk kenaikan     | {ak_minimal pangkat berikutnya} | {ak_minimal jenjang berikutnya} |
Kekurangan AK untuk kenaikan  | {selisih}  | {selisih} |

{kalimat penutup — LIHAT bagian 5.5 di bawah untuk mekanisme lengkap, JANGAN hardcode if/else di kode}
```

### 5.5 Mekanisme Kalimat Penutup PAK — data-driven, bukan hardcode

Kalimat penutup PAK (mis. "DAPAT DIPERTIMBANGKAN UNTUK DIANGKAT MENJADI PNS...") adalah teks hukum baku yang variasinya banyak: pengangkatan CPNS→PNS, kenaikan pangkat, kenaikan jenjang, kenaikan pangkat+jenjang sekaligus, atau belum memenuhi syarat. Kita HANYA punya contoh redaksi resmi untuk kondisi CPNS→PNS (dari `Format_sudah_Rapih.xlsx`). Menebak redaksi untuk kondisi lain berisiko salah secara administratif/legal — JANGAN dilakukan.

**Implementasi:**

1. Tambah tabel:
   ```sql
   CREATE TABLE kalimat_penutup_referensi (
       id SERIAL PRIMARY KEY,
       kondisi TEXT NOT NULL UNIQUE,   -- 'pengangkatan_cpns_pns', 'kenaikan_pangkat', dst (free text, admin yang nentuin nama kondisinya)
       template TEXT NOT NULL          -- boleh pakai placeholder {jabatan_fungsional}, {pangkat}, {jenjang}, dst.
   );
   ```
   Seed awal HANYA 1 baris yang sudah terverifikasi:
   ```sql
   INSERT INTO kalimat_penutup_referensi (kondisi, template) VALUES
   ('pengangkatan_cpns_pns', 'DAPAT DIPERTIMBANGKAN UNTUK DIANGKAT MENJADI PNS DALAM JABATAN FUNGSIONAL {jabatan_fungsional} DENGAN PANGKAT {pangkat}');
   ```
   Kondisi lain (kenaikan pangkat, kenaikan jenjang, dll.) TIDAK di-seed sampai admin (Anda) memasukkan redaksi resmi yang benar lewat halaman pengaturan.

2. Tambah kolom `kalimat_penutup TEXT` (nullable) di tabel `penetapan_ak` — ini yang disimpan permanen di dokumen yang sudah terbit (snapshot, konsisten dengan prinsip immutable di bagian 2 rancangan arsitektur).

3. Di form "Terbitkan PAK" (`/pegawai/{id}/penetapan-ak/baru`):
   - Sistem cek kondisi pegawai (jenjang_target == 'CPNS' → cocokkan ke `kalimat_penutup_referensi` kondisi `pengangkatan_cpns_pns`, isi otomatis sebagai default).
   - Tampilkan sebagai **textarea yang bisa diedit manual** sebelum submit — bukan teks statis hasil render. Kalau tidak ada kondisi yang cocok (kenaikan pangkat/jenjang dll. yang belum ada template), textarea kosong.
   - Validasi: `kalimat_penutup` TIDAK BOLEH kosong saat status mau diset 'terbit' (400 kalau kosong) — supaya tidak ada dokumen terbit dengan baris penutup hilang.

4. Halaman pengaturan tambahan: `/pengaturan/kalimat-penutup` — CRUD sederhana untuk `kalimat_penutup_referensi`, supaya begitu Anda dapat redaksi resmi untuk kenaikan pangkat/jenjang, tinggal ditambahkan sebagai template baru tanpa perlu ubah kode.

**Kesimpulan untuk agent:** field ini SELALU manual-editable di UI, prefill otomatis hanya terjadi kalau ada template terverifikasi yang cocok. Jangan menulis logika tebak-kalimat untuk kondisi yang belum punya template di `kalimat_penutup_referensi`.

ASLI Penetapan Angka Kredit untuk          Ditetapkan di {kota}
Jabatan Fungsional yang bersangkutan       Pada tanggal {tanggal_penetapan}

                                            Pejabat Penilai Kinerja,
                                            {nama_pejabat_penilai}
                                            NIP {nip_pejabat_penilai}

Tembusan disampaikan kepada:
{loop tembusan_referensi}
```

---

## 6. Yang SENGAJA tidak masuk MVP (jangan dikerjakan agent kecuali diminta eksplisit)
- Generate PDF otomatis di server (cukup andalkan print browser dulu)
- Multi-user / login role-based
- Notifikasi otomatis AK hampir cukup
- ~~Edit `jenjang_referensi` lewat UI~~ — REVISI (lihat 1.5r): ini SUDAH WAJIB masuk MVP, bukan dikecualikan, karena kebijakan koefisien/ambang AK bisa berubah dan HR butuh kontrol langsung tanpa minta developer ubah kode.

## 7. Definition of Done untuk MVP
- [ ] Semua test case angka di bagian 2.4 lolos
- [ ] Seed `jenjang_referensi` + `tembusan_referensi` jalan tanpa error
- [ ] `migrate_spreadsheet.py` bisa diimpor ke DB baru lewat `seed_data.sql` tanpa FK error
- [ ] Bisa input predikat kinerja baru → status draft → disetujui → muncul di dashboard
- [ ] Bisa pilih ≥1 periode disetujui → terbitkan PAK → nomor PAK auto-generate → halaman print menampilkan data benar
- [ ] 3 halaman dokumen print menghasilkan tata letak yang readable saat di-print ke PDF dari browser (cek manual di Chrome print preview)
- [ ] Tidak ada cara untuk mengedit `ak_terkonversi` atau `ak_kumulatif_sebelum/sesudah` langsung dari UI (harus selalu lewat alur append-only)
- [ ] PAK tidak bisa berstatus 'terbit' tanpa `kalimat_penutup` terisi (textarea manual-editable, prefill otomatis hanya untuk kondisi CPNS→PNS)
- [ ] Pangkat tersimpan sebagai riwayat (`riwayat_pangkat`), tidak ada kolom pangkat statis yang bisa ditimpa langsung
- [ ] Dokumen Konversi Periode, Akumulasi AK, dan PAK dalam satu batch memakai `nomor_dokumen` yang sama persis
- [ ] Input periode kinerja ditolak (400) kalau melintasi tanggal pergantian jenjang
- [ ] Membatalkan PAK melepas periode terkait sehingga bisa dipakai lagi di PAK baru
- [ ] Tidak ada halaman/endpoint yang bisa diakses tanpa login (kecuali `/login` itu sendiri)
- [ ] PAK menampilkan DUA baris kekurangan AK terpisah (pangkat & jenjang), bukan digabung
- [ ] PAK lama yang di-print ulang menampilkan data PERSIS sama dengan saat terbit (dari `snapshot_data`, tidak terpengaruh perubahan data master setelahnya)
- [ ] Dokumen PAK tidak bisa diedit manual sebelum print (beda dengan Konversi/Akumulasi yang boleh)
- [ ] Setiap persetujuan & pembatalan tercatat siapa/kapan/alasan -- tidak ada perubahan status tanpa jejak
- [ ] Tembusan otomatis terisi benar untuk Perancang PUU & Analis Hukum (bukan kosong karena mismatch nama jabatan)
- [ ] Nomor dokumen hanya digenerate saat PAK benar-benar terbit, tidak hangus karena preview dibatalkan
- [ ] Migrasi 34 pegawai berhasil tanpa error walau NIP/tgl lahir/pangkat kosong (status `data_lengkap=0`)
- [ ] Endpoint terbit PAK menolak (400) kalau `data_lengkap=0` untuk pegawai terkait
- [ ] Admin bisa edit koefisien & ambang AK di `/pengaturan/jenjang-referensi` tanpa perlu ubah kode, dan PAK lama tetap tidak terpengaruh (snapshot)
- [ ] Admin bisa edit label & persentase predikat di `/pengaturan/predikat-kinerja` tanpa perlu ubah kode
- [ ] Form Terbitkan PAK punya input manual AK Dasar/AK JF Lama/AK Penyesuaian (default 0, bisa diisi untuk jalur perpindahan jabatan)
- [ ] Input periode kinerja ditolak (400) kalau kurang dari 1 bulan kalender
- [ ] `predikat_kinerja_log` memakai unit per-bulan (`tahun`+`bulan`), bukan range tanggal bebas; Akumulasi/PAK fleksibel menggabung 1/3/12 baris bulanan sesuai kadensa masing-masing pegawai
- [ ] `migrate_spreadsheet.py` diupdate: nilai "Nilai 2025" & "Nilai 2026 Jan-Mar" (total tahunan/kuartalan legacy) tetap diimpor sebagai SATU baris ringkasan per periode (predikat=NULL, catatan "legacy"), BUKAN dipecah otomatis jadi 12/3 baris bulanan palsu — karena predikat asli per bulan tidak tercatat di spreadsheet lama. Baris-baris baru yang diinput admin SETELAH migrasi yang memakai format bulanan penuh.

---

## 8. Robustness Tambahan (Nice-to-have, kerjakan setelah MVP inti jalan)

Dari review Opus, bukan blocker tapi sebaiknya tidak dilupakan:

- **Validasi periode di luar rentang jenjang aktif** — jangan diam-diam menghitung lalu di-drop dari kumulatif; tolak di endpoint dengan pesan jelas.
- **Sanity check periode >12 bulan** — kemungkinan salah input (penilaian seharusnya tahunan), beri peringatan atau tolak.
- **Kategorisasi AK legacy hasil migrasi** — AK warisan dari spreadsheet lama (`ak_awal_jenjang`) secara administratif beda baris dengan "AK Konversi" di Tabel II PAK. Pertimbangkan kolom asal AK supaya PAK pertama pasca-migrasi menaruhnya di baris yang benar.
- **Tampilan kekurangan negatif (kelebihan AK)** — tampilkan `0`/`-` saat sudah cukup, jangan angka negatif mentah di dokumen PAK.
- **Prosedur backup SQLite yang aman** — gunakan `VACUUM INTO 'backup.db'` atau aktifkan WAL, jangan sekadar copy file `.db` saat aplikasi aktif (bisa korup). Catat di README bahwa file database berisi data pribadi pegawai, jangan disimpan di folder yang ter-sync cloud sembarangan.
- **Pegawai kategori Struktural** — pastikan dashboard & tombol "Terbitkan PAK" otomatis skip pegawai ini (tidak punya `riwayat_jenjang`), jangan sampai error saat `hitung_ak_kumulatif` dipanggil untuk mereka.
- **Kebijakan pembulatan tampilan** — simpan presisi penuh di database, tapi sepakati aturan tampil (mis. 3 desimal) supaya 3 dokumen yang berbagi 1 nomor tidak terlihat beda angka satu sama lain.

---

## 9. Pertanyaan Regulasi — Status Jawaban

Awalnya 5 pertanyaan (C1–C5) sengaja tidak dijawab sendiri oleh agent karena menyangkut keabsahan dokumen legal. Status setelah dikonfirmasi ke HR:

**C1 — SUDAH DIJAWAB.** Ada jalur selain CPNS (perpindahan jabatan), HR sudah punya angkanya. → diimplementasikan sebagai input manual, lihat **1.5(q)**.

**C2 — BELUM DIJAWAB, masih terbuka.**
Kalau nanti ditambah template kalimat penutup "kenaikan pangkat" (lihat 5.5), apakah sistem perlu mengecek syarat tambahan (mis. minimal 2 tahun dalam pangkat terakhir, predikat minimal "Baik" 2 tahun terakhir) sebelum menyarankan kalimat itu? Atau itu murni pertimbangan manual pejabat penilai di luar sistem? **Tidak blocking untuk MVP** (kondisi non-CPNS templatenya memang sengaja kosong/manual di 5.5) — bisa dijawab kapan saja sebelum fase pengembangan kalimat penutup non-CPNS dimulai.

**C3 — SUDAH DIJAWAB.** Angka ambang sudah dicocokkan dan benar. Tapi karena kebijakan bisa berubah, → dibuat editable lewat UI, lihat **1.5(r)**, bukan sekadar di-seed statis.

**C4 — SUDAH DIJAWAB.** PAK saat ini tahunan (akhir tahun), periode bisa custom (CPNS Jun–Des = 7 bulan), ke depan bisa per bulan. → date picker bebas + minimal 1 bulan, formula sudah sesuai (tidak berubah), lihat **1.5(t)**.

**C5 — SUDAH DIJAWAB.** Diatur Permendikdasmen, tapi sebutan bisa berubah. → label & persentase predikat jadi tabel `predikat_referensi` yang editable lewat UI, lihat **1.5(s)**, bukan hardcode `CHECK` constraint atau dict Python.

