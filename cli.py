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


def _extract_job_payload(data: dict) -> tuple[dict | None, str]:
    result_wrapper = data.get("result") or {}
    client_result = result_wrapper.get("result") or {}
    stdout = str(client_result.get("stdout", "") or "").strip()
    if not stdout:
        return None, ""
    try:
        return json.loads(stdout), stdout
    except Exception:
        return None, stdout


def _queue_job(base_url: str, admin_token: str, client_id: str, job_type: str, job_args: list[str]) -> dict:
    return _call(
        f"{base_url}/api/v1/jobs",
        admin_token,
        method="POST",
        payload={"client_id": client_id, "type": job_type, "args": job_args},
    )


def _run_job_and_wait(
    base_url: str,
    admin_token: str,
    client_id: str,
    job_type: str,
    job_args: list[str],
    timeout: float,
    interval: float,
) -> tuple[dict, int]:
    queued = _queue_job(base_url, admin_token, client_id, job_type, job_args)
    job_id = str(queued.get("job_id", "") or "")
    if not job_id:
        return {
            "ok": False,
            "error": "missing job_id in queue response",
            "queued": queued,
        }, 4

    waited, rc = _wait_for_job(base_url, admin_token, job_id, timeout, interval)
    payload, stdout_text = _extract_job_payload(waited)
    client_result = ((waited.get("result") or {}).get("result") or {})
    final = dict(waited)
    final["queued"] = queued
    final["payload"] = payload
    final["stdout_text"] = stdout_text
    final["client_returncode"] = client_result.get("returncode")
    final["client_stderr"] = client_result.get("stderr")

    if rc != 0:
        return final, rc
    if client_result.get("returncode") not in (None, 0):
        final.setdefault("ok", False)
        final.setdefault("error", "client command failed")
        return final, 4
    return final, 0


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

    run_job = sub.add_parser("run-job", help="Queue job, wait, and return final payload")
    run_job.add_argument("--client-id", required=True)
    run_job.add_argument("--type", choices=["talkha", "talkhalokal"], required=True)
    run_job.add_argument("--timeout", type=float, default=120.0)
    run_job.add_argument("--interval", type=float, default=2.0)
    run_job.add_argument("args", nargs=argparse.REMAINDER)

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
            data = _queue_job(args.base_url, args.admin_token, args.client_id, args.type, job_args)
            rc = 0
        elif args.cmd == "run-job":
            job_args = list(args.args)
            if job_args[:1] == ["--"]:
                job_args = job_args[1:]
            data, rc = _run_job_and_wait(
                args.base_url,
                args.admin_token,
                args.client_id,
                args.type,
                job_args,
                args.timeout,
                args.interval,
            )
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
