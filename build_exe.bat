@echo off
REM ============================================================
REM  Trip Bot - Windows build script
REM  Run this ON WINDOWS, in a folder containing:
REM    - auto_trip_bot.py   (the patched script)
REM    - signature.png
REM  (No chromedriver needed - Selenium Manager fetches it
REM   automatically at runtime, matched to the user's Chrome.)
REM ============================================================

echo Checking for required files...
if not exist auto_trip_bot.py (
    echo ERROR: auto_trip_bot.py not found in this folder.
    goto :end
)
if not exist signature.png (
    echo ERROR: signature.png not found in this folder.
    goto :end
)

echo Installing/upgrading build dependencies...
python -m pip install --upgrade pip
python -m pip install --upgrade pyinstaller "selenium>=4.15"

echo Building TripBot.exe ...
REM --collect-all selenium: PyInstaller's static import scan misses several
REM Selenium submodules that are loaded dynamically (e.g.
REM selenium.webdriver.chrome.options), causing ModuleNotFoundError at
REM runtime even though selenium is installed. --collect-all forces every
REM selenium submodule + its data files into the bundle.
python -m PyInstaller ^
  --name TripBot ^
  --onefile ^
  --console ^
  --collect-all selenium ^
  --add-data "signature.png;." ^
  auto_trip_bot.py

echo.
echo ============================================================
echo Build complete. Find TripBot.exe in the "dist" folder.
echo Give users ONLY dist\TripBot.exe -- nothing else needed.
echo ============================================================

:end
pause
