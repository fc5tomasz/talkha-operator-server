from __future__ import annotations

import json
import os
import secrets
import time
from pathlib import Path
from typing import Any

from aiohttp import web


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("TALKHA_OPERATOR_DATA_DIR", BASE_DIR / "data"))
CLIENTS_FILE = Path(os.environ.get("TALKHA_OPERATOR_CLIENTS_FILE", DATA_DIR / "clients.json"))
AUDIT_LOG_FILE = Path(os.environ.get("TALKHA_OPERATOR_AUDIT_LOG", DATA_DIR / "audit.log"))
SERVER_HOST = os.environ.get("TALKHA_OPERATOR_HOST", "127.0.0.1")
SERVER_PORT = int(os.environ.get("TALKHA_OPERATOR_PORT", "8787"))
ADMIN_TOKEN = os.environ.get("TALKHA_OPERATOR_ADMIN_TOKEN", "")
POLL_INTERVAL = int(os.environ.get("TALKHA_OPERATOR_POLL_INTERVAL", "10"))
SESSION_TTL_SECONDS = int(os.environ.get("TALKHA_OPERATOR_SESSION_TTL", "1800"))
SHARED_REGISTRATION_TOKEN = os.environ.get("TALKHA_SHARED_REGISTRATION_TOKEN", "").strip()

CLIENT_SESSIONS: dict[str, dict[str, Any]] = {}
JOB_QUEUES: dict[str, list[dict[str, Any]]] = {}
JOB_RESULTS: dict[str, dict[str, Any]] = {}
ACTIVE_JOBS: dict[str, dict[str, Any]] = {}


def _json(data: dict[str, Any], status: int = 200) -> web.Response:
    return web.json_response(data, status=status, dumps=lambda x: json.dumps(x, ensure_ascii=False))


