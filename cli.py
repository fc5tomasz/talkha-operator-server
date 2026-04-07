from __future__ import annotations

import argparse
import json
import os
import sys
from urllib import request


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def _call(url: str, token: str, method: str = "GET", payload: dict | None = None) -> dict:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    req = request.Request(url, data=body, method=method, headers=_headers(token))
    with request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="TalkHa Operator CLI")
    parser.add_argument("--base-url", default=os.environ.get("TALKHA_OPERATOR_BASE_URL", "http://127.0.0.1:8787"))
    parser.add_argument("--admin-token", default=os.environ.get("TALKHA_OPERATOR_ADMIN_TOKEN", ""))
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("clients", help="List clients")

    job = sub.add_parser("job", help="Queue job")
    job.add_argument("--client-id", required=True)
    job.add_argument("--type", choices=["talkha", "talkhalokal"], required=True)
    job.add_argument("args", nargs=argparse.REMAINDER)

    result = sub.add_parser("result", help="Fetch result")
    result.add_argument("--job-id", required=True)

    args = parser.parse_args()
    if not args.admin_token:
        print("admin token required", file=sys.stderr)
        return 2

    if args.cmd == "clients":
        data = _call(f"{args.base_url}/api/v1/clients", args.admin_token)
    elif args.cmd == "job":
        data = _call(
            f"{args.base_url}/api/v1/jobs",
            args.admin_token,
            method="POST",
            payload={"client_id": args.client_id, "type": args.type, "args": args.args},
        )
    else:
        data = _call(f"{args.base_url}/api/v1/jobs/{args.job_id}", args.admin_token)

    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
