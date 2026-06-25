# -----------------------------------------------------------------------------
# lib_deadman.sh — VM-side budget backstop (forgot-the-GPU-overnight insurance).
# Installs a one-shot @reboot cron that self-terminates this instance via Verda API
# after max_session_hours + 30 minutes. NEVER passes models volume IDs to delete.
# -----------------------------------------------------------------------------

geopoai_install_deadman_cron() {
  local max_hours="${GEOPOAI_MAX_SESSION_HOURS:-8}"
  local grace_min=30
  local cred_dir="/root/.config/geopoai"
  local cred_file="${cred_dir}/verda_credentials"
  local terminate_script="/usr/local/bin/geopoai-deadman-terminate.sh"
  local log_file="/var/log/geopoai-deadman.log"
  local sleep_sec=$(( (max_hours * 60 + grace_min) * 60 ))

  echo "[geopoai:deadman] installing backstop (max_session_hours=${max_hours} + ${grace_min}m grace)" >&2

  install -d -m 700 "${cred_dir}"
  if [[ -n "${VERDA_CLIENT_ID:-}" && -n "${VERDA_CLIENT_SECRET:-}" ]]; then
    umask 077
    cat >"${cred_file}" <<EOF
VERDA_CLIENT_ID=${VERDA_CLIENT_ID}
VERDA_CLIENT_SECRET=${VERDA_CLIENT_SECRET}
EOF
    chmod 600 "${cred_file}"
  else
    echo "[geopoai:deadman] WARNING: VERDA credentials not set — VM backstop disabled" >&2
    return 0
  fi

  cat >"${terminate_script}" <<'EOSCRIPT'
#!/usr/bin/env bash
set -euo pipefail
LOG="/var/log/geopoai-deadman.log"
CRED="/root/.config/geopoai/verda_credentials"
API_BASE="${VERDA_BASE_URL:-https://api.verda.com/v1}"

exec >>"${LOG}" 2>&1
echo "[geopoai:deadman] terminate start $(date -Is) host=$(hostname)"

if [[ ! -f "${CRED}" ]]; then
  echo "[geopoai:deadman] ERROR: missing credentials at ${CRED}"
  exit 1
fi
# shellcheck source=/dev/null
source "${CRED}"

if [[ -z "${VERDA_CLIENT_ID:-}" || -z "${VERDA_CLIENT_SECRET:-}" ]]; then
  echo "[geopoai:deadman] ERROR: empty Verda credentials"
  exit 1
fi

TOKEN_JSON="$(curl -fsS -X POST "${API_BASE}/oauth2/token" \
  -H "Content-Type: application/json" \
  -d "{\"grant_type\":\"client_credentials\",\"client_id\":\"${VERDA_CLIENT_ID}\",\"client_secret\":\"${VERDA_CLIENT_SECRET}\"}")"
ACCESS_TOKEN="$(echo "${TOKEN_JSON}" | jq -r '.access_token // empty')"
if [[ -z "${ACCESS_TOKEN}" ]]; then
  echo "[geopoai:deadman] ERROR: oauth token failed: ${TOKEN_JSON}"
  exit 1
fi

HOST="$(hostname)"
INSTANCE_ID="${GEOPOAI_INSTANCE_ID:-}"
if [[ -z "${INSTANCE_ID}" ]]; then
  INSTANCES_JSON="$(curl -fsS -H "Authorization: Bearer ${ACCESS_TOKEN}" "${API_BASE}/instances")"
  INSTANCE_ID="$(echo "${INSTANCES_JSON}" | jq -r --arg h "${HOST}" '.[] | select(.hostname == $h or .name == $h) | .id' | head -1)"
fi
if [[ -z "${INSTANCE_ID}" ]]; then
  echo "[geopoai:deadman] ERROR: could not resolve instance id for host ${HOST}"
  exit 1
fi

echo "[geopoai:deadman] DELETING instance ${INSTANCE_ID} (models volume NOT in volume_ids)"
HTTP_CODE="$(curl -fsS -o /tmp/geopoai-deadman-resp.json -w '%{http_code}' \
  -X PUT "${API_BASE}/instances" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Content-Type: application/json" \
  -d "{\"action\":\"delete\",\"id\":\"${INSTANCE_ID}\"}")"
echo "[geopoai:deadman] API response ${HTTP_CODE}: $(cat /tmp/geopoai-deadman-resp.json)"
echo "[geopoai:deadman] DONE $(date -Is)"
EOSCRIPT
  chmod 755 "${terminate_script}"

  cat >/etc/cron.d/geopoai-deadman <<EOF
# GeoPoAI VM dead-man backstop — self-terminate after budget cap (+ grace)
@reboot root sleep ${sleep_sec} && ${terminate_script}
EOF
  chmod 644 /etc/cron.d/geopoai-deadman
  echo "[geopoai:deadman] cron installed; fires ~$(( sleep_sec / 60 )) minutes after boot" >&2
}
