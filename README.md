# Monitoring & Penetapan Angka Kredit (AK) — Biro Hukum

Aplikasi internal 1-admin untuk menggantikan spreadsheet "Monitoring AK". Lihat
`Rancangan_Arsitektur_Aplikasi_Angka_Kredit.md` untuk latar belakang & desain,
dan `AGENT_BRIEF (2).md` untuk spesifikasi lengkap yang diimplementasikan di sini.

## Cara tercepat: `Launch.bat`

Dobel-klik `Launch.bat`. Saat pertama kali dijalankan, ini otomatis akan:
membuat virtual environment, install dependency, inisialisasi database +
data referensi/migrasi, dan menanyakan username/password admin (sekali saja,
disimpan di `secrets.bat` lokal yang TIDAK ikut di-commit). Setelah itu,
browser terbuka otomatis ke `http://127.0.0.1:8000` dan jendela terpisah
("Server Angka Kredit") menjalankan server -- jangan ditutup selama memakai
aplikasi. Jalankan `Launch.bat` lagi kapan saja untuk start ulang (setup di
atas dilewati karena semua sudah tersedia).

## Setup manual (untuk development)

```bash
python -m venv venv
venv\Scripts\activate          # Windows
pip install -r requirements.txt
```

### Environment variables (wajib)

```
ADMIN_USERNAME=admin
ADMIN_PASSWORD_HASH=<bcrypt hash, generate dengan passlib>
SECRET_KEY=<random string, untuk session signing>
```

Generate hash password:

```bash
python -c "from passlib.context import CryptContext; print(CryptContext(schemes=['bcrypt']).hash('password-anda'))"
```

Jangan commit nilai-nilai ini ke repo. Set langsung sebagai environment variable
di terminal/OS atau lewat konfigurasi process manager sebelum menjalankan --
aplikasi ini tidak memuat file `.env` otomatis (sengaja, supaya tidak menambah
dependency `python-dotenv` di luar daftar minimal).

### Database

```bash
python -c "from app.database import Base, engine; import app.models; Base.metadata.create_all(bind=engine)"
sqlite3 data/angka_kredit.db < seed/jenjang_referensi.sql
sqlite3 data/angka_kredit.db < seed/predikat_referensi.sql
sqlite3 data/angka_kredit.db < seed/tembusan_referensi.sql
sqlite3 data/angka_kredit.db < seed/kalimat_penutup_referensi.sql
sqlite3 data/angka_kredit.db < seed/pengaturan_instansi.sql
```

### Migrasi data pegawai dari spreadsheet lama

```bash
python scripts/migrate_spreadsheet.py "1. Angka Kredit JF Biro Hukum dan Estimasi Kenaikan (1).xlsx"
sqlite3 data/angka_kredit.db < seed/seed_data.sql
```

Script ini HANYA mengimpor identitas pegawai (nama, jabatan, jenjang sekarang).
Angka kredit historis (Nilai PAK 2024/2025/2026) SENGAJA tidak diimpor otomatis
(keputusan: kemudahan reset data > replikasi format lama yang sebagian tidak
valid). AK awal tiap pegawai diisi manual lewat form "Catat Naik Jenjang" di
halaman detail pegawai setelah migrasi. Cek `flagged_rows.csv` untuk baris yang
jabatannya tidak bisa diparse otomatis.

### Jalankan

```bash
uvicorn app.main:app --reload --port 8000
```

### Test

```bash
pytest tests/
```

## Keamanan (lihat 1.4o brief)

- Aplikasi ini WAJIB dijalankan di belakang reverse proxy HTTPS, atau dibatasi
  ke `127.0.0.1`/jaringan internal kantor saja — jangan expose ke internet
  tanpa TLS, karena data berisi NIP dan tanggal lahir pegawai.
- CSRF token divalidasi di semua route halaman yang mengubah data (hidden
  field di setiap form). Endpoint JSON `/api/*` dilindungi oleh kombinasi
  login session + content-type JSON (tidak rentan CSRF klasik tanpa CORS).
- File database (`data/angka_kredit.db`) berisi data pribadi pegawai — jangan
  simpan di folder yang ter-sync cloud (Dropbox/Google Drive/OneDrive) tanpa
  enkripsi tambahan.
- Backup: gunakan `sqlite3 data/angka_kredit.db ".backup data/backup.db"` atau
  `VACUUM INTO`, jangan copy file `.db` mentah saat aplikasi sedang berjalan
  (risiko korup).

## Struktur

Lihat `AGENT_BRIEF (2).md` bagian 0 untuk peta folder lengkap. Ringkas:

- `app/calculations.py` — logika kalkulasi AK (murni, gampang ditest)
- `app/services.py` — logika bisnis dipakai bersama router JSON & halaman
- `app/routers/` — endpoint JSON (`/api/*`) dan halaman (Jinja2)
- `app/templates/` — UI server-rendered + 3 template dokumen print
- `scripts/migrate_spreadsheet.py` — migrasi identitas pegawai (1x, lihat di atas)
