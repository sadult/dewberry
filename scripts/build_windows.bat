@echo off
REM ============================================================
REM  Dewberry - Windows build script
REM ============================================================
setlocal
cd /d "%~dp0.."

echo [1/4] Creating virtual environment...
if not exist .venv (
    python -m venv .venv
)
call .venv\Scripts\activate.bat

echo [2/4] Installing dependencies...
python -m pip install --upgrade pip
pip install -r requirements.txt

echo [3/4] Building with PyInstaller...
pyinstaller --noconfirm build\dewberry.spec

echo [4/4] Done.
echo Output: dist\Dewberry\Dewberry.exe
echo Remember to place xray.exe, tun2socks.exe, wintun.dll, geoip.dat and
echo geosite.dat into dist\Dewberry\core\
endlocal
pause
