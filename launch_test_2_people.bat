@echo off
setlocal
cd /d "%~dp0"

if "%~1"=="" (
  echo Usage: launch_test_2_people.bat "D:\path\to\passports" "D:\path\to\review-output"
  echo Expected input: passports\Person Name\*.jpg
  exit /b 2
)
if "%~2"=="" (
  echo Usage: launch_test_2_people.bat "D:\path\to\passports" "D:\path\to\review-output"
  echo Expected input: passports\Person Name\*.jpg
  exit /b 2
)

call .venv\Scripts\activate.bat
python run_review.py ^
  --folders-root "%~1" ^
  --output-root "%~2" ^
  --config config.example.json ^
  --copy-renamed ^
  --limit 2
endlocal
