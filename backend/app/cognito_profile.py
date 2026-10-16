import json
import urllib.request

import boto3
from botocore import UNSIGNED
from botocore.config import Config


def fetch_email(access_token, claims, cfg):
    scopes = (claims.get("scope") or "").split()

    if "openid" in scopes and cfg.get("COGNITO_HOSTED_UI"):
        req = urllib.request.Request(
            f"{cfg['COGNITO_HOSTED_UI']}/oauth2/userInfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.load(r).get("email")

    if "aws.cognito.signin.user.admin" in scopes:
        region = cfg["COGNITO_ISSUER"].split(".")[1]  
        client = boto3.client("cognito-idp", region_name=region,
                              config=Config(signature_version=UNSIGNED))
        resp = client.get_user(AccessToken=access_token)
        return {a["Name"]: a["Value"] for a in resp["UserAttributes"]}.get("email")

    return None