# Filename Priority Update — v0.3.0

This update keeps dynamic person-folder discovery and removes ambiguity when the four image names already identify their purpose.

Recognised filename words, case-insensitively:

- `front` -> passport front/data page
- `back` -> passport back/address/last page
- `blank` -> passport blank/visa page
- `photo` -> standalone photograph

The words can be separated by spaces, underscores, or hyphens. Examples: `front.jpg`, `Ravi_front.jpeg`, `Ravi-back-page.jpg`, `Ravi blank 1.jpg`, and `Ravi_photo.jpeg`.

The filename category is authoritative. OCR and local computer vision validate readability, passport-number consistency, dimensions, blur, background, face placement, and hands. Content-based category detection runs only for files without a recognised label.

`black page` is accepted as a compatibility alias for a likely `blank page` typo. The bare word `black` is not accepted.

After copying the update over the existing project, rerun the existing command; model setup is not required again.
