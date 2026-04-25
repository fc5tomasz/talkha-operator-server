#!/usr/bin/env bash
set -euo pipefail

HX_CONFIG_DIR="${HOME}/.config/codex"
HX_ENV_FILE="${HX_CONFIG_DIR}/hx.env"
HX_STATE_DIR="${HX_CONFIG_DIR}/hx"
HX_CURRENT_CLIENT_FILE="${HX_STATE_DIR}/current_client"
HX_LAST_JOB_FILE="${HX_STATE_DIR}/last_job"
HX_LAST_JOB_CLIENT_FILE="${HX_STATE_DIR}/last_job_client"

mkdir -p "${HX_STATE_DIR}"

if [[ -f "${HX_ENV_FILE}" ]]; then
  # shellcheck disable=SC1090
  . "${HX_ENV_FILE}"
fi

HX_BASE_URL="${HX_BASE_URL:-http://127.0.0.1:8787}"
HX_ADMIN_TOKEN="${HX_ADMIN_TOKEN:-}"
HX_OPERATOR_CLI="${HX_OPERATOR_CLI:-/home/tomasz/Codex/Klient/publish/talkha-operator-server/cli.py}"
HX_REMOTE_BACKUP_DIR="${HX_REMOTE_BACKUP_DIR:-/homeassistant/TalkHaBackup/operator_remote}"

die() {
  printf 'hx: %s\n' "$*" >&2
  exit 1
}

require_cli() {
  [[ -f "${HX_OPERATOR_CLI}" ]] || die "Brak operator CLI: ${HX_OPERATOR_CLI}"
  [[ -n "${HX_ADMIN_TOKEN}" ]] || die "Brak HX_ADMIN_TOKEN w ${HX_ENV_FILE}"
}

run_cli() {
  require_cli
  python3 "${HX_OPERATOR_CLI}" --base-url "${HX_BASE_URL}" --admin-token "${HX_ADMIN_TOKEN}" "$@"
}

current_client() {
  [[ -f "${HX_CURRENT_CLIENT_FILE}" ]] || return 1
  tr -d '\r\n' < "${HX_CURRENT_CLIENT_FILE}"
}

save_current_client() {
  printf '%s\n' "$1" > "${HX_CURRENT_CLIENT_FILE}"
}

save_last_job() {
  printf '%s\n' "$1" > "${HX_LAST_JOB_FILE}"
}

save_last_job_client() {
  printf '%s\n' "$1" > "${HX_LAST_JOB_CLIENT_FILE}"
}

last_job() {
  [[ -f "${HX_LAST_JOB_FILE}" ]] || return 1
  tr -d '\r\n' < "${HX_LAST_JOB_FILE}"
}

last_job_client() {
  [[ -f "${HX_LAST_JOB_CLIENT_FILE}" ]] || return 1
  tr -d '\r\n' < "${HX_LAST_JOB_CLIENT_FILE}"
}

extract_job_id() {
  python3 -c 'import json,sys; print(json.load(sys.stdin).get("job_id",""))'
}

extract_json_field() {
  local field="$1"
  python3 -c '
import json,sys
field = sys.argv[1]
data = json.load(sys.stdin)
value = data.get(field, "")
if isinstance(value, bool):
    print("true" if value else "false")
elif value is None:
    print("")
else:
    print(value)
' "${field}"
}

client_online() {
  local client_id="$1"
  run_cli clients | python3 -c '
import json,sys
client_id = sys.argv[1]
data = json.load(sys.stdin)
rows = data.get("clients", [])
for row in rows:
    if row.get("client_id") == client_id:
        print("true" if row.get("online") else "false")
        raise SystemExit(0)
print("missing")
' "${client_id}"
}

require_online_client() {
  local client_id="$1"
  local status
  status="$(client_online "${client_id}")"
  case "${status}" in
    true)
      return 0
      ;;
    false)
      die "Klient ${client_id} jest offline. STOP. Najpierw zbadaj, dlaczego nie ma aktywnej sesji."
      ;;
    *)
      die "Klient ${client_id} nie istnieje po stronie operatora."
      ;;
  esac
}

submit_job() {
  local job_type="$1"
  shift
  local client_id
  client_id="$(current_client)" || die "Brak aktywnego klienta. Użyj: hx use CLIENT_ID"
  require_online_client "${client_id}"
  local output job_id
  output="$(run_cli job --client-id "${client_id}" --type "${job_type}" -- "$@")"
  printf '%s\n' "${output}"
  job_id="$(printf '%s' "${output}" | extract_job_id)"
  [[ -n "${job_id}" ]] || die "Nie udało się odczytać job_id"
  save_last_job "${job_id}"
  save_last_job_client "${client_id}"
}

wait_for_result() {
  local job_id="${1:-}"
  [[ -n "${job_id}" ]] || job_id="$(last_job)" || die "Brak job_id i brak ostatniego zadania"
  local output
  if ! output="$(run_cli wait "--job-id=${job_id}" --timeout=180 --interval=2)"; then
    printf '%s\n' "${output}"
    die "Brak zakonczonego wyniku dla job_id=${job_id}"
  fi
  printf '%s\n' "${output}"
  save_last_job "${job_id}"
}

run_sync_job() {
  local job_type="$1"
  shift
  local client_id
  client_id="$(current_client)" || die "Brak aktywnego klienta. Użyj: hx use CLIENT_ID"
  require_online_client "${client_id}"
  local output job_id
  if ! output="$(run_cli run-job --client-id "${client_id}" --type "${job_type}" --timeout=180 --interval=2 -- "$@")"; then
    printf '%s\n' "${output}"
    return 1
  fi
  job_id="$(printf '%s' "${output}" | extract_job_id)"
  [[ -n "${job_id}" ]] && save_last_job "${job_id}"
  save_last_job_client "${client_id}"
  printf '%s\n' "${output}"
}

unwrap_sync_payload() {
  python3 -c '
import json, sys
data = json.load(sys.stdin)
payload = data.get("payload")
if payload is not None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    raise SystemExit(0)
inner = ((data.get("result") or {}).get("result") or {})
stdout = str(inner.get("stdout", "") or "").strip()
if stdout:
    try:
        print(json.dumps(json.loads(stdout), ensure_ascii=False, indent=2))
    except Exception:
        print(stdout)
    raise SystemExit(0)
print(json.dumps(data, ensure_ascii=False, indent=2))
'
}

run_sync_payload() {
  local job_type="$1"
  shift
  local output
  if ! output="$(run_sync_job "${job_type}" "$@")"; then
    return 1
  fi
  printf '%s' "${output}" | unwrap_sync_payload
}

require_file() {
  [[ -f "$1" ]] || die "Brak pliku: $1"
}

file_base64_single_line() {
  require_file "$1"
  base64 -w0 < "$1"
}

read_file_text() {
  require_file "$1"
  cat "$1"
}

yaml_alias_from_file() {
  require_file "$1"
  sed -n 's/^alias:[[:space:]]*//p' "$1" | head -n1
}

slugify_identifier() {
  printf '%s' "$1" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9]\+/_/g; s/^_//; s/_$//'
}

render_compact_tx_summary() {
  python3 -c '
import json,sys
data=json.load(sys.stdin)
checks=data.get("checks") or {}
print(json.dumps({
  "tx_id": data.get("tx_id"),
  "status": data.get("status"),
  "message": data.get("message"),
  "backup_dir": data.get("backup_dir"),
  "checks": {
    "ha_core_check_ok": checks.get("ha_core_check_ok", checks.get("ha_core_check", {}).get("ok") if isinstance(checks.get("ha_core_check"), dict) else None),
    "reload_ok": checks.get("reload_ok", checks.get("reload", {}).get("ok") if isinstance(checks.get("reload"), dict) else None),
    "reload_services": checks.get("reload_services", [str(r.get("domain", "")) + "." + str(r.get("service", "")) for r in (checks.get("reload", {}).get("results") or []) if isinstance(r, dict)]),
  },
  "rollback": data.get("rollback"),
  "replaced": data.get("replaced"),
  "removed": data.get("removed"),
  "removed_alias": data.get("removed_alias"),
  "removed_id": data.get("removed_id"),
  "removed_key": data.get("removed_key"),
  "key": data.get("key"),
  "kind": data.get("kind"),
  "helper": data.get("helper"),
  "entity_id": data.get("entity_id"),
}, ensure_ascii=False, indent=2))
'
}

