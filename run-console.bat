@echo off
setlocal
cd /d "%~dp0"
set "FRAME_PY=%USERPROFILE%\miniconda3\envs\cheshi_handedit\python.exe"
if not exist "%FRAME_PY%" (
  echo Python environment cheshi_handedit was not found.
  pause
  exit /b 1
)
"%FRAME_PY%" "%~dp0app.py" %*
set "FRAME_RESULT=%ERRORLEVEL%"
if not "%FRAME_RESULT%"=="0" pause
exit /b %FRAME_RESULT%
