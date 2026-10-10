@echo off
setlocal
set "FRAME_DIR=%~dp0"
set "FRAME_APP=%~dp0app.py"
set "FRAME_PY=%USERPROFILE%\miniconda3\envs\cheshi_handedit\pythonw.exe"
if not exist "%FRAME_PY%" (
  echo Python environment cheshi_handedit was not found.
  echo Please use Python 3.10 or newer to run app.py.
  pause
  exit /b 1
)
powershell -NoProfile -Command "$ErrorActionPreference='Stop'; try { Start-Process -FilePath $env:FRAME_PY -ArgumentList (([char]34) + $env:FRAME_APP + ([char]34)) -WorkingDirectory $env:FRAME_DIR -WindowStyle Hidden } catch { Write-Host $_.Exception.Message; exit 1 }"
if errorlevel 1 (
  echo Could not start Frame. Try run-console.bat for details.
  pause
  exit /b 1
)
endlocal
