# Worker

From the `backend` directory, process one local file without contacting AWS:

```powershell
python jobs/worker.py --file C:\path\to\receipt.jpg
```

The local mode emits one JSON log line containing the resolved path and file
size. It does not upload or download files, or create SQS/S3 clients.

To long-poll SQS instead, set `SQS_QUEUE_URL` and AWS credentials/region in the
environment, then run:

```powershell
python jobs/worker.py
```

The worker uses 20-second long polling, logs each message as a JSON line, then
deletes that message. `AWS_REGION` is used when set; otherwise it falls back to
`AWS_DEFAULT_REGION` and then `ap-southeast-1`.
