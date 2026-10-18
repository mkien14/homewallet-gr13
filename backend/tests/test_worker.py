import json
import sys

import pytest

from jobs import worker


def test_file_mode_logs_file_metadata_without_aws(tmp_path, monkeypatch, capsys):
    receipt = tmp_path / "receipt.jpg"
    receipt.write_bytes(b"local receipt")
    monkeypatch.setattr(
        worker.boto3,
        "client",
        lambda *args, **kwargs: pytest.fail("file mode must not create an AWS client"),
    )

    monkeypatch.setattr(sys, "argv", ["worker.py", "--file", str(receipt)])
    worker.main()

    event = json.loads(capsys.readouterr().out)
    assert event == {
        "event": "file_processed",
        "path": str(receipt.resolve()),
        "size_bytes": len(b"local receipt"),
    }


def test_poll_once_logs_each_message_before_deleting(capsys):
    events = []
    queue_url = "https://sqs.example.test/queue"

    class FakeSqs:
        def receive_message(self, **kwargs):
            assert kwargs == {
                "QueueUrl": queue_url,
                "MaxNumberOfMessages": 10,
                "WaitTimeSeconds": 20,
                "MessageAttributeNames": ["All"],
            }
            return {"Messages": [{
                "MessageId": "message-1",
                "ReceiptHandle": "receipt-1",
                "Body": '{"receipt_id":42}',
            }]}

        def delete_message(self, **kwargs):
            events.append(json.loads(capsys.readouterr().out))
            events.append(kwargs)

    assert worker.poll_once(FakeSqs(), queue_url) == 1
    assert events == [
        {
            "event": "sqs_message",
            "message_id": "message-1",
            "body": {"receipt_id": 42},
        },
        {"QueueUrl": queue_url, "ReceiptHandle": "receipt-1"},
    ]


def test_missing_local_file_raises():
    with pytest.raises(FileNotFoundError):
        worker.process_file("no-such-receipt.jpg")


def test_non_json_sqs_body_is_logged_as_text(capsys):
    class FakeSqs:
        def receive_message(self, **kwargs):
            return {"Messages": [{
                "MessageId": "message-2",
                "ReceiptHandle": "receipt-2",
                "Body": "plain text",
            }]}

        def delete_message(self, **kwargs):
            pass

    worker.poll_once(FakeSqs(), "queue")

    assert json.loads(capsys.readouterr().out) == {
        "event": "sqs_message",
        "message_id": "message-2",
        "body": "plain text",
    }
