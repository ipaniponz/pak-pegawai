@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (
    set "PY_CREATE_VENV=py -3.11"
) else (
    set "PY_CREATE_VENV=python"
)

if not exist venv (
    echo [Setup] Membuat virtual environment Python...
    %PY_CREATE_VENV% -m venv venv
    if errorlevel 1 (
        echo.
        echo Gagal membuat virtual environment. Pastikan Python 3.11+ sudah
        echo terpasang dan tercatat di PATH, lalu coba jalankan lagi.
        pause
        exit /b 1
    )
)

call venv\Scripts\activate.bat

echo [Setup] Memeriksa dependency Python...
pip install -q -r requirements.txt
if errorlevel 1 (
    echo.
    echo Gagal install dependency. Cek koneksi internet lalu coba lagi.
    pause
    exit /b 1
)

if not exist data\angka_kredit.db (
    echo [Setup] Inisialisasi database awal + data referensi...
    python scripts\init_db.py
)

if not exist secrets.bat (
    echo.
    python scripts\setup_admin.py
    if errorlevel 1 (
        echo Setup akun admin dibatalkan/gagal.
        pause
        exit /b 1
    )
)

call secrets.bat

start "Server Angka Kredit - JANGAN DITUTUP selama aplikasi dipakai" cmd /k "uvicorn app.main:app --port 8000"
timeout /t 3 /nobreak >nul
start "" http://127.0.0.1:8000

echo.
echo Aplikasi berjalan di http://127.0.0.1:8000
echo Jendela server terbuka terpisah -- JANGAN ditutup selama memakai aplikasi.
echo Tutup jendela "Server Angka Kredit" itu untuk menghentikan aplikasi.
echo.
pause
