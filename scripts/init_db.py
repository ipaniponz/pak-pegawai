"""Inisialisasi database awal: buat semua tabel + load seed data referensi
+ data identitas pegawai hasil migrasi (kalau filenya ada). Dipanggil otomatis
oleh Launch.bat HANYA saat data/angka_kredit.db belum ada -- jangan dijalankan
ulang manual kalau db sudah berisi data (akan gagal kena UNIQUE constraint)."""
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.database import Base, engine
import app.models  # noqa: F401  (registrasi model ke Base.metadata)
SEED_FILES = [
    "seed/jenjang_referensi.sql",
    "seed/predikat_referensi.sql",
    "seed/tembusan_referensi.sql",
    "seed/kalimat_penutup_referensi.sql",
    "seed/pengaturan_instansi.sql",
    "seed/seed_data.sql",
]


def main():
    Base.metadata.create_all(bind=engine)
    db_path = ROOT / "data" / "angka_kredit.db"
    con = sqlite3.connect(db_path)
    con.execute("PRAGMA foreign_keys=ON")
    for rel_path in SEED_FILES:
        path = ROOT / rel_path
        if not path.exists():
            print(f"  (lewati {rel_path}, file tidak ada)")
            continue
        con.executescript(path.read_text(encoding="utf-8"))
        print(f"  loaded {rel_path}")
    con.commit()
    con.close()
    print("Database awal siap.")


if __name__ == "__main__":
    main()
