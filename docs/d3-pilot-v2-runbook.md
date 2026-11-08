# D3 pilot v2 runbook

This is a new pilot with a new lock and report. The original files
`ocr-lab/out/d3-pilot-run.json` and `ocr-lab/out/d3-pilot-report.json` are
preserved; never rerun `ocr-lab/d3_pilot.py` or remove its lock. The new runner
uses the same approved test set, `021.jpg`–`030.jpg`, with the corresponding
labels. The team's prior written approval covers both providers and this exact
sample, with Roboflow recorded as the source and no disallowed personal or
financial data.

The new run is fixed to one call per image per provider. Retries are disabled.
Gemini calls are spaced 20 seconds apart to stay under a 3 RPM operational
pace, below the previous Free Tier limit of 5 RPM and leaving room for other
project traffic. A provider error stops
further calls to that provider; the other provider may continue. The output
records successful responses, schema failures, call errors, skipped IDs,
field-level accuracy, usage-based estimated cost, and latency. It never stores
raw model output or receipt text. The `057.jpg` date convention does not affect
this pilot, which contains images 021–030.

## Fix and validation changes

Gemini now receives an explicit JSON response schema. Amazon Nova Lite does not
support Bedrock structured outputs, so it receives the shared JSON instructions
and its response is checked field-by-field by the local parser. Schema checks
cover required keys, types, ISO dates, item structure, and booleans mistakenly
returned as numbers. Parser tests use synthetic JSON only and make no API calls.

## Gates before sending images

1. `ocr-lab/d3-pilot-v2-preflight.json` records the prior group approval and
   source. Confirm that the exact sample and services still match the team's
   approval. No credentials belong in this file.
2. Gemini quota is project/model-specific and cannot be confirmed by the
   read-only model-list API call. In Google AI Studio, open the project's active
   rate limits and usage for `gemini-3.6-flash`; check at least 4 RPM and at
   least 10 requests remaining for the day. Then fill `verified_in_ai_studio`,
`rpm`, `remaining_requests_today`, `checked_utc`, and confirm
`api_key_project_matches` in the preflight JSON. The screenshot provided on
2026-11-08 shows 5 RPM, peak usage 4/5, and 6/20 requests today (14 remaining)
for project HWAPI. Verify that the key in `ocr-lab/.env` belongs to HWAPI in
AI Studio before setting `api_key_project_matches` to true.
   The last field must be a UTC ISO timestamp no more than 24 hours old. Do not
   paste or print the API key.
3. AWS preflight checks STS identity, active APAC inference profile, and
   `bedrock:InvokeModel` through IAM `SimulatePrincipalPolicy` on the profile and
   destination model ARNs. This is a no-inference authorization check. The
   simulation API itself may require `iam:SimulatePrincipalPolicy`. If denied,
   ask the AWS administrator to run that simulation or grant this narrowly
   scoped read-only simulation action. The simulator does not make an actual
   invocation; AWS notes simulation can differ from live evaluation.
4. Run the preflight command and inspect its sanitized status. It sends no
   images. If any check fails, stop and resolve that gate before `--run`.

## Cost and execution

The per-provider planning ceiling is USD 0.50, USD 1.00 total. The runner uses
conservative planning assumptions of 40,000 input and 512 output tokens per
image with USD 0.75 / 1M input and USD 3.75 / 1M output for Gemini, and USD
1.00 / 1M input and USD 5.00 / 1M output for Bedrock. The resulting estimates
are USD 0.3192 for Gemini and USD 0.4256 for Bedrock. They are estimates, not
provider price quotes or billing guarantees; the run report recalculates from
returned token usage. Reconcile actual usage with provider billing after the
run. AWS pricing varies by region and inference route; consult the
[official Bedrock pricing page](https://aws.amazon.com/bedrock/pricing/) on
the run date. Gemini's active limits are shown in
[Google AI Studio](https://aistudio.google.com/).

From the repository root in PowerShell, with the OCR lab environment active:

```powershell
Set-Location ocr-lab
python -m unittest test_d3_pilot_v2.py
python d3_pilot_v2.py --preflight
```

After all preflight checks pass and the quota fields are filled, make the one
authorized run:

```powershell
python d3_pilot_v2.py --run
```

The new lock is `ocr-lab/out/d3-pilot-v2-run.json`; the report is
`ocr-lab/out/d3-pilot-v2-report.json`. Both are ignored by Git. Do not run
`--run` again if it fails or stops partway through. Share the report artifact
with the team without adding secrets or raw receipt/model text.

The conclusion is limited to these ten images and this pilot configuration.
It cannot establish general model superiority or justify changing the
production OCR provider by itself.
