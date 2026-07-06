# Passport Review Tool — Dynamic Local-Only Version

This version reviews person-wise passport folders **without using a manifest, spreadsheet, booking ID, expected folder name, or expected passport number**.

Everything runs locally after setup. No passport image or photograph is sent to a cloud service.

## Required folder structure

The input root contains one immediate subfolder for each person:

```text
passports\
├── Person One\
│   ├── IMG_001.jpg
│   ├── IMG_002.jpg
│   ├── IMG_003.jpg
│   └── photo.jpg
├── Person Two\
│   ├── DSC_1001.jpeg
│   ├── DSC_1002.jpeg
│   └── DSC_1003.jpeg
└── Person Three\
    └── ...
```

The program now gives first priority to the document-type word in each filename. Use filenames containing these standalone words:

- `front` — passport front/data page
- `back` — passport address/last page
- `blank` — blank/visa page
- `photo` — standalone photograph

Examples: `Ravi_front.jpeg`, `Ravi-back-page.jpg`, `Ravi_blank_01.jpeg`, and `Ravi photo.jpg`. Matching is case-insensitive, and underscores/hyphens are treated as spaces. The phrase `black page` is also accepted as a compatibility alias for an accidental `blank page` typo.

The program:

1. Discovers every immediate person folder automatically.
2. Opens all supported images inside that folder.
3. Uses the filename word as the authoritative document category.
4. Uses local OCR and image analysis to validate the selected front, back, blank page, and photo.
5. Uses content-based classification only when a file does not contain a usable filename label.
6. Detects the passport number from the submitted passport images.
7. Compares that detected number across the address page and blank pages.
8. Writes masked passport numbers to reports.
9. Creates standardized copies without changing the originals.

Supported inputs: `.jpg`, `.jpeg`, `.png`, `.webp`, `.tif`, `.tiff`, `.bmp`, and `.pdf`.

## Filename classification rules

A filename containing exactly one recognised document-type label is authoritative, even if OCR content scoring suggests another category. For example, `ABC_front.jpeg` is always treated as the front page. OCR then verifies readability and passport-number consistency.

A filename such as `front_photo.jpeg` contains conflicting labels. It is not trusted automatically; the tool falls back to content analysis and adds a manual-review note. A word is matched as a complete word, so `back` does not accidentally match `background`.

When a filename contains none of the recognised labels, the tool retains the previous content-based fallback. Ambiguous cases are marked `Manual review`, and classification evidence is written to the report.

Jewellery, bindi, complete ear visibility, spectacle glare, and frames obstructing the eyes remain human-confirmation checks.

## Updating an already installed copy

You previously installed the manifest-based version. To retain the existing virtual environment and downloaded local models:

1. Close any running review command.
2. Back up the old project folder if required.
3. Extract the new ZIP.
4. Copy all files from the new `passport_review_tool_local` folder into your existing project folder.
5. Choose **Replace the files in the destination** when Windows asks.
6. Do not delete your existing `.venv` folder or downloaded files inside `models`.

There is no need to run model setup again when `.venv` and the downloaded model files are retained.

## First test — two person folders

Open PowerShell in the project directory and run:

```powershell
& ".\launch_test_2_people.bat" ".\passports" ".\passports_output"
```

For your current full paths, use:

```powershell
& ".\launch_test_2_people.bat" "D:\lohith\kailash yatra\passport_review_tool_local_only\passport_review_tool_local\passports" "D:\lohith\kailash yatra\passport_review_tool_local_only\passport_review_tool_local\passports_output"
```

Quotation marks are mandatory because `kailash yatra` contains a space.

Expected beginning of the output:

```text
Person folders discovered dynamically: 2
Strict offline mode enabled...
OCR engine: paddleocr
Local MediaPipe face/hand models loaded.
[1/2] Reviewing person folder 1...
[2/2] Reviewing person folder 2...
```

It should no longer display `1/65` or refer to manifest rows.

## Review all person folders

```powershell
& ".\launch_review.bat" ".\passports" ".\passports_output"
```

Or with full paths:

```powershell
& ".\launch_review.bat" "D:\lohith\kailash yatra\passport_review_tool_local_only\passport_review_tool_local\passports" "D:\lohith\kailash yatra\passport_review_tool_local_only\passport_review_tool_local\passports_output"
```

## Direct Python command

```powershell
.\.venv\Scripts\Activate.ps1
python .\run_review.py `
  --folders-root ".\passports" `
  --output-root ".\passports_output" `
  --config ".\config.example.json" `
  --copy-renamed `
  --limit 2
```

Remove `--limit 2` to process all person folders.

## Output files

```text
passports_output\
├── review_results.csv
├── manual_review_queue.csv
├── review_summary.txt
└── renamed-documents\
    ├── Person One\
    │   ├── Person One_passport_front.jpg
    │   ├── Person One_passport_back.jpg
    │   ├── Person One_passport_blank_01.jpg
    │   └── Person One_photo.jpg
    └── Person Two\
        └── ...
```

The reports contain:

- Person folder name
- Masked detected passport number
- Passport-number confidence
- Automatically selected front, back, blank-page, and photo files
- Review status for each document category
- Photo-dimension result
- Comments explaining ambiguous or failed checks
- Technical measurements and classification evidence

Full passport numbers are not written to CSV reports.

## Status meanings

- `ok`: automated checks passed.
- `Error`: a definite mismatch or rule failure was detected.
- `Not legible`: required text or number could not be read.
- `Manual review`: classification or a subjective rule needs human confirmation.
- `Missing`: a required document category was not found.

## Local-only components

- PaddleOCR: local text recognition
- Tesseract: optional local OCR fallback
- OpenCV: dimensions, blur, contrast, white-background and duplicate-page checks
- MediaPipe: local face landmarks and hand/finger detection

The process-level network block is enabled during reviews unless `--allow-network` is deliberately supplied.

## Troubleshooting

### It says no person folders were found

Confirm that images are inside person folders, not directly inside the root:

```text
Correct:   passports\Person Name\image.jpg
Incorrect: passports\image.jpg
```

List the detected folders in PowerShell:

```powershell
Get-ChildItem -LiteralPath ".\passports" -Directory | Select-Object Name
```

### It processes the wrong number of folders

The two-person BAT file processes the first two immediate subfolders alphabetically. The full BAT file processes every immediate subfolder.

### Tesseract warning

This warning is acceptable when PaddleOCR loads successfully:

```text
Tesseract executable is unavailable
OCR engine: paddleocr
```

### Model cache messages

Messages saying that PaddleOCR model files already exist and cached files are being used are expected and confirm that the models are local.