def _ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not CLIENTS_FILE.exists():
        CLIENTS_FILE.write_text(json.dumps({"clients": []}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _load_clients() -> dict[str, dict[str, Any]]:
    raw = json.loads(CLIENTS_FILE.read_text(encoding="utf-8"))
    clients = raw.get("clients", [])
    result: dict[str, dict[str, Any]] = {}
    for item in clients:
        client_id = item.get("client_id", "")
        if client_id:
            result[client_id] = item
    return result


def _load_clients_raw() -> list[dict[str, Any]]:
    raw = json.loads(CLIENTS_FILE.read_text(encoding="utf-8"))
    clients = raw.get("clients", [])
    return clients if isinstance(clients, list) else []


def _save_clients_raw(clients: list[dict[str, Any]]) -> None:
    CLIENTS_FILE.write_text(json.dumps({"clients": clients}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_audit(event: str, payload: dict[str, Any]) -> None:
    entry = {
        "ts": int(time.time()),
        "event": event,
        "payload": payload,
    }
    with AUDIT_LOG_FILE.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _client_ip(request: web.Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
    if forwarded:
        return forwarded
    peer = request.transport.get_extra_info("peername") if request.transport else None
    if isinstance(peer, tuple) and peer:
        return str(peer[0])
    return request.remote or ""


def _admin_ok(request: web.Request) -> bool:
    if not ADMIN_TOKEN:
        return False
    auth = request.headers.get("Authorization", "")
    return auth == f"Bearer {ADMIN_TOKEN}"


def _public_path(path: str) -> bool:
    return path in {"/health", "/api/v1/register", "/api/v1/poll", "/api/v1/result"}


def _session_ok(client_id: str, session_token: str) -> bool:
    session = CLIENT_SESSIONS.get(client_id)
    if not session or session.get("session_token") != session_token:
        return False
    if int(time.time()) - int(session.get("last_seen", 0)) > SESSION_TTL_SECONDS:
        CLIENT_SESSIONS.pop(client_id, None)
        return False
    return True


@web.middleware
async def auth_middleware(request: web.Request, handler):
    if _public_path(request.path):
        return await handler(request)
    if not _admin_ok(request):
        return _json({"ok": False, "error": "unauthorized"}, status=401)
    return await handler(request)


async def health(_: web.Request) -> web.Response:
    return _json(
        {
            "ok": True,
            "clients_online": sorted(CLIENT_SESSIONS.keys()),
            "queued_jobs": {client_id: len(queue) for client_id, queue in JOB_QUEUES.items()},
        }
    )


async def register(request: web.Request) -> web.Response:
    payload = await request.json()
    client_id = payload.get("client_id", "")
    registration_token = payload.get("registration_token", "")
    clients = _load_clients()
    client = clients.get(client_id)
    expected_token = (client or {}).get("registration_token", "") or SHARED_REGISTRATION_TOKEN
    if not client or not client.get("enabled", True) or not expected_token or registration_token != expected_token:
        _write_audit("register_failed", {"client_id": client_id, "ip": _client_ip(request)})
        return _json({"ok": False, "error": "registration failed"}, status=401)

    session_token = secrets.token_urlsafe(32)
    now = int(time.time())
    client_ip = _client_ip(request)
    CLIENT_SESSIONS[client_id] = {
        "session_token": session_token,
        "registered_at": now,
        "last_seen": now,
        "last_ip": client_ip,
        "hostname": payload.get("hostname", ""),
        "mode": payload.get("mode", "full"),
        "allow_mutations": payload.get("allow_mutations", True),
        "capabilities": payload.get("capabilities", []),
    }
    JOB_QUEUES.setdefault(client_id, [])
    _write_audit("register_ok", {"client_id": client_id, "ip": client_ip, "hostname": payload.get("hostname", "")})
    return _json({"ok": True, "session_token": session_token, "poll_interval": POLL_INTERVAL})


async def poll(request: web.Request) -> web.Response:
    payload = await request.json()
    client_id = payload.get("client_id", "")
    session_token = payload.get("session_token", "")
    if not _session_ok(client_id, session_token):
        _write_audit("poll_unauthorized", {"client_id": client_id, "ip": _client_ip(request)})
        return _json({"ok": False, "error": "unauthorized"}, status=401)

    CLIENT_SESSIONS[client_id]["last_seen"] = int(time.time())
    CLIENT_SESSIONS[client_id]["last_ip"] = _client_ip(request)
    queue = JOB_QUEUES.setdefault(client_id, [])
    active_job = ACTIVE_JOBS.get(client_id)
    if active_job:
        return _json({"ok": True, "job": None})

    job = queue.pop(0) if queue else None
    if job:
        ACTIVE_JOBS[client_id] = job
    return _json({"ok": True, "job": job})


async def submit_result(request: web.Request) -> web.Response:
    payload = await request.json()
    client_id = payload.get("client_id", "")
    session_token = payload.get("session_token", "")
    job_id = payload.get("job_id", "")
    result = payload.get("result")
    if not _session_ok(client_id, session_token):
        _write_audit("result_unauthorized", {"client_id": client_id, "ip": _client_ip(request)})
        return _json({"ok": False, "error": "unauthorized"}, status=401)
    if not job_id:
        return _json({"ok": False, "error": "job_id required"}, status=400)

    JOB_RESULTS[job_id] = {
        "client_id": client_id,
        "received_at": int(time.time()),
        "result": result,
    }
    active_job = ACTIVE_JOBS.get(client_id)
    if active_job and active_job.get("job_id") == job_id:
        ACTIVE_JOBS.pop(client_id, None)
    CLIENT_SESSIONS[client_id]["last_seen"] = int(time.time())
    CLIENT_SESSIONS[client_id]["last_ip"] = _client_ip(request)
    _write_audit("job_result", {"client_id": client_id, "job_id": job_id, "ok": bool(result and result.get("ok"))})
    return _json({"ok": True})


async def enqueue_job(request: web.Request) -> web.Response:
    payload = await request.json()
    client_id = payload.get("client_id", "")
    job_type = payload.get("type", "")
    args = payload.get("args", [])
    if client_id not in _load_clients():
        return _json({"ok": False, "error": "unknown client_id"}, status=404)
    if job_type not in {"talkha", "talkhalokal"}:
        return _json({"ok": False, "error": "unsupported job type"}, status=400)
    if not isinstance(args, list) or not all(isinstance(item, str) for item in args):
        return _json({"ok": False, "error": "args must be string list"}, status=400)

    job_id = secrets.token_urlsafe(12)
    job = {"job_id": job_id, "type": job_type, "args": args}
    JOB_QUEUES.setdefault(client_id, []).append(job)
    _write_audit("job_enqueued", {"client_id": client_id, "job_id": job_id, "type": job_type, "args": args})
    return _json({"ok": True, "job_id": job_id, "queued_for": client_id})


async def get_result(request: web.Request) -> web.Response:
    job_id = request.match_info["job_id"]
    result = JOB_RESULTS.get(job_id)
    if result is None:
        return _json({"ok": False, "error": "result not found"}, status=404)
    return _json({"ok": True, "job_id": job_id, "result": result})


async def list_clients(_: web.Request) -> web.Response:
    configured = _load_clients()
    rows = []
    for client_id, item in configured.items():
        session = CLIENT_SESSIONS.get(client_id, {})
        rows.append(
            {
                "client_id": client_id,
                "enabled": item.get("enabled", True),
                "description": item.get("description", ""),
                "communication_mode": item.get("communication_mode", "operator_reverse_http"),
                "communication_label": item.get("communication_label", "Laptop operator"),
                "online": bool(session),
                "queued_jobs": len(JOB_QUEUES.get(client_id, [])),
                "active_job_id": (ACTIVE_JOBS.get(client_id) or {}).get("job_id", ""),
                "last_ip": session.get("last_ip", ""),
                "last_seen": session.get("last_seen", 0),
                "hostname": session.get("hostname", ""),
                "mode": session.get("mode", ""),
                "allow_mutations": session.get("allow_mutations", False),
            }
        )
    return _json({"ok": True, "clients": rows})


async def add_client(request: web.Request) -> web.Response:
    payload = await request.json()
    client_id = str(payload.get("client_id", "")).strip()
    if not client_id:
        return _json({"ok": False, "error": "client_id required"}, status=400)

    clients = _load_clients_raw()
    existing_idx = next((idx for idx, item in enumerate(clients) if str(item.get("client_id", "")).strip() == client_id), None)
    row = {
        "client_id": client_id,
        "enabled": bool(payload.get("enabled", True)),
        "description": str(payload.get("description", "")).strip(),
        "communication_mode": str(payload.get("communication_mode", "operator_reverse_http")).strip() or "operator_reverse_http",
        "communication_label": str(payload.get("communication_label", "Laptop operator")).strip() or "Laptop operator",
    }
    if existing_idx is None:
        clients.append(row)
        action = "added"
    else:
        clients[existing_idx] = row
        action = "updated"
    _save_clients_raw(clients)
    _write_audit("client_saved", {"client_id": client_id, "action": action})
    return _json({"ok": True, "client": row, "action": action})


async def remove_client(request: web.Request) -> web.Response:
    payload = await request.json()
    client_id = str(payload.get("client_id", "")).strip()
    if not client_id:
        return _json({"ok": False, "error": "client_id required"}, status=400)
    clients = _load_clients_raw()
    kept = [item for item in clients if str(item.get("client_id", "")).strip() != client_id]
    if len(kept) == len(clients):
        return _json({"ok": False, "error": "client not found"}, status=404)
    _save_clients_raw(kept)
    CLIENT_SESSIONS.pop(client_id, None)
    JOB_QUEUES.pop(client_id, None)
    ACTIVE_JOBS.pop(client_id, None)
    _write_audit("client_removed", {"client_id": client_id})
    return _json({"ok": True, "client_id": client_id, "removed": True})


def main() -> None:
    _ensure_data_dir()
    app = web.Application(middlewares=[auth_middleware])
    app.router.add_get("/health", health)
    app.router.add_post("/api/v1/register", register)
    app.router.add_post("/api/v1/poll", poll)
    app.router.add_post("/api/v1/result", submit_result)
    app.router.add_get("/api/v1/clients", list_clients)
    app.router.add_post("/api/v1/clients/add", add_client)
    app.router.add_post("/api/v1/clients/remove", remove_client)
    app.router.add_post("/api/v1/jobs", enqueue_job)
    app.router.add_get("/api/v1/jobs/{job_id}", get_result)
    web.run_app(app, host=SERVER_HOST, port=SERVER_PORT)


if __name__ == "__main__":
    main()
