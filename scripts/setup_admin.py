"""Setup awal akun login admin -- dipanggil otomatis oleh Launch.bat kalau
secrets.bat belum ada. Menulis secrets.bat (sudah di-gitignore, JANGAN commit
ke repo) berisi ADMIN_USERNAME, ADMIN_PASSWORD_HASH (bcrypt), dan SECRET_KEY
acak untuk session signing."""
import getpass
import secrets
import sys
from pathlib import Path

from passlib.context import CryptContext

ROOT = Path(__file__).resolve().parent.parent
pwd_context = CryptContext(schemes=["bcrypt"])


def main():
    print("=== Setup awal akun login admin ===")
    username = input("Username: ").strip()
    if not username:
        print("Username tidak boleh kosong.")
        sys.exit(1)
    password = getpass.getpass("Password: ")
    password_confirm = getpass.getpass("Ulangi password: ")
    if not password:
        print("Password tidak boleh kosong.")
        sys.exit(1)
    if password != password_confirm:
        print("Password tidak sama, ulangi lagi.")
        sys.exit(1)

    password_hash = pwd_context.hash(password)
    secret_key = secrets.token_urlsafe(32)

    secrets_bat = ROOT / "secrets.bat"
    secrets_bat.write_text(
        "@echo off\n"
        f"set ADMIN_USERNAME={username}\n"
        f"set ADMIN_PASSWORD_HASH={password_hash}\n"
        f"set SECRET_KEY={secret_key}\n",
        encoding="utf-8",
    )
    print(f"Akun admin '{username}' berhasil dibuat. Simpan username/password ini baik-baik.")


if __name__ == "__main__":
    main()
