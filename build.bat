@echo off
cd /d "%~dp0"
python -m pip install -r requirements-dev.txt -q
if exist "dist\StreamFeed.exe" del /f "dist\StreamFeed.exe"
python -m PyInstaller --noconfirm --onefile --windowed --name StreamFeed --add-data "telegram_channels.json;." main.py
copy /y "telegram_channels.json" "dist\telegram_channels.json" >nul 2>&1
echo.
echo Готово: dist\StreamFeed.exe
echo Каналы TG: dist\telegram_channels.json
pause
