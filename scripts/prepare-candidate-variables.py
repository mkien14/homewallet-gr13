"""Prepare PUBLIC GitHub repository variables; no secret retrieval or AWS writes."""
import argparse
import base64
import json
import re
from pathlib import Path
import subprocess

import boto3


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--support-email", default="homewallet26@gmail.com")
    args = parser.parse_args()
    account = boto3.client("sts").get_caller_identity()["Account"]
    if account != "179923444714":
        raise ValueError("Wrong AWS account")
    response = subprocess.run(["terraform", "-chdir=infra/envs/dev", "output", "-json"],
                              check=True, capture_output=True, text=True, encoding="utf-8")
    outputs = json.loads(response.stdout)
    values = {
        "PRODUCTION_COGNITO_DOMAIN": outputs["cognito_hosted_ui"]["value"].removeprefix("https://").rstrip("/"),
        "PRODUCTION_COGNITO_CLIENT_ID": outputs["cognito_spa_client_id"]["value"],
        "PRODUCTION_COGNITO_USER_POOL_ID": outputs["cognito_user_pool_id"]["value"],
        "PRODUCTION_SUPPORT_EMAIL": args.support_email,
    }
    # Read only the explicitly public key, never copy the environment file.
    local = Path("frontend/.env.local")
    match = re.search(r"^\s*VITE_VAPID_PUBLIC_KEY\s*=\s*(.+?)\s*$", local.read_text(encoding="utf-8-sig") if local.exists() else "", re.M)
    if not match:
        raise ValueError("Public VAPID key missing in frontend/.env.local")
    key = match[1].strip().strip("\"'")
    if not re.fullmatch(r"[A-Za-z0-9_-]+={0,2}", key):
        raise ValueError("Invalid public VAPID key format")
    decoded = base64.urlsafe_b64decode(key + "=" * (-len(key) % 4))
    if len(decoded) != 65 or decoded[0] != 4:
        raise ValueError("Expected an uncompressed P-256 PUBLIC key")
    values["PRODUCTION_VAPID_PUBLIC_KEY"] = key
    if not re.fullmatch(r"[^ @]+@[^ @]+\.[^ @]+", args.support_email):
        raise ValueError("Invalid support mailbox")
    destination = Path(args.output)
    with destination.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(values, indent=2) + "\n")
    print(json.dumps({"status": "PUBLIC_VARIABLES_PREPARED", "names": sorted(values), "output": str(destination)}))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(json.dumps({"status": "FAILED", "error_type": type(error).__name__}))
        raise SystemExit(1)
