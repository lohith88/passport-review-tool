@echo off
setlocal
if "%~1"=="" (
  echo Usage: show_person_folders.bat "D:\path\to\passports"
  exit /b 2
)
echo Person folders directly under:
echo %~1
echo ---------------------------------------------------
powershell -NoProfile -Command "Get-ChildItem -LiteralPath '%~1' -Directory ^| Sort-Object Name ^| Select-Object -ExpandProperty Name"
endlocal
