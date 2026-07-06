@echo off
setlocal
cd /d "%~dp0"

if "%~3"=="" (
  echo Usage: run_all_review.bat "workbook.xlsx" ".\passports" ".\passports_output"
  echo Runs the review and automatically resumes/skips if a file crashes the process.
  exit /b 2
)

call .venv\Scripts\activate.bat

echo === Initial run ===
python run_sheet_review.py --workbook "%~1" --folders-root "%~2" --output-root "%~3" --config config.example.json
set CODE=%ERRORLEVEL%

set /a ATTEMPTS=0
:resume_loop
if %CODE%==0 goto done
if %ATTEMPTS% GEQ 80 goto giveup
set /a ATTEMPTS+=1
echo === Resume attempt %ATTEMPTS% (previous exit %CODE%) ===
python run_sheet_review.py --workbook "%~1" --folders-root "%~2" --output-root "%~3" --config config.example.json --resume
set CODE=%ERRORLEVEL%
goto resume_loop

:done
echo === All folders processed. ===
goto end
:giveup
echo === Stopped after %ATTEMPTS% attempts; check the output folder. ===
:end
endlocal
