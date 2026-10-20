import argparse
import json
import os
import sys
from pathlib import Path

import boto3

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jobs import pipeline


MAX_RECEIVE_COUNT = 3


def log_json(event):
    print(json.dumps(event, ensure_ascii=False, separators=(",", ":")), flush=True)


def _decode_message(raw_body):
    try:
        body = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise ValueError("SQS message body is not valid JSON") from exc
    if not isinstance(body, dict):
        raise ValueError("SQS message body must be a JSON object")
    return body


def _message_keys(body):
    if body.get("Event") == "s3:TestEvent":
        return []
    records = body.get("Records")
    if not isinstance(records, list):
        raise ValueError("S3 notification must contain Records")
    keys = []
    for record in records:
        try:
            keys.append(record["s3"]["object"]["key"])
        except (KeyError, TypeError) as exc:
            raise ValueError("Malformed S3 notification record") from exc
    return keys


def process_message(body, *, config=None, s3_client=None):
    if body.get("Event") == "s3:TestEvent":
        return {"test_event": True, "results": []}

    records = body.get("Records")
    if not isinstance(records, list):
        raise ValueError("S3 notification must contain Records")

    results = []
    for record in records:
        try:
            bucket = record["s3"]["bucket"]["name"]
            key = record["s3"]["object"]["key"]
        except (KeyError, TypeError) as exc:
            raise ValueError("Malformed S3 notification record") from exc

        decoded_key = pipeline.unquote_plus(key)
        try:
            results.append(pipeline.process_receipt(
                {"bucket": bucket, "key": decoded_key},
                config=config,
                s3_client=s3_client,
            ))
        except pipeline.ReceiptNotFound:
            results.append({"key": decoded_key, "not_found": True})
    return {"test_event": False, "results": results}


def poll_once(sqs, queue_url, *, config=None, s3_client=None):
    response = sqs.receive_message(
        QueueUrl=queue_url,
        MaxNumberOfMessages=1,
        WaitTimeSeconds=20,
        AttributeNames=["ApproximateReceiveCount"],
    )
    messages = response.get("Messages", [])
    if not messages:
        return 0

    message = messages[0]
    message_id = message.get("MessageId")
    attributes = message.get("Attributes") or {}
    receive_count = int(attributes.get("ApproximateReceiveCount", "1"))
    try:
        body = _decode_message(message.get("Body", ""))
        result = process_message(body, config=config, s3_client=s3_client)
    except Exception as exc:
        log_json({
            "event": "sqs_message_failed",
            "message_id": message_id,
            "receive_count": receive_count,
            "error": type(exc).__name__,
            "message": str(exc)[:300],
        })
        if receive_count >= MAX_RECEIVE_COUNT:
            try:
                body = _decode_message(message.get("Body", ""))
                for key in _message_keys(body):
                    pipeline.mark_receipt_failed(
                        pipeline.unquote_plus(key),
                        "WORKER_MAX_ATTEMPTS",
                        config=config,
                    )
            except Exception as mark_error:
                log_json({
                    "event": "receipt_failure_mark_failed",
                    "message_id": message_id,
                    "error": type(mark_error).__name__,
                    "message": str(mark_error)[:300],
                })
                raise
            raise
        return 1

    log_json({
        "event": "sqs_message",
        "message_id": message_id,
        "result": result,
    })
    sqs.delete_message(
        QueueUrl=queue_url,
        ReceiptHandle=message["ReceiptHandle"],
    )
    return 1


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
    parser.add_argument("--file", help="process a local receipt without SQS or S3")
    parser.add_argument("--household-id", type=int)
    parser.add_argument("--user-id", type=int)
    args = parser.parse_args()

    if args.file:
        if (args.household_id is None) != (args.user_id is None):
            parser.error("--household-id and --user-id must be provided together")
        result = pipeline.process_file(
            args.file,
            household_id=args.household_id,
            user_id=args.user_id,
        )
        log_json({"event": "file_processed", "result": result})
    else:
        if args.household_id is not None or args.user_id is not None:
            parser.error("--household-id and --user-id require --file")
        run_sqs_worker()


if __name__ == "__main__":
    main()
