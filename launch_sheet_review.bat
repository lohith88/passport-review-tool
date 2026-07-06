@echo off
setlocal
cd /d "%~dp0"

if "%~1"=="" (
  echo Usage: launch_sheet_review.bat "D:\path\to\workbook.xlsx" "D:\path\to\passports" "D:\path\to\output"
  echo Fills Sheet1 of the workbook from an offline review and renames folders/files.
  exit /b 2
)
if "%~2"=="" (
  echo Usage: launch_sheet_review.bat "D:\path\to\workbook.xlsx" "D:\path\to\passports" "D:\path\to\output"
  exit /b 2
)
if "%~3"=="" (
  echo Usage: launch_sheet_review.bat "D:\path\to\workbook.xlsx" "D:\path\to\passports" "D:\path\to\output"
  exit /b 2
)

call .venv\Scripts\activate.bat
python run_sheet_review.py ^
  --workbook "%~1" ^
  --folders-root "%~2" ^
  --output-root "%~3" ^
  --config config.example.json
endlocal
