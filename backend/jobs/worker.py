import argparse
import json
import os
from pathlib import Path

import boto3


def log_json(event):
    print(json.dumps(event, ensure_ascii=False, separators=(",", ":")), flush=True)


def process_file(file_path):
    path = Path(file_path).resolve(strict=True)
    if not path.is_file():
        raise ValueError(f"Not a file: {path}")

    log_json({
        "event": "file_processed",
        "path": str(path),
        "size_bytes": path.stat().st_size,
    })


def poll_once(sqs, queue_url):
    response = sqs.receive_message(
        QueueUrl=queue_url,
        MaxNumberOfMessages=10,
        WaitTimeSeconds=20,
        MessageAttributeNames=["All"],
    )

    messages = response.get("Messages", [])
    for message in messages:
        raw_body = message.get("Body", "")
        try:
            body = json.loads(raw_body)
        except json.JSONDecodeError:
            body = raw_body

        log_json({
            "event": "sqs_message",
            "message_id": message.get("MessageId"),
            "body": body,
        })
        sqs.delete_message(
            QueueUrl=queue_url,
            ReceiptHandle=message["ReceiptHandle"],
        )

    return len(messages)


def run_sqs_worker():
    queue_url = os.getenv("SQS_QUEUE_URL")
    if not queue_url:
        raise ValueError("Set SQS_QUEUE_URL to run the SQS worker")

    region = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or "ap-southeast-1"
    sqs = boto3.client("sqs", region_name=region)
    while True:
        poll_once(sqs, queue_url)


def main():
    parser = argparse.ArgumentParser(description="Homewallet receipt worker")
    parser.add_argument("--file", help="log metadata for one local file without AWS")
    args = parser.parse_args()

    if args.file is not None:
        process_file(args.file)
    else:
        run_sqs_worker()


if __name__ == "__main__":
    main()
