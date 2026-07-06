
## Document identification priority

1. Filename word `front`, `back`, `blank`, or `photo` determines the category.
2. OCR and visual checks validate the contents after filename classification.
3. Content-based classification is used only when the filename has no usable label.
4. Multiple labels in one filename trigger manual review.
5. `black page` is accepted as a compatibility alias for `blank page`.

# Review Rules — Dynamic Local-Only Mode

## Input discovery

- Every immediate subfolder under the supplied passport root is treated as one person.
- No spreadsheet or manifest is read.
- The person folder name is used only as the record label and output-folder name.
- Document categories come from filename labels when present; passport numbers are inferred from local image content.

## Passport front page

- Use the filename word `front` when present; otherwise identify the likely data page using local OCR, MRZ text, passport field labels, and image layout.
- Detect the passport number locally.
- Check blur, contrast, OCR legibility, and visible hands/fingers.
- Ambiguous front-page selection is marked for manual review.

## Address or passport last page

- Use the filename word `back` when present; otherwise identify the likely address page using local OCR terms such as address, father, mother, spouse, and file number.
- Compare its passport number with the number detected from the front page.
- Check image clarity and visible hands/fingers.

## Blank pages

- Use the filename word `blank` when present; otherwise treat remaining passport-page images as blank/visa-page candidates after front, back, and photo are selected.
- Compare passport numbers with the number detected from the front page.
- Check printed page numbers where readable.
- Flag repeated printed page numbers and visually near-identical pages.
- Check clarity and visible hands/fingers.

## Photograph

- Use the filename word `photo` when present; otherwise identify the standalone photograph using dimensions, portrait shape, face detection, and OCR-text density.
- Check exact dimensions of 390 × 567 pixels.
- Check that the photo is 300 DPI (390 × 567 px at 300 DPI = 3.30 × 4.80 cm).
- Check blur, contrast, white background, one face, face placement, face size, head tilt, and visible hands/fingers.
- Jewellery, bindi, full ear visibility, spectacle glare, and frames obscuring the eyes remain manual checks.

## File format

- Every submitted document and the photograph should be a JPG/JPEG file. Any other extension (for example PNG or PDF) is flagged as an error with a comment.

## Privacy

- Processing runs locally.
- Full passport numbers are held only in memory while comparing pages.
- CSV reports contain masked passport numbers only.
- Originals are never modified.