run_doctor() {
  local client_id auth_job scan_job auth_result scan_result
  client_id="$(current_client)" || die "Brak aktywnego klienta. Użyj: hx use CLIENT_ID"
  require_online_client "${client_id}"

  auth_job="$(submit_job talkha test-auth)"
  auth_result="$(wait_for_result "$(printf '%s' "${auth_job}" | extract_job_id)")"

  scan_job="$(submit_job talkhalokal scan --compact --limit 5)"
  scan_result="$(wait_for_result "$(printf '%s' "${scan_job}" | extract_job_id)")"

  cat <<EOF
{
  "ok": true,
  "client_id": "${client_id}",
  "checks": {
    "talkha_test_auth": $(printf '%s' "${auth_result}" | python3 -c 'import json,sys; data=json.load(sys.stdin); print(json.dumps(data, ensure_ascii=False))'),
    "talkhalokal_scan": $(printf '%s' "${scan_result}" | python3 -c 'import json,sys; data=json.load(sys.stdin); print(json.dumps(data, ensure_ascii=False))')
  }
}
EOF
}

usage() {
  cat <<'EOF'
hx - skróty operatora TalkHa

Użycie:
  hx clients
  hx use CLIENT_ID
  hx current
  hx talkha ...
  hx local ...
  hx talkha-sync ...
  hx local-sync ...
  hx result [JOB_ID]
  hx wait [JOB_ID]
  hx doctor
  hx install-check
  hx last
  hx test
  hx zigbee
  hx lights
  hx entity ENTITY_ID
  hx state ENTITY_ID [ENTITY_ID...]
  hx history ENTITY_ID [ENTITY_ID...]
  hx changes ENTITY_ID [ENTITY_ID...]
  hx last-trigger AUTOMATION_REF
  hx find QUERY
  hx scan
  hx where-used ENTITY_ID
  hx script ALIAS
  hx auto ALIAS
  hx script-summary ALIAS
  hx auto-summary ALIAS
  hx thresholds ENTITY_ID
  hx threshold-check ENTITY_ID VALUE
  hx diag-auto ALIAS
  hx why-light ENTITY_ID
  hx tx-summary TX_ID
  hx upsert-automation FILE [TARGET]
  hx delete-automation TARGET
  hx upsert-script FILE [TARGET]
  hx delete-script TARGET
  hx helper-upsert KIND HELPER ITEM_FILE
  hx helper-delete KIND HELPER
  hx rollback-tx TX_ID
EOF
}

