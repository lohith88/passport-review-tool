# Third-Party Components

This project does not redistribute model binaries. The setup script downloads official model files to the local `models` directory.

- PaddleOCR and PaddlePaddle: local optical character recognition.
- MediaPipe Face Landmarker: local face detection and facial landmarks; not identity recognition.
- MediaPipe Hand Landmarker: local hand/finger-region detection.
- OpenCV: image quality and supporting vision checks.
- Tesseract/pytesseract: optional local OCR fallback.
- pypdfium2/PDFium: local PDF rendering.

Review the licences and your organisation's software approval requirements before deployment. The project contains no cloud AI SDK or API integration.
