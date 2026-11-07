"""Create one synthetic post, exercise D2, and leave it HIDDEN.

Tokens are read from HOMEWALLET_D2_MEMBER_TOKEN / HOMEWALLET_D2_ADMIN_TOKEN.
Output contains only case IDs, status codes, request IDs and the synthetic post ID.
Audit persistence must additionally be verified in MySQL using the runbook.
"""

import argparse
from datetime import datetime, timezone
import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
import uuid


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def transport(base_url, tokens):
    opener = build_opener(NoRedirect())

    def call(method, path, role=None, body=None):
        headers = {"Accept": "application/json"}
        if role:
            headers["Authorization"] = "Bearer " + tokens[role]
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = Request(base_url + path, data=data, headers=headers, method=method)
        try:
            response = opener.open(request, timeout=15)
        except HTTPError as error:
            response = error
        with response:
            raw = response.read()
            try:
                payload = json.loads(raw)
            except (ValueError, UnicodeDecodeError):
                payload = None
            return response.code, payload, response.headers.get("X-Request-Id")

    return call


def run_checks(call):
    evidence = {"started_at": datetime.now(timezone.utc).isoformat(), "cases": [], "post_id": None}

    def check(case, method, path, role, body, expected, predicate=lambda value: True):
        status, payload, request_id = call(method, path, role, body)
        try:
            passed = status == expected and payload is not None and predicate(payload)
        except (KeyError, TypeError, IndexError):
            passed = False
        evidence["cases"].append({"case": case, "status": "PASS" if passed else "FAIL",
                                  "http": status, "request_id": request_id})
        if not passed:
            raise AssertionError(case)
        return payload

    try:
        check("anonymous-denied", "GET", "/api/community/posts", None, None, 401)
        check("member-admin-list-denied", "GET", "/api/admin/community/posts", "member", None, 403)
        check("admin-list-allowed", "GET", "/api/admin/community/posts", "admin", None, 200,
              lambda value: isinstance(value["items"], list))
        content = {"type": "tip", "title": "D2 synthetic " + uuid.uuid4().hex[:12],
                   "body": "Synthetic acceptance data. Turn off unused lights."}
        check("cannot-submit-approved", "POST", "/api/community/posts", "member",
              {**content, "status": "APPROVED"}, 422)
        check("cannot-self-promote", "PATCH", "/api/me", "member", {"role": "admin"}, 422)
        # Record ID immediately so even a status assertion failure triggers cleanup.
        created = check("create-post", "POST", "/api/community/posts", "member", content, 201,
                        lambda value: type(value["post"]["id"]) is int and value["post"]["id"] > 0)
        post_id = evidence["post_id"] = created["post"]["id"]
        if created["post"]["status"] != "PENDING":
            evidence["cases"].append({"case": "created-pending", "status": "FAIL"})
            raise AssertionError("created-pending")
        evidence["cases"].append({"case": "created-pending", "status": "PASS"})
        path = f"/api/admin/community/posts/{post_id}"
        absent = lambda value: all(post["id"] != post_id for post in value["items"])
        present = lambda value: any(post["id"] == post_id for post in value["items"])
        check("pending-not-in-feed", "GET", "/api/community/posts?status=PENDING", "member", None, 200, absent)
        check("pending-in-admin-queue", "GET", "/api/admin/community/posts?status=PENDING", "admin", None, 200, present)
        check("member-patch-denied", "PATCH", path, "member", {"status": "APPROVED"}, 403)
        check("admin-approve", "PATCH", path, "admin", {"status": "APPROVED"}, 200,
              lambda value: value["post"]["status"] == "APPROVED")
        check("approved-in-feed", "GET", "/api/community/posts", "member", None, 200, present)
        check("admin-edit", "PATCH", path, "admin", {"title": "D2 synthetic edited"}, 200,
              lambda value: value["post"]["title"] == "D2 synthetic edited")
        check("admin-hide", "PATCH", path, "admin", {"status": "HIDDEN"}, 200,
              lambda value: value["post"]["status"] == "HIDDEN")
        check("hidden-not-in-feed", "GET", "/api/community/posts?status=HIDDEN", "member", None, 200, absent)
        evidence["status"] = "PASS"
    except (AssertionError, URLError, TimeoutError, OSError, ValueError, KeyError, TypeError):
        # Never print exception text: transport errors may carry private response data.
        evidence["status"] = "FAIL"
    finally:
        if evidence["post_id"] is not None:
            try:
                check("cleanup-hide", "PATCH", f"/api/admin/community/posts/{evidence['post_id']}",
                      "admin", {"status": "HIDDEN"}, 200,
                      lambda value: value["post"]["status"] == "HIDDEN")
            except (AssertionError, URLError, TimeoutError, OSError, ValueError):
                evidence["status"] = "FAIL"
    evidence["audit_status"] = "PENDING_DB_VERIFICATION"
    return evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True, help="Dev API origin, no /api suffix")
    args = parser.parse_args()
    parsed = urlsplit(args.base_url)
    if (parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username
            or parsed.password or parsed.query or parsed.fragment or parsed.path not in ("", "/")):
        parser.error("Expected an HTTP(S) origin without credentials, query or path")
    if parsed.scheme == "http" and parsed.hostname not in ("localhost", "127.0.0.1", "::1"):
        parser.error("Use HTTPS for dev; HTTP is allowed only on localhost")
    tokens = {role: os.getenv(f"HOMEWALLET_D2_{role.upper()}_TOKEN", "").strip()
              for role in ("member", "admin")}
    if not all(tokens.values()):
        parser.error("Set both HOMEWALLET_D2_MEMBER_TOKEN and HOMEWALLET_D2_ADMIN_TOKEN")
    evidence = run_checks(transport(args.base_url.rstrip("/"), tokens))
    print(json.dumps(evidence, indent=2))
    return 0 if evidence["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
