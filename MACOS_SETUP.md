# macOS setup & run

This repo contains **code only** — no passport data or workbook. You copy those to
the Mac separately (see step 4).

## 1. Prerequisites

Install [Homebrew](https://brew.sh) if you don't have it, then:

```bash
brew install python@3.11 git tesseract
```

- **Python 3.11** — PaddlePaddle/PaddleOCR wheels target 3.11.
- **tesseract** — optional OCR fallback (PaddleOCR is the primary engine).

## 2. Clone

```bash
git clone https://github.com/lohith88/passport-review-tool.git
cd passport-review-tool
```

## 3. Set up the environment (one time, needs internet)

```bash
chmod +x setup_linux_mac.sh run_all_review.sh
./setup_linux_mac.sh
```

This creates `.venv`, installs PaddlePaddle + the Python dependencies, and downloads
the local OCR + MediaPipe models. After it prints *"Local model setup is complete"*
you can work fully offline.

> **Apple Silicon (M1/M2/M3):** if `paddlepaddle==3.2.0` fails to install, try
> `pip install paddlepaddle` (latest) inside the venv, then
> `pip install -r requirements.txt` and `python setup_local_models.py`.

## 4. Copy your data onto the Mac (kept out of git on purpose)

```
<repo>/
├── Option A2 Group 2 - all docs review.xlsx     <- copy the workbook here
└── passports/                                    <- create this and put person folders inside
    ├── <Person One>/  (their front/back/blank/photo files)
    ├── <Person Two>/
    └── ...
```

## 5. Run

```bash
./run_all_review.sh "Option A2 Group 2 - all docs review.xlsx" ./passports ./passports_output
```

It auto-resumes past any file that crashes a native library, so it always finishes.
Results appear in `./passports_output/`:

- `…_reviewed.xlsx` — the filled workbook
- `reviewed-documents/` — renamed copies (PNG→JPG, PDF→JPG; voter-ID/visa ignored)
- `file_actions.csv` — per source file: kept / converted / extracted / ignored
- `review_results.csv`, `manual_review_queue.csv`, `unmatched.csv`, `review_summary.txt`

To fill the sheet without creating copies, add `--no-copy`. To try a few folders
first, run `run_sheet_review.py` directly with `--limit 5` (see `SHEET_REVIEW.md`).

## Notes

- The review runs **offline** — a process-level network block is on by default.
- Nothing is uploaded anywhere; all processing is local.
