"""Store a newly rotated Gemini API key in an existing AWS Secrets Manager secret.

The key is read without terminal echo and is never included in output. This does
not revoke the old key; revoke it in the Google project first.
"""

from __future__ import annotations

import argparse
import getpass
import sys

import boto3
from botocore.exceptions import BotoCoreError, ClientError


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--secret-id", required=True, help="Explicit existing secret name or ARN; no implicit dev target")
    parser.add_argument("--expected-account", default="179923444714")
    parser.add_argument("--region", default="ap-southeast-1")
    parser.add_argument("--profile", help="AWS CLI profile; omit to use the default chain")
    args = parser.parse_args()

    key = confirm = ""
    try:
        session = boto3.Session(profile_name=args.profile, region_name=args.region)
        if session.client("sts").get_caller_identity()["Account"] != args.expected_account:
            print("Wrong AWS account; nothing changed.", file=sys.stderr)
            return 2
        client = session.client("secretsmanager")
        # Verify the target exists before writing. Do not retrieve or print its value.
        secret = client.describe_secret(SecretId=args.secret_id)
        if secret.get("DeletedDate") or secret["ARN"].split(":")[4] != args.expected_account:
            print("Secret target is not active in the expected account; nothing changed.", file=sys.stderr)
            return 2
        key = getpass.getpass("New Gemini API key (input hidden): ").strip()
        confirm = getpass.getpass("Re-enter new key to confirm (input hidden): ").strip()
        if not key or key != confirm:
            print("Empty or mismatched entries; nothing changed.", file=sys.stderr)
            return 2
        result = client.put_secret_value(SecretId=args.secret_id, SecretString=key)
    except (BotoCoreError, ClientError) as exc:
        print(f"Secrets Manager update failed ({type(exc).__name__}); key not printed.", file=sys.stderr)
        return 1
    finally:
        key = ""
        confirm = ""

    print("Secret version stored successfully.")
    print(f"Secret ARN: {secret['ARN']}")
    print(f"Version ID: {result['VersionId']}")
    print("No secret value was displayed. Restart/redeploy consumers if they cache secret values.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