cmd="${1:-}"
case "${cmd}" in
  clients)
    shift
    run_cli clients "$@"
    ;;
  use)
    shift
    [[ $# -ge 1 ]] || die "Użycie: hx use CLIENT_ID"
    save_current_client "$1"
    printf 'Aktywny klient: %s\n' "$1"
    ;;
  current)
    current_client || die "Brak aktywnego klienta"
    ;;
  talkha)
    shift
    [[ $# -ge 1 ]] || die "Użycie: hx talkha ..."
    submit_job talkha "$@"
    ;;
  local|talkhalokal)
    shift
    [[ $# -ge 1 ]] || die "Użycie: hx local ..."
    submit_job talkhalokal "$@"
    ;;
  talkha-sync)
    shift
    [[ $# -ge 1 ]] || die "Użycie: hx talkha-sync ..."
    run_sync_payload talkha "$@"
    ;;
  local-sync|talkhalokal-sync)
    shift
    [[ $# -ge 1 ]] || die "Użycie: hx local-sync ..."
    run_sync_payload talkhalokal "$@"
    ;;
  result)
    shift
    run_cli result "--job-id=${1:-$(last_job || true)}"
    ;;
  wait)
    shift
    wait_for_result "${1:-}"
    ;;
  doctor|install-check)
    shift
    run_doctor
    ;;
  last)
    last_job || die "Brak ostatniego zadania"
    ;;
  test)
    submit_job talkha test-auth
    ;;
  zigbee)
    submit_job talkha zigbee-status-report
    ;;
  lights)
    submit_job talkha lights-on-report
    ;;
  entity)
    shift
    [[ $# -ge 1 ]] || die "Użycie: hx entity ENTITY_ID"
    submit_job talkha get-entity --entity-id "$1"
    ;;
  state)
    shift
    [[ $# -ge 1 ]] || die "Użycie: hx state ENTITY_ID [ENTITY_ID...]"
    submit_job talkha get-state "$@"
    ;;
  history)
    shift
    [[ $# -ge 3 ]] || die "Użycie: hx history ENTITY_ID [ENTITY_ID...] --from-time \"YYYY-MM-DD HH:MM:SS\" [--to-time ...]"
    submit_job talkha state-history "$@"
    ;;
  changes)
    shift
    [[ $# -ge 1 ]] || die "Użycie: hx changes ENTITY_ID [ENTITY_ID...] [--minutes N | --from-time ...]"
    submit_job talkha recent-changes "$@"
    ;;
  last-trigger)
    shift
    [[ $# -ge 1 ]] || die "Użycie: hx last-trigger AUTOMATION_REF"
    submit_job talkha last-trigger "$1"
    ;;
  find)
    shift
    [[ $# -ge 1 ]] || die "Użycie: hx find QUERY"
    submit_job talkhalokal find --query "$1"
    ;;
  scan)
    shift
    submit_job talkhalokal scan --compact "$@"
    ;;
  where-used)
    shift
    [[ $# -ge 1 ]] || die "Użycie: hx where-used ENTITY_ID"
    submit_job talkhalokal where-used --entity "$1"
    ;;
  script)
    shift
    [[ $# -ge 1 ]] || die "Użycie: hx script ALIAS [dodatkowe flagi get-script]"
    target="$1"
    shift
    submit_job talkhalokal get-script --target "${target}" --match-by alias "$@"
    ;;
  script-summary)
    shift
    [[ $# -ge 1 ]] || die "Użycie: hx script-summary ALIAS"
    target="$1"
    shift
    run_sync_payload talkhalokal script-summary --target "${target}" --match-by alias --compact "$@"
    ;;
  auto)
    shift
    [[ $# -ge 1 ]] || die "Użycie: hx auto ALIAS [dodatkowe flagi get-automation]"
    target="$1"
    shift
    submit_job talkhalokal get-automation --target "${target}" --match-by alias "$@"
    ;;
  auto-summary)
    shift
    [[ $# -ge 1 ]] || die "Użycie: hx auto-summary ALIAS"
    target="$1"
    shift
    run_sync_payload talkhalokal automation-summary --target "${target}" --match-by alias --compact "$@"
    ;;
  thresholds)
    shift
    [[ $# -ge 1 ]] || die "Użycie: hx thresholds ENTITY_ID"
    run_sync_payload talkhalokal entity-thresholds --entity-id "$1" --compact
    ;;
  threshold-check)
    shift
    [[ $# -ge 2 ]] || die "Użycie: hx threshold-check ENTITY_ID VALUE"
    run_sync_payload talkhalokal threshold-check --entity-id "$1" --candidate "$2" --compact
    ;;
  diag-auto)
    shift
    [[ $# -ge 1 ]] || die "Użycie: hx diag-auto ALIAS [--from-time ...] [--to-time ...]"
    target="$1"
    shift
    run_sync_payload talkhalokal diagnoza-automatyzacji --target "${target}" --match-by alias --compact "$@"
    ;;
  why-light)
    shift
    [[ $# -ge 1 ]] || die "Użycie: hx why-light ENTITY_ID [dodatkowe flagi why-light-on]"
    target="$1"
    shift
    submit_job talkhalokal why-light-on --entity-id "${target}" "$@"
    ;;
  tx-summary)
    shift
    [[ $# -ge 1 ]] || die "Użycie: hx tx-summary TX_ID"
    run_sync_payload talkhalokal tx-report --tx-id "$1" --compact
    ;;
  upsert-automation)
    shift
    [[ $# -ge 1 ]] || die "Użycie: hx upsert-automation FILE [TARGET]"
    block_file="$1"
    shift
    block_b64="$(file_base64_single_line "${block_file}")"
    if [[ $# -ge 1 && "${1:0:2}" != "--" ]]; then
      target="$1"
      shift
      output="$(run_sync_payload talkhalokal upsert-automation --block-base64 "${block_b64}" --target "${target}" --match-by alias --allow-add --backup-dir "${HX_REMOTE_BACKUP_DIR}" "$@")" || exit 1
    else
      output="$(run_sync_payload talkhalokal upsert-automation --block-base64 "${block_b64}" --match-by alias --allow-add --backup-dir "${HX_REMOTE_BACKUP_DIR}" "$@")" || exit 1
    fi
    printf '%s' "${output}" | render_compact_tx_summary
    ;;
  delete-automation)
    shift
    [[ $# -ge 1 ]] || die "Użycie: hx delete-automation TARGET"
    target="$1"
    shift
    output="$(run_sync_payload talkhalokal delete-automation --target "${target}" --match-by alias --backup-dir "${HX_REMOTE_BACKUP_DIR}" "$@")" || exit 1
    printf '%s' "${output}" | render_compact_tx_summary
    ;;
  upsert-script)
    shift
    [[ $# -ge 1 ]] || die "Użycie: hx upsert-script FILE [TARGET]"
    block_file="$1"
    shift
    block_b64="$(file_base64_single_line "${block_file}")"
    if [[ $# -ge 1 && "${1:0:2}" != "--" ]]; then
      target="$1"
      shift
      output="$(run_sync_payload talkhalokal upsert-script --block-base64 "${block_b64}" --target "${target}" --match-by alias --backup-dir "${HX_REMOTE_BACKUP_DIR}" "$@")" || exit 1
    else
      alias_value="$(yaml_alias_from_file "${block_file}")"
      [[ -n "${alias_value}" ]] || die "Nie udało się odczytać alias z pliku skryptu: ${block_file}"
      script_key="$(slugify_identifier "${alias_value}")"
      [[ -n "${script_key}" ]] || die "Nie udało się zbudować klucza skryptu z aliasu: ${alias_value}"
      output="$(run_sync_payload talkhalokal upsert-script --block-base64 "${block_b64}" --key "${script_key}" --match-by alias --backup-dir "${HX_REMOTE_BACKUP_DIR}" "$@")" || exit 1
    fi
    printf '%s' "${output}" | render_compact_tx_summary
    ;;
  delete-script)
    shift
    [[ $# -ge 1 ]] || die "Użycie: hx delete-script TARGET"
    target="$1"
    shift
    output="$(run_sync_payload talkhalokal delete-script --target "${target}" --match-by alias --backup-dir "${HX_REMOTE_BACKUP_DIR}" "$@")" || exit 1
    printf '%s' "${output}" | render_compact_tx_summary
    ;;
  helper-upsert)
    shift
    [[ $# -ge 3 ]] || die "Użycie: hx helper-upsert KIND HELPER ITEM_FILE"
    kind="$1"
    helper="$2"
    item_file="$3"
    shift 3
    item_json="$(read_file_text "${item_file}")"
    output="$(run_sync_payload talkhalokal helper-upsert --kind "${kind}" --helper "${helper}" --item-json "${item_json}" --backup-dir "${HX_REMOTE_BACKUP_DIR}" "$@")" || exit 1
    printf '%s' "${output}" | render_compact_tx_summary
    ;;
  helper-delete)
    shift
    [[ $# -ge 2 ]] || die "Użycie: hx helper-delete KIND HELPER"
    kind="$1"
    helper="$2"
    shift 2
    output="$(run_sync_payload talkhalokal helper-delete --kind "${kind}" --helper "${helper}" --backup-dir "${HX_REMOTE_BACKUP_DIR}" "$@")" || exit 1
    printf '%s' "${output}" | render_compact_tx_summary
    ;;
  rollback-tx)
    shift
    [[ $# -ge 1 ]] || die "Użycie: hx rollback-tx TX_ID"
    run_sync_payload talkhalokal rollback --tx-id "$1"
    ;;
  ""|-h|--help|help)
    usage
    ;;
  *)
    die "Nieznana komenda: ${cmd}"
    ;;
esac
