"""One real #37 budget email to an operator-readable mailbox, then cleanup.

Default mode asks the operator to confirm the new email's actual contents.
--send-only records transport evidence without claiming mailbox acceptance.
"""

import argparse
import getpass
import hashlib
import importlib.util
import json
import re
import uuid
from pathlib import Path


spec = importlib.util.spec_from_file_location("d1_mail_shared", Path(__file__).with_name("run-chi43-runtime-acceptance.py"))
shared = importlib.util.module_from_spec(spec)
spec.loader.exec_module(shared)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--recipient", help="Prefer the hidden interactive prompt on a shared terminal.")
    parser.add_argument("--send-only", action="store_true")
    parser.add_argument("--cleanup-from", type=Path)
    args = parser.parse_args()
    result = {"run_id": uuid.uuid4().hex[:12], "started_utc": shared.now(), "status": "STARTED",
              "api": [], "runtime_tasks": [], "mailbox_confirmed": False,
              "email_send_limit": 1, "push_send_limit": 0, "scheduler_changes": 0}
    if args.cleanup_from:
        previous = json.loads(args.cleanup_from.read_text(encoding="utf-8"))
        shared.require(re.fullmatch(r"[0-9a-f]{12}", previous["run_id"]) is not None, "invalid_previous_run")
        result["run_id"] = previous["run_id"]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2)
    def checkpoint():
        args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    runner, attempted = None, False
    fixture = {"run_id": result["run_id"], "household_id": 0, "vi_user_id": 0, "en_user_id": 0}
    try:
        recipient = None
        if not args.cleanup_from:
            recipient = (args.recipient or getpass.getpass("Email you can read (hidden): ")).strip()
            shared.require(len(recipient) <= 254 and re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", recipient) is not None,
                           "invalid_recipient")
            result["recipient_sha256"] = hashlib.sha256(recipient.lower().encode()).hexdigest()
        runner = shared.Runner(result, runtime_source=Path(__file__).with_name("budget-mailbox-runtime.py"),
                               event_prefix="D1MAIL", checkpoint=checkpoint)
        runner.task_definition = "hw-jobs:3"
        runner.runtime_container = "jobs"
        runner.runtime_log_group = "/ecs/hw-jobs"
        runner.runtime_log_prefix = "scheduled"
        if not args.cleanup_from:
            attempted = True
            runner.runtime("prepare", fixture, admin=True, extra_args=["--recipient", recipient])
            events = runner.runtime("exercise", fixture)
            sent = next((event for event in events if event["event"] == "D1MAIL_SEND_PASS"), None)
            shared.require(sent is not None, "send_pass_event_missing")
            result["delivery"] = sent
            marker = "D1 Acceptance " + result["run_id"][:6]
            result["expected_subject_marker"] = marker
            if not args.send_only:
                print("Open the NEW email containing: " + marker, flush=True)
                print("Check: Vietnamese budget alert at 80%, the same marker, and the HomeWallet link/instructions.", flush=True)
                answer = input("Did you receive and verify this exact new email? Type y only if all checks pass: ").strip().lower()
                result["mailbox_confirmed"] = answer == "y"
                if result["mailbox_confirmed"]:
                    result["mailbox_confirmed_utc"] = shared.now()
    except Exception as exc:
        result.update(status="FAILED", error_type=type(exc).__name__)
        if type(exc) is RuntimeError and re.fullmatch(r"[a-z0-9_]+", str(exc)):
            result["reason"] = str(exc)
    finally:
        if runner and (attempted or args.cleanup_from):
            try:
                runner.runtime("cleanup", fixture, admin=True)
                result["cleanup"] = "PASS"
            except Exception as exc:
                result.update(cleanup="FAILED", cleanup_error_type=type(exc).__name__)
        if args.cleanup_from and result.get("cleanup") == "PASS":
            result["status"] = "CLEANUP_PASS"
        elif result.get("delivery") and result.get("cleanup") == "PASS":
            result["status"] = "PASS" if result["mailbox_confirmed"] else "SENT_AWAITING_MAILBOX_CONFIRMATION"
        elif result["status"] == "STARTED":
            result["status"] = "PARTIAL"
        result["finished_utc"] = shared.now()
        checkpoint()
        shared.progress("D1MAIL_RESULT_WRITTEN", status=result["status"], output=str(args.output))
    return 0 if result["status"] in {"PASS", "CLEANUP_PASS", "SENT_AWAITING_MAILBOX_CONFIRMATION"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
