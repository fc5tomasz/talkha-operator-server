from __future__ import annotations

import argparse
import json
import os
import sys
import time
from urllib import error, request


class CliCallError(Exception):
    def __init__(self, status: int, payload: dict):
        super().__init__(payload.get("error", f"http {status}"))
        self.status = status
        self.payload = payload


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def _call(url: str, token: str, method: str = "GET", payload: dict | None = None) -> dict:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    req = request.Request(url, data=body, method=method, headers=_headers(token))
    try:
        with request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            data = json.loads(raw) if raw else {}
        except Exception:
            data = {"ok": False, "error": raw or str(exc)}
        data.setdefault("ok", False)
        data.setdefault("http_status", exc.code)
        raise CliCallError(exc.code, data) from exc


def _wait_for_job(base_url: str, admin_token: str, job_id: str, timeout: float, interval: float) -> tuple[dict, int]:
    deadline = time.monotonic() + max(timeout, 0.0)
    poll_interval = max(interval, 0.2)
    while True:
        data = _call(f"{base_url}/api/v1/jobs/{job_id}", admin_token)
        if str(data.get("status", "")).lower() == "completed":
            return data, 0
        if time.monotonic() >= deadline:
            return {
                "ok": False,
                "error": f"timeout waiting for job {job_id}",
                "job_id": job_id,
                "status": data.get("status", ""),
                "client_id": data.get("client_id", ""),
                "queue_position": data.get("queue_position", 0),
                "timeout": timeout,
            }, 3
        time.sleep(poll_interval)


def main() -> int:
    parser = argparse.ArgumentParser(description="TalkHa Operator CLI")
    parser.add_argument("--base-url", default=os.environ.get("TALKHA_OPERATOR_BASE_URL", "http://127.0.0.1:8787"))
    parser.add_argument("--admin-token", default=os.environ.get("TALKHA_OPERATOR_ADMIN_TOKEN", ""))
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("clients", help="List clients")

    add_client = sub.add_parser("add-client", help="Add or update client")
    add_client.add_argument("--client-id", required=True)
    add_client.add_argument("--description", default="")
    add_client.add_argument("--communication-mode", default="operator_reverse_http")
    add_client.add_argument("--communication-label", default="Laptop operator")
    add_client.add_argument("--disabled", action="store_true")

    remove_client = sub.add_parser("remove-client", help="Remove client")
    remove_client.add_argument("--client-id", required=True)

    job = sub.add_parser("job", help="Queue job")
    job.add_argument("--client-id", required=True)
    job.add_argument("--type", choices=["talkha", "talkhalokal"], required=True)
    job.add_argument("args", nargs=argparse.REMAINDER)

    result = sub.add_parser("result", help="Fetch job status/result")
    result.add_argument("--job-id", required=True)

    wait = sub.add_parser("wait", help="Wait until job is completed")
    wait.add_argument("--job-id", required=True)
    wait.add_argument("--timeout", type=float, default=120.0)
    wait.add_argument("--interval", type=float, default=2.0)

    args = parser.parse_args()
    if not args.admin_token:
        print("admin token required", file=sys.stderr)
        return 2

    try:
        if args.cmd == "clients":
            data = _call(f"{args.base_url}/api/v1/clients", args.admin_token)
            rc = 0
        elif args.cmd == "add-client":
            data = _call(
                f"{args.base_url}/api/v1/clients/add",
                args.admin_token,
                method="POST",
                payload={
                    "client_id": args.client_id,
                    "description": args.description,
                    "communication_mode": args.communication_mode,
                    "communication_label": args.communication_label,
                    "enabled": not args.disabled,
                },
            )
            rc = 0
        elif args.cmd == "remove-client":
            data = _call(
                f"{args.base_url}/api/v1/clients/remove",
                args.admin_token,
                method="POST",
                payload={"client_id": args.client_id},
            )
            rc = 0
        elif args.cmd == "job":
            job_args = list(args.args)
            if job_args[:1] == ["--"]:
                job_args = job_args[1:]
            data = _call(
                f"{args.base_url}/api/v1/jobs",
                args.admin_token,
                method="POST",
                payload={"client_id": args.client_id, "type": args.type, "args": job_args},
            )
            rc = 0
        elif args.cmd == "wait":
            data, rc = _wait_for_job(args.base_url, args.admin_token, args.job_id, args.timeout, args.interval)
        else:
            data = _call(f"{args.base_url}/api/v1/jobs/{args.job_id}", args.admin_token)
            rc = 0
    except CliCallError as exc:
        data = exc.payload
        rc = 1

    print(json.dumps(data, ensure_ascii=False, indent=2))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
