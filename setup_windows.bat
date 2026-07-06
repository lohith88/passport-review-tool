@echo off
setlocal
cd /d "%~dp0"

echo ===================================================
echo Passport Review Tool - Windows Local Setup
echo ===================================================

where py >nul 2>nul
if errorlevel 1 (
  echo Python launcher was not found. Install 64-bit Python 3.11 first.
  exit /b 2
)

if not exist .venv (
  py -3.11 -m venv .venv
  if errorlevel 1 (
    echo Could not create Python 3.11 environment.
    exit /b 2
  )
)

call .venv\Scripts\activate.bat
python -m pip install --upgrade pip setuptools wheel
if errorlevel 1 exit /b 2

set PADDLE_OK=1
python -m pip install paddlepaddle==3.2.0 -i https://www.paddlepaddle.org.cn/packages/stable/cpu/
if errorlevel 1 (
  set PADDLE_OK=0
  echo WARNING: PaddlePaddle installation failed. The tool can still use Tesseract OCR.
)

python -m pip install -r requirements.txt
if errorlevel 1 exit /b 2

where tesseract >nul 2>nul
if errorlevel 1 (
  echo.
  echo WARNING: Tesseract is not installed or not on PATH.
  echo PaddleOCR will still work if its installation succeeded.
  echo See README.md for optional Tesseract installation instructions.
)

python setup_local_models.py --skip-paddle
if errorlevel 1 (
  echo MediaPipe model setup failed. Check internet access and rerun this file.
  exit /b 2
)

if "%PADDLE_OK%"=="1" (
  python setup_local_models.py --skip-mediapipe
  if errorlevel 1 (
    echo WARNING: PaddleOCR model setup failed. Tesseract OCR may still be used.
  )
)

python verify_setup.py
if errorlevel 1 (
  echo Verification found a problem. Review the messages above.
  exit /b 2
)

echo.
echo Setup completed successfully.
echo You may now disconnect from the internet before reviewing documents.
endlocal
