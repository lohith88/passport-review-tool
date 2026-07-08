# Passport Review Tool - Complete Guide

## Table of Contents

1. [What This Tool Does](#what-this-tool-does)
2. [Setup Instructions](#setup-instructions)
   - [Windows Setup](#windows-setup)
   - [macOS Setup](#macos-setup)
3. [Two Modes of Operation](#two-modes-of-operation)
4. [Usage Examples](#usage-examples)
5. [Output Structure](#output-structure)
6. [Troubleshooting](#troubleshooting)

---

## What This Tool Does

This is a **local-only passport document review and validation system** that processes person-wise passport folders using computer vision and OCR, **without sending any data to cloud services**.

### Core Features

✅ **Automatic Document Classification**

- Passport front page (data/biodata page)
- Passport back page (address/last page)
- Blank/visa pages
- Standalone photograph

✅ **Quality Checks**

- Photo dimensions (390×567 px at 300 DPI)
- Image clarity (blur, contrast)
- Face detection and positioning
- Hand/finger detection
- Passport number consistency across pages
- Duplicate page detection
- File format validation (JPG/JPEG required)

✅ **Privacy & Security**

- Process-level network blocking during reviews
- All processing runs locally (PaddleOCR, Tesseract, MediaPipe, OpenCV)
- Full passport numbers only in memory, masked in reports
- Original files never modified

✅ **Two Operating Modes**

1. **Dynamic Mode**: Process folders without Excel (preserves folder names)
2. **Spreadsheet Mode**: Match folders to Excel rows and rename based on Excel data

---

## Setup Instructions

### Windows Setup

#### Prerequisites

1. **Install Python 3.11 (64-bit)**
   - Download from: https://www.python.org/downloads/
   - ✅ Check "Add Python to PATH" during installation
   - Verify: Open PowerShell and run `py --version`

2. **Install Tesseract OCR (Optional but Recommended)**
   - Download from: https://github.com/UB-Mannheim/tesseract/wiki
   - Install to default location: `C:\Program Files\Tesseract-OCR`
   - Add to PATH: `C:\Program Files\Tesseract-OCR`

#### Installation Steps

1. **Download the tool**

   ```powershell
   # Option A: Download ZIP from GitHub and extract
   # Option B: Clone with git
   git clone https://github.com/lohith88/passport-review-tool.git
   cd passport-review-tool
   ```

2. **Run the setup script**

   ```powershell
   .\setup_windows.bat
   ```

   This will:
   - Create a Python virtual environment (`.venv`)
   - Install PaddlePaddle OCR engine
   - Install all required Python packages
   - Download MediaPipe face/hand detection models
   - Download PaddleOCR models
   - Verify the installation

3. **Wait for completion**
   - First run needs internet (downloads ~500MB of models)
   - You'll see: "Setup completed successfully"
   - After this, you can work **completely offline**

4. **Verify installation**
   ```powershell
   .\.venv\Scripts\python.exe verify_setup.py
   ```

#### Folder Structure After Setup

```
passport-review-tool/
├── .venv/                          # Python virtual environment
├── models/                         # Downloaded AI models
│   ├── face_landmarker.task
│   ├── hand_landmarker.task
│   └── (PaddleOCR models)
├── passport_review/                # Tool source code
├── config.example.json             # Configuration file
├── setup_windows.bat               # Setup script
├── run_review.py                   # Dynamic mode script
├── run_sheet_review.py             # Spreadsheet mode script
├── launch_review.bat               # Quick launcher
└── requirements.txt                # Python dependencies
```

---

### macOS Setup

#### Prerequisites

1. **Install Homebrew** (if not already installed)

   ```bash
   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
   ```

2. **Install Python 3.11 and Tesseract**
   ```bash
   brew install python@3.11 git tesseract
   ```

#### Installation Steps

1. **Clone the repository**

   ```bash
   git clone https://github.com/lohith88/passport-review-tool.git
   cd passport-review-tool
   ```

2. **Make scripts executable**

   ```bash
   chmod +x setup_linux_mac.sh run_all_review.sh
   ```

3. **Run the setup script**

   ```bash
   ./setup_linux_mac.sh
   ```

   This will:
   - Create a Python virtual environment (`.venv`)
   - Install PaddlePaddle OCR engine
   - Install all required Python packages
   - Download MediaPipe and PaddleOCR models
   - Verify the installation

4. **Apple Silicon (M1/M2/M3) Note**

   If PaddlePaddle installation fails:

   ```bash
   source .venv/bin/activate
   pip install paddlepaddle  # Latest version
   pip install -r requirements.txt
   python setup_local_models.py
   python verify_setup.py
   ```

5. **Verify installation**
   ```bash
   source .venv/bin/activate
   python verify_setup.py
   ```

---

## Two Modes of Operation

### Mode 1: Dynamic Folder Review (No Excel Required)

**Use when:** You just want to review folders without Excel integration

**Command:** `run_review.py`

**Features:**

- Discovers person folders automatically
- Uses folder names as-is for output
- No spreadsheet needed
- Generates CSV reports only

**Input Structure Required:**

```
passports/                          ← Input root
├── Person One/                     ← Each person has their own folder
│   ├── IMG_001.jpg                 ← Passport images inside
│   ├── IMG_002.jpg
│   ├── IMG_003.jpg
│   └── photo.jpg
├── Person Two/
│   ├── Ravi_front.jpg              ← Filename keywords work
│   ├── Ravi_back.jpg
│   ├── Ravi_blank_01.jpg
│   └── Ravi_photo.jpg
└── Person Three/
    └── ...
```

**Output Structure:**

```
output/
├── review_results.csv              # Full review report
├── manual_review_queue.csv         # Items needing human review
├── review_summary.txt              # Statistics summary
└── renamed-documents/              # Only if --copy-renamed used
    ├── Person One/                 # Same name as input folder
    │   ├── Person One_passport_front.jpg
    │   ├── Person One_passport_back.jpg
    │   ├── Person One_passport_blank_01.jpg
    │   └── Person One_photo.jpg
    └── Person Two/
        └── ...
```

---

### Mode 2: Spreadsheet Review (Excel-Driven Renaming)

**Use when:** You want to match folders to Excel rows and rename everything

**Command:** `run_sheet_review.py`

**Features:**

- Matches folders to Excel rows automatically
- **Renames folders AND files based on Excel data**
- Fills review results back into Excel
- Generates detailed reports

**Excel Columns Used:**

| Column | Purpose                   | Example                     |
| ------ | ------------------------- | --------------------------- |
| A      | Booking ID                | `2608-KMYM-0050`            |
| B      | TSF ID                    | `TSF1234`                   |
| D      | Name                      | `Ravi Kumar`                |
| E      | Passport No. Front        | `A1234567`                  |
| **L**  | **Target Folder Name**    | `Kumar_Ravi_TSF1234`        |
| **M**  | **Target Front Filename** | `Kumar_Ravi_passport_front` |
| **N**  | **Target Last Filename**  | `Kumar_Ravi_passport_last`  |
| **O**  | **Target Blank Filename** | `Kumar_Ravi_passport_blank` |
| **P**  | **Target Photo Filename** | `Kumar_Ravi_photo`          |

**Folder Matching Priority:**

The tool matches each person folder to an Excel row using (in order):

1. **Passport number** detected from front page → Column E
2. **TSF ID** found in filenames → Column B
3. **Booking ID** found in filenames → Column A
4. **Person name** (last resort) → Column D

**Example Transformation:**

**Before (Input):**

```
passports/
└── Ravi Kumar/
    ├── IMG_001.jpg  (detected as front)
    ├── IMG_002.jpg  (detected as back)
    ├── IMG_003.jpg  (detected as blank)
    └── photo.jpg    (detected as photo)
```

**Excel Row:**

```
Column L: "Kumar_Ravi_TSF1234"
Column M: "Kumar_Ravi_passport_front"
Column N: "Kumar_Ravi_passport_last"
Column O: "Kumar_Ravi_passport_blank"
Column P: "Kumar_Ravi_photo"
```

**After (Output):**

```
output/reviewed-documents/
└── Kumar_Ravi_TSF1234/              ← Renamed from "Ravi Kumar"
    ├── Kumar_Ravi_passport_front.jpg    ← From IMG_001.jpg
    ├── Kumar_Ravi_passport_last.jpg     ← From IMG_002.jpg
    ├── Kumar_Ravi_passport_blank.jpg    ← From IMG_003.jpg
    └── Kumar_Ravi_photo.jpg             ← From photo.jpg
```

**Excel Output Columns:**

The tool fills these columns in your Excel file:

| Column                           | Content                  | Values                             |
| -------------------------------- | ------------------------ | ---------------------------------- |
| Passport Front Page Review (new) | Front page status        | `ok` / `Error` / `Not legible`     |
| F - Passport No. Back            | Back page status         | `ok` / `Error` / `Not legible`     |
| G - Passport No. Blank Pages     | Blank pages status       | `ok` / `Error` / `Not legible`     |
| H - Photo Dimension              | Photo status             | `ok` / `Error` / `Not legible`     |
| I - Any comments for errors      | Detailed comments        | Full passport numbers (local only) |
| Email (re-upload request) (new)  | Draft email to applicant | Text or blank                      |

---

## Usage Examples

### Windows Examples

#### Dynamic Mode (No Excel)

**Basic review (reports only, no file copying):**

```powershell
.\.venv\Scripts\python.exe run_review.py `
  --folders-root ".\passports" `
  --output-root ".\output"
```

**Review AND create renamed copies:**

```powershell
.\.venv\Scripts\python.exe run_review.py `
  --folders-root ".\passports" `
  --output-root ".\output" `
  --copy-renamed
```

**Quick launcher (with file copying):**

```powershell
& ".\launch_review.bat" ".\passports" ".\output"
```

**Test with first 2 folders only:**

```powershell
.\.venv\Scripts\python.exe run_review.py `
  --folders-root ".\passports" `
  --output-root ".\output" `
  --copy-renamed `
  --limit 2
```

#### Spreadsheet Mode (Excel-Driven)

**Basic spreadsheet review:**

```powershell
.\.venv\Scripts\python.exe run_sheet_review.py `
  --workbook ".\Option A2 Group 2 - all docs review.xlsx" `
  --folders-root ".\passports" `
  --output-root ".\output"
```

**With auto-resume (recommended - handles crashes):**

```powershell
& ".\run_all_review.bat" ".\Option A2 Group 2 - all docs review.xlsx" ".\passports" ".\output"
```

**Fill Excel only (no file copying):**

```powershell
.\.venv\Scripts\python.exe run_sheet_review.py `
  --workbook ".\Option A2 Group 2 - all docs review.xlsx" `
  --folders-root ".\passports" `
  --output-root ".\output" `
  --no-copy
```

**Test with first 5 folders:**

```powershell
.\.venv\Scripts\python.exe run_sheet_review.py `
  --workbook ".\Option A2 Group 2 - all docs review.xlsx" `
  --folders-root ".\passports" `
  --output-root ".\output" `
  --limit 5
```

**Resume interrupted run:**

```powershell
.\.venv\Scripts\python.exe run_sheet_review.py `
  --workbook ".\Option A2 Group 2 - all docs review.xlsx" `
  --folders-root ".\passports" `
  --output-root ".\output" `
  --resume
```

---

### macOS Examples

#### Dynamic Mode (No Excel)

**Basic review with file copying:**

```bash
source .venv/bin/activate
python run_review.py \
  --folders-root "./passports" \
  --output-root "./output" \
  --copy-renamed
```

**Test with first 2 folders:**

```bash
source .venv/bin/activate
python run_review.py \
  --folders-root "./passports" \
  --output-root "./output" \
  --copy-renamed \
  --limit 2
```

#### Spreadsheet Mode (Excel-Driven)

**Basic spreadsheet review:**

```bash
source .venv/bin/activate
python run_sheet_review.py \
  --workbook "./Option A2 Group 2 - all docs review.xlsx" \
  --folders-root "./passports" \
  --output-root "./output"
```

**With auto-resume:**

```bash
./run_all_review.sh "Option A2 Group 2 - all docs review.xlsx" ./passports ./output
```

---

## Output Structure

### Dynamic Mode Output

```
output/
├── review_results.csv              # Full technical details
├── manual_review_queue.csv         # Items needing human review
├── review_summary.txt              # Statistics
└── renamed-documents/              # Only if --copy-renamed used
    ├── Person One/
    │   ├── Person One_passport_front.jpg
    │   ├── Person One_passport_back.jpg
    │   ├── Person One_passport_blank_01.jpg
    │   └── Person One_photo.jpg
    └── Person Two/
        └── ...
```

### Spreadsheet Mode Output

```
output/
├── Option A2 Group 2 - all docs review_reviewed.xlsx  # Filled Excel
├── reviewed-documents/                                 # Renamed copies
│   ├── Kumar_Ravi_TSF1234/                            # Excel Column L
│   │   ├── Kumar_Ravi_passport_front.jpg              # Excel Column M
│   │   ├── Kumar_Ravi_passport_last.jpg               # Excel Column N
│   │   ├── Kumar_Ravi_passport_blank.jpg              # Excel Column O
│   │   └── Kumar_Ravi_photo.jpg                       # Excel Column P
│   └── {NextPerson}/
│       └── ...
├── review_results.csv              # Full technical details
├── file_actions.csv                # What happened to each file
├── manual_review_queue.csv         # Items needing human review
├── unmatched.csv                   # Folders/rows that didn't match
└── review_summary.txt              # Statistics
```

---

## File Format Handling

| Format                    | Behavior                                | Output                 |
| ------------------------- | --------------------------------------- | ---------------------- |
| **JPG/JPEG**              | ✅ Eligible - reviewed and copied as-is | `.jpg`                 |
| **PNG**                   | ⚠️ Reviewed but marked as Error         | Converted to `.jpg`    |
| **PDF**                   | 📄 Pages rendered and extracted         | Converted to `.jpg`    |
| **Other** (WEBP/TIFF/BMP) | ❌ Not reviewed                         | Copied as-is, flagged  |
| **Voter ID / Visa forms** | 🚫 Detected and ignored                 | Not copied or reviewed |

---

## Filename Keywords

The tool recognizes these keywords in filenames (case-insensitive):

- **Front page**: `front`, `passport front`, `front page`, `first page`, `biodata`, `data page`
- **Back page**: `back`, `passport back`, `last page`, `address page`, `back page`
- **Blank pages**: `blank`, `blank page`, `blank pages`, `visa pages`, `empty pages`
- **Photo**: `photo`, `photograph`, `passport photo`, `passport size`

**Examples:**

- `Ravi_front.jpg` → Front page
- `Ravi-back-page.jpg` → Back page
- `Ravi_blank_01.jpeg` → Blank page
- `Ravi photo.jpg` → Photo

---

## Status Meanings

| Status          | Meaning                                                                |
| --------------- | ---------------------------------------------------------------------- |
| `ok`            | All automated checks passed                                            |
| `Manual review` | Needs human confirmation (ambiguous classification, subjective checks) |
| `Not legible`   | OCR couldn't read required text                                        |
| `Error`         | Definite rule violation detected                                       |
| `Missing`       | Required document not found                                            |

---

## Troubleshooting

### Windows Issues

**Problem: "Python launcher was not found"**

- Solution: Install Python 3.11 from python.org and check "Add to PATH"

**Problem: "PaddlePaddle installation failed"**

- Solution: The tool can still use Tesseract OCR. Install Tesseract from the link above.

**Problem: "Could not save workbook (is it open in Excel?)"**

- Solution: Close the Excel file and re-run with `--resume`

**Problem: Setup script fails**

- Solution: Run as Administrator or check internet connection

### macOS Issues

**Problem: "python3.11: command not found"**

- Solution: Install Python 3.11 via Homebrew: `brew install python@3.11`

**Problem: PaddlePaddle fails on Apple Silicon**

- Solution: Use the alternative installation method in the macOS setup section

**Problem: Permission denied on scripts**

- Solution: Run `chmod +x setup_linux_mac.sh run_all_review.sh`

### Common Issues (Both Platforms)

**Problem: "No person folders were found"**

- Solution: Ensure images are inside person folders, not directly in root:
  ```
  Correct:   passports/Person Name/image.jpg
  Incorrect: passports/image.jpg
  ```

**Problem: "Tesseract executable is unavailable"**

- Solution: This is OK if PaddleOCR loaded successfully. Otherwise, install Tesseract.

**Problem: Process crashes on certain files**

- Solution: Use `--resume` flag to skip problematic files and continue

**Problem: Folder not matched to Excel row**

- Solution: Check `unmatched.csv` for details. Ensure TSF ID or Booking ID is in filenames.

---

## Important Notes

1. ✅ **Original files NEVER modified** - all changes happen in output folder
2. 🔒 **Completely offline** after setup - network blocked during reviews
3. 🎭 **Passport numbers masked** in CSV reports (full numbers in Excel mode)
4. 📊 **Progress saved** after each folder - safe to interrupt and resume
5. 🔄 **PNG → JPG conversion** automatic in output
6. 📄 **PDF → JPG extraction** automatic in output
7. 📝 **Multiple blank pages** numbered: `_blank_01.jpg`, `_blank_02.jpg`, etc.

---

## Getting Help

- Check `REVIEW_RULES.md` for detailed review rules
- Check `SHEET_REVIEW.md` for Excel mode details
- Check `FILENAME_PRIORITY_UPDATE.md` for filename classification rules
- Run `verify_setup.py` to check installation
- Check output CSV files for detailed error messages

---

## Summary

This tool provides two ways to review passport documents:

1. **Dynamic Mode** (`run_review.py`): Quick review without Excel, preserves folder names
2. **Spreadsheet Mode** (`run_sheet_review.py`): Matches to Excel, renames everything per Excel data

Both modes:

- Run completely offline after setup
- Never modify original files
- Use local AI models (PaddleOCR, MediaPipe, OpenCV)
- Generate detailed reports
- Support resume/retry for interrupted runs

Choose the mode that fits your workflow!
