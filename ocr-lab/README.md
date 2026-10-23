# OCR Lab

Keep this project’s Python dependencies separate from the backend environment.
From the repository root, create the OCR lab environment and install its
dependencies with:

```powershell
py -m venv ocr-lab\.venv
.\ocr-lab\.venv\Scripts\Activate.ps1
python -m pip install -r ocr-lab\requirements.txt
```

The environment is local and ignored by Git. Do not install OCR lab
dependencies into `backend\.venv`.
