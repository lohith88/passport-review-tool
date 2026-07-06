# Spreadsheet Review — fill Sheet1 from an offline review

Reviews each person folder locally and writes the results back into the workbook
(`Sheet1`), matching every folder to its row and renaming folders/files to the
names in the sheet. Nothing is sent to any cloud service.

## Run

Use the auto-resuming launcher (recommended — it restarts and skips a file that
crashes a native library):

```powershell
& ".\run_all_review.bat" ".\Option A2 Group 2 - all docs review.xlsx" ".\passports" ".\passports_output"
```

Single pass (no auto-resume):

```powershell
.\.venv\Scripts\python.exe run_sheet_review.py `
  --workbook ".\Option A2 Group 2 - all docs review.xlsx" `
  --folders-root ".\passports" `
  --output-root ".\passports_output" `
  --config config.example.json
```

Useful flags: `--limit 2` (first two folders only), `--no-copy` (fill the sheet
but do not create the renamed copies), `--resume` (continue a previous run,
skipping done and crashed folders), `--show-pii-in-console` (print folder names).

## Resilience

Progress is saved after every folder into `<output>\<name>_reviewed.xlsx`. If a
file crashes the process (some PDFs can crash the native libraries), re-running
with `--resume` continues where it left off and skips the offending folder.
`run_all_review.bat` does this looping for you automatically.

## How a folder is matched to a row

In priority order:

1. **Passport number** read from the front page → column E (`Passport No. Front`).
2. **TSF ID** found in a file name → column B.
3. **Booking ID** found in a file name → column A.
4. **Person name** → column D (last resort; flagged for manual confirmation).

Folders that match no row, and rows that match no folder, are listed in
`unmatched.csv`.

## What gets written into Sheet1

| Column | Meaning | Value |
|--------|---------|-------|
| `Passport Front Page Review` (appended) | front/data-page review | `ok` / `Error` / `Not legible` |
| F `Passport No. Back` | address/last-page review | `ok` / `Error` / `Not legible` |
| G `Passport No. Blank Pages` | blank-pages review | `ok` / `Error` / `Not legible` |
| H `Photo Dimension (390 x 567)` | whole-photo review | `ok` / `Error` / `Not legible` |
| I `Any comments for errors` | consolidated comments | full numbers (local only) |
| `Email (re-upload request)` (appended) | draft message to the applicant | text, or blank |

The two appended columns are added automatically at the end of the row (so the
existing `=CONCATENATE(...)` formula columns are not shifted).

`Error` covers a rule failure, a missing document, an ineligible format, or an
item that needs the human second check. Jewellery/bindi, ear visibility and
glasses glare cannot be judged automatically and are added to the comments.

**Address/blank pages and the old passport number.** A passport number that differs
from the front page is **not** an error by itself — those pages normally carry the
**old/previous** passport number above the current one (which sits below the
barcode). The blank-page number is often dot-printed and can appear mirrored, so
OCR frequently cannot read it; that is marked `Not legible` and flagged in the
comments as **verify manually** (it is not put in the re-upload email).

## File format rules

- **JPG / JPEG** — eligible; reviewed and copied as-is.
- **PNG** — reviewed, but marked `Error` (not an eligible format) with a comment;
  **converted to JPG** in the output copy.
- **PDF** — the page(s) are **rendered and extracted to JPG**, then reviewed like an
  image (the output copy is a `.jpg`).
- **Any other format** (WEBP/TIFF/BMP/...) — not reviewed; copied as-is and flagged.
- **Voter ID / China visa form / other non-passport files** — detected by file name
  or OCR content and **ignored entirely** (never classified, renamed, or copied).
  Tunable via `exclude_filename_keywords` / `exclude_content_terms` in the config.

**Photo resolution** — the photo should be 300 DPI (390 × 567 px = 3.30 × 4.80 cm).
Wrong or missing DPI is flagged. Tunable in the config (`convert_png_to_jpeg`,
`jpeg_extensions`, `required_photo_dpi`, `mask_passport_numbers`).

## Email column

For each person with any issue, the tool drafts a re-upload request addressed by
name (column D), listing only the documents that need re-sending — image-quality,
format, missing, or wrong-photo problems. Documents that only need a manual number
check (e.g. an unreadable blank-page number) are **not** included.

The original workbook and the original folders are **never modified**. Results are
written to `<name>_reviewed.xlsx` in the output folder.

## Renamed copies (in the output — originals untouched)

Each matched folder's documents are **copied** into
`<output>\reviewed-documents\<Folder Name (L)>\` with the file names from columns
M = Front, N = Last, O = Blank Pages, P = Photo. PNGs are converted to JPG; PDFs
and other formats are copied as-is. Pass `--no-copy` to skip creating copies.

## Outputs (in the output folder)

- `<name>_reviewed.xlsx` — the filled workbook (formulas preserved)
- `reviewed-documents\` — renamed copies (PNG→JPG, PDF→JPG), one folder per person
- `review_results.csv` — full per-document detail and technical measurements
- `file_actions.csv` — per source file: kept / converted PNG→JPG / extracted PDF→JPG / copied as-is / **ignored** (voter ID, visa, ...), with the output file name
- `manual_review_queue.csv` — only the folders needing attention
- `unmatched.csv` — folders with no row and rows with no folder
- `review_summary.txt` — counts by outcome

## Notes

- Requires `openpyxl` (already added to `requirements.txt`).
- File names should embed the document type (`Front`, `Back`, `Blank`, `Photo`);
  `PassportBack`, `Passport_Back`, and `passport back` are all recognised.
- Matching is by content (passport number / TSF ID), so it works even if the
  person folders are named arbitrarily.
