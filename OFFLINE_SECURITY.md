# Offline Security Checklist

Before reviewing real identity documents:

1. Use an organisation-authorised computer and user account.
2. Store source and output folders on an encrypted local drive.
3. Keep the folders outside OneDrive, Google Drive, Dropbox and other sync locations.
4. Complete package and model installation before adding any real documents.
5. Run `python verify_setup.py` successfully while disconnected or firewall-blocked.
6. Block outbound access for the virtual environment's Python executable at operating-system or network level.
7. Do not use the `--allow-network` option for real documents.
8. Restrict read access to source folders and write access to output folders.
9. Do not email reports containing passport numbers.
10. Define a retention period and securely delete temporary/output copies after the authorised review completes.
11. Treat `review_results.csv`, `manual_review_queue.csv` and `renamed-documents` as sensitive PII.
12. Have a human confirm every `Error`, `Not legible` and `Manual review` result before taking action.

## What strict offline mode blocks

The program replaces the process's outbound internet socket functions before loading OCR and visual models. If PaddleOCR attempts a missing-model download, the attempt fails rather than sending a document.

This does not protect against:

- Another process on the machine uploading files.
- Cloud-sync software watching the source/output directories.
- Malware or an already compromised operating system.
- A user explicitly adding `--allow-network`.

Use operating-system firewall, endpoint protection and access controls as the primary security boundary.
