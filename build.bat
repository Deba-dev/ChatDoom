@echo off
REM Builds dist\CHATDOOM\CHATDOOM.exe and, if Inno Setup is installed, installer\CHATDOOM-Setup.exe
cd /d "%~dp0"
py -3.12 -m pip install -r requirements.txt pyinstaller
py -3.12 -m PyInstaller --noconfirm --windowed --noupx --name CHATDOOM --icon assets\icon.ico --version-file version_info.txt --add-data "assets;assets" --exclude-module numpy --exclude-module PIL --exclude-module tkinter --exclude-module matplotlib --collect-submodules pytchat --collect-submodules edge_tts --collect-all PySide6.QtWebEngineCore --collect-all PySide6.QtWebEngineWidgets main.py
set ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe
if exist "%ISCC%" (
  "%ISCC%" installer.iss
  echo.
  echo Installer ready: installer\CHATDOOM-Setup.exe
) else (
  echo.
  echo App ready: dist\CHATDOOM\CHATDOOM.exe
  echo For a proper Setup.exe, install the free Inno Setup 6 from jrsoftware.org and run build.bat again.
)
pause
