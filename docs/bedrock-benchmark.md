# D3 / #34: Gemini and Amazon Bedrock pilot

**Status (2026-11-10): PARTIAL.** Both image pilots are consumed; no paired OCR
accuracy comparison is available. CloudTrail confirmed the old Bedrock denial
was caused by the regional guard in `homewallet-dev-d1-testing:v3`. Current v4
already fixes that guard. The preflight's destination-region context is now
fixed; current Hoang IAM simulation allows all seven resources, and one small
synthetic text call by Kien returned HTTP 200. Hoang's live identity is still
unverified because his AWS profile is absent on this machine.

See [current remediation and remaining gates](acceptance/34-bedrock-remediation-20261110.md)
and [sanitized evidence](acceptance/34-bedrock-diagnosis-20261110.json).
The historical results below remain unchanged. **Do not rerun either old pilot**;
the tracked run ledger now blocks them even without ignored local lock files.

**Prepared:** 2026-11-07; updated 2026-11-10

## Approved scope and data

The team confirmed in writing on 2026-11-07 that images `021.jpg` through
`030.jpg` and their labels may be sent to Google Gemini and Amazon Bedrock, and
that they contain no personal or financial data that may not be shared. The
user identified images 1–31 as sourced from Roboflow and images 31 onward as
sourced from a thread. The ten pilot images are therefore recorded as
`Roboflow` in `ocr-lab/labels.csv`. Image 031 is outside this pilot and the
overlap in the source ranges does not affect it.

Only the ten pilot images may be used: one request per image per provider,
automatic retries disabled, no reruns, no expansion to 42 images. The total
operational ceiling is USD 1.00, with at most USD 0.50 per provider. Image 057's
date label remains literal `None`; it is excluded only from date accuracy.

## Access and model configuration

The approved AWS identity is account `179923444714`, user `hoang`; the AWS
profile is `homewallet-d3-pilot` in `ap-southeast-1`. The user verified STS
identity and read access to inference profile `apac.amazon.nova-lite-v1:0`,
which returned `ACTIVE` / `SYSTEM_DEFINED`. The admin reported invocation
permissions assigned. The profile read does not prove invocation access; the
pilot's first Bedrock request will test it. Gemini key/model availability was
verified with a read-only model-list check; the local model is
`gemini-3.6-flash`.

The prepared runner estimates maximum spend before the run using a conservative
planning allowance of 45,000 input and 256 output tokens per image. Rates used
for this operational estimate are USD 0.75 / 1M input and USD 3.75 / 1M output
for Gemini, and USD 1.00 / 1M input and USD 5.00 / 1M output for Bedrock. This
gives USD 0.3471 for Gemini and USD 0.4628 for Bedrock, below each ceiling.
These allowances are not a provider quote or billing guarantee; the report
calculates estimated usage cost from returned token counts. Actual cost should
be reconciled with provider billing. The runner stops a provider if its
usage-based estimate exceeds USD 0.50.

## Runner and report

`ocr-lab/d3_pilot.py` fixes the input to `data_small/021.jpg`–`030.jpg`, checks
the source and test labels, uses one shared prompt and JSON schema, and records
only per-image correctness flags, schema validity, latency, token usage,
request count, and estimated cost. It does not persist model text or receipt
contents. Gemini and Bedrock SDK retries are set to one total attempt. A local
one-shot lock is created before the first inference; its presence permanently
blocks reruns, including after a partial failure. The report and lock are
written under ignored `ocr-lab/out/`.

This runner is archived as consumed. Its tracked history gate runs before any
provider access. Use the current remediation document for the separate small
access check; a new image pilot needs a separately approved run identity.
Historical report/lock paths below describe the artifacts recorded at run time;
those ignored files are not present in this main checkout on 2026-11-10. Obtain
the originals from the operator's machine rather than reconstructing them.

## Evidence and decision

### Original pilot attempt (2026-11-07)

On 2026-11-07, the one-shot run made seven Gemini request attempts. Six
returned responses with usage; the seventh was rejected with HTTP 429 due to
the Gemini Free Tier per-minute request quota. Automatic retries were zero.
The runner did not pause between calls, so it was not paced for the reported
five-requests-per-minute quota. The six returned responses all failed the
runner's JSON schema validation. Since raw response text was deliberately not
saved, the cause of the malformed responses cannot be diagnosed from this run.
The local report records 7,200 input tokens, 41 output tokens, and USD 0.005554
estimated usage cost for the six responses, whose field-accuracy flags are not
usable as OCR accuracy results. Bedrock has zero attempts. The one-shot guard is now
consumed; do not rerun the runner or resend any Gemini images. The local report
is at `ocr-lab/out/d3-pilot-report.json` and the guard is at
`ocr-lab/out/d3-pilot-run.json` (both ignored by Git).

### Approved v2 pilot attempt (2026-11-08)

The v2 preflight passed for the exact 10-image sample. Its one authorized run
started at 2026-11-08 11:19:05 UTC and stopped at 11:19:52 UTC after about 46.4
seconds with status `complete_with_failures`; retries were zero. Gemini made 3
of 10 planned requests: two API responses contained invalid JSON, one request
returned 503, and the remaining seven images were skipped. Bedrock made 1 of 10 planned
requests: image 021 returned `AccessDeniedException`, and the remaining nine
images were skipped. This runtime denial occurred even though the preflight
IAM simulation allowed the inference profile and all six destination model
resources.

Gemini recorded 2,396 input tokens and 9 output tokens, with an estimated cost
of USD 0.001831. Its three request latencies were 8.334, 4.361, and 6.358
seconds. Bedrock returned no token usage; the report's USD 0 estimate does not
replace billing reconciliation. Its denied request took 8.844 seconds. The
report marks field accuracy as 0/10 because errors and skipped samples count
as incorrect for end-to-end coverage. That is not a measure of OCR accuracy
on valid predictions: Gemini produced no schema-valid prediction and Bedrock
produced none. The detailed machine report and one-shot lock remain in ignored
`ocr-lab/out/d3-pilot-v2-report.json` and
`ocr-lab/out/d3-pilot-v2-run.json`; no raw model text is stored.

The existing `out/` predictions are only two dev examples per provider, with
unknown model version, date, pricing, region, and retry history. They are not
test-set benchmark evidence. No provider change is supported until the paired
pilot is completed and reviewed. The pilot does not measure item descriptions,
quantities, or category accuracy.

The least-privilege policy draft is in
[`bedrock-d3-pilot-policy.template.json`](bedrock-d3-pilot-policy.template.json).
