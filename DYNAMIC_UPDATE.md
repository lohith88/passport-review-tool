# Dynamic Scan Update

This release removes the external manifest requirement.

Use this structure:

```text
passports\Person Name\*.jpg
```

Run two folders:

```powershell
& ".\launch_test_2_people.bat" ".\passports" ".\passports_output"
```

Run all folders:

```powershell
& ".\launch_review.bat" ".\passports" ".\passports_output"
```

The program discovers the folders, files, document types, and passport number dynamically.

## Filename-priority update (v0.3.0)

Files containing the standalone words `front`, `back`, `blank`, or `photo` are now classified directly from the filename. OCR and computer vision validate the file after classification. Files without those words continue to use content-based fallback. The compatibility phrase `black page` is also accepted as `blank page`.
