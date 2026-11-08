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

For D3 benchmark status, evidence, and the access/cost/data gates, see
[`docs/bedrock-benchmark.md`](../docs/bedrock-benchmark.md) from the repository root.

`d3_pilot.py` and its `out/d3-pilot-*` artifacts are the frozen original
attempt. Never run that script again. The newly approved pilot uses
`d3_pilot_v2.py`, writes separate `out/d3-pilot-v2-*` artifacts, and refuses to
infer until sharing approval, Gemini quota, and Bedrock access checks pass.
Follow [`docs/d3-pilot-v2-runbook.md`](../docs/d3-pilot-v2-runbook.md).
