#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DIR="$ROOT_DIR/.run"
DOTENV_FILE="$ROOT_DIR/.env"

BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
PERPLEXITY_CONTAINER="${PERPLEXITY_CONTAINER:-perplexity}"
PERPLEXITY_IMAGE="${PERPLEXITY_IMAGE:-ghcr.io/ardzz/perplexity-scrape:latest}"
PERPLEXITY_ENV_FILE="${PERPLEXITY_ENV_FILE:-$ROOT_DIR/.perplexity.env}"
PERPLEXITY_REFRESH_ON_START="${PERPLEXITY_REFRESH_ON_START:-1}"

mkdir -p "$RUN_DIR"

dotenv_get() {
  local key="$1"
  local default="${2:-}"

  if [[ -f "$DOTENV_FILE" ]]; then
    local line
    line="$(grep -E "^${key}=" "$DOTENV_FILE" | tail -n1 || true)"
    if [[ -n "$line" ]]; then
      local value="${line#*=}"
      value="${value%%#*}"
      value="$(echo "$value" | xargs)"
      if [[ -n "$value" ]]; then
        echo "$value"
        return
      fi
    fi
  fi

  echo "$default"
}

env_file_has_value() {
  local file_path="$1"
  local key="$2"

  [[ -f "$file_path" ]] || return 1

  local line value
  line="$(grep -E "^${key}=" "$file_path" | tail -n1 || true)"
  [[ -n "$line" ]] || return 1

  value="${line#*=}"
  value="${value%%#*}"
  value="$(echo "$value" | xargs)"
  [[ -n "$value" ]]
}

perplexity_env_ready_for_recreate() {
  env_file_has_value "$PERPLEXITY_ENV_FILE" "PERPLEXITY_SESSION_TOKEN" && \
  env_file_has_value "$PERPLEXITY_ENV_FILE" "PERPLEXITY_CF_CLEARANCE"
}

AWS_PROFILE_NAME="${AWS_PROFILE:-$(dotenv_get AWS_PROFILE "")}"
PERPLEXITY_BASE_URL_EFFECTIVE="${PERPLEXITY_BASE_URL:-$(dotenv_get PERPLEXITY_BASE_URL "http://127.0.0.1:8045/v1")}"
PERPLEXITY_MODEL_EFFECTIVE="${PERPLEXITY_MODEL:-$(dotenv_get PERPLEXITY_MODEL "claude46sonnetthinking")}"
PERPLEXITY_API_KEY_EFFECTIVE="${PERPLEXITY_API_KEY:-$(dotenv_get PERPLEXITY_API_KEY "")}"
PERPLEXITY_FALLBACK_API_KEY="${PERPLEXITY_FALLBACK_API_KEY:-$(dotenv_get PERPLEXITY_FALLBACK_API_KEY "")}"
PERPLEXITY_FALLBACK_MODEL="${PERPLEXITY_FALLBACK_MODEL:-$(dotenv_get PERPLEXITY_FALLBACK_MODEL "sonar-pro")}"

PERPLEXITY_BASE_URL_EFFECTIVE="${PERPLEXITY_BASE_URL_EFFECTIVE%/}"

enable_perplexity_sonar_fallback() {
  if [[ -z "$PERPLEXITY_FALLBACK_API_KEY" ]]; then
    return 1
  fi

  export PERPLEXITY_BASE_URL="https://api.perplexity.ai"
  export PERPLEXITY_API_KEY="$PERPLEXITY_FALLBACK_API_KEY"
  export PERPLEXITY_MODEL="$PERPLEXITY_FALLBACK_MODEL"

  PERPLEXITY_BASE_URL_EFFECTIVE="$PERPLEXITY_BASE_URL"
  PERPLEXITY_API_KEY_EFFECTIVE="$PERPLEXITY_API_KEY"
  PERPLEXITY_MODEL_EFFECTIVE="$PERPLEXITY_MODEL"
  PERPLEXITY_BASE_URL_EFFECTIVE="${PERPLEXITY_BASE_URL_EFFECTIVE%/}"

  echo "[perplexity] switched backend to official Sonar fallback (${PERPLEXITY_MODEL_EFFECTIVE})"
  return 0
}

is_proxy_healthy() {
  local payload response content
  payload="$(printf '{"model":"%s","messages":[{"role":"user","content":"Respond with only the word ALIVE"}],"stream":false}' "$PERPLEXITY_MODEL_EFFECTIVE")"

  local -a curl_args=(
    -fsS
    --max-time 25
    "$PERPLEXITY_BASE_URL_EFFECTIVE/chat/completions"
    -H "Content-Type: application/json"
  )

  if [[ -n "$PERPLEXITY_API_KEY_EFFECTIVE" ]]; then
    curl_args+=( -H "Authorization: Bearer $PERPLEXITY_API_KEY_EFFECTIVE" )
  fi

  curl_args+=( -d "$payload" )

  if ! response="$(curl "${curl_args[@]}" 2>/dev/null)"; then
    return 1
  fi

  if command -v jq >/dev/null 2>&1; then
    content="$(printf '%s' "$response" | jq -r '.choices[0].message.content // empty' 2>/dev/null || true)"
  else
    content="$(printf '%s' "$response" | sed -n 's/.*"content":"\([^"]*\)".*/\1/p' | head -n1)"
  fi

  content="$(echo "$content" | xargs)"
  [[ -n "$content" ]] && [[ "$content" == *"ALIVE"* ]]
}

recreate_perplexity_container_from_env_file() {
  if [[ ! -f "$PERPLEXITY_ENV_FILE" ]]; then
    return 1
  fi

  echo "[perplexity] recreating ${PERPLEXITY_CONTAINER} from $PERPLEXITY_ENV_FILE"
  docker rm -f "$PERPLEXITY_CONTAINER" >/dev/null 2>&1 || true
  docker run -d \
    --name "$PERPLEXITY_CONTAINER" \
    -p 8045:8045 \
    --env-file "$PERPLEXITY_ENV_FILE" \
    "$PERPLEXITY_IMAGE" \
    python -m uvicorn unified_service:app --host 0.0.0.0 --port 8045 >/dev/null
}

ensure_aws_sso_session() {
  if ! command -v aws >/dev/null 2>&1; then
    echo "[aws] aws cli not found; skipping SSO refresh"
    return 0
  fi

  if [[ -z "$AWS_PROFILE_NAME" ]]; then
    echo "[aws] AWS_PROFILE not set; skipping SSO refresh"
    return 0
  fi

  if aws sts get-caller-identity --profile "$AWS_PROFILE_NAME" >/dev/null 2>&1; then
    echo "[aws] SSO session is valid for profile ${AWS_PROFILE_NAME}"
    return 0
  fi

  echo "[aws] SSO session expired for profile ${AWS_PROFILE_NAME}; running aws sso login..."
  aws sso login --profile "$AWS_PROFILE_NAME"

  if ! aws sts get-caller-identity --profile "$AWS_PROFILE_NAME" >/dev/null 2>&1; then
    echo "[aws] failed to refresh SSO session for profile ${AWS_PROFILE_NAME}"
    return 1
  fi

  echo "[aws] SSO refresh complete"
}

is_port_listening() {
  local port="$1"
  lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1
}

ensure_docker_daemon() {
  if docker info >/dev/null 2>&1; then
    return 0
  fi

  if command -v colima >/dev/null 2>&1; then
    echo "[perplexity] Docker daemon not reachable; starting Colima..."
    colima start >/dev/null
  fi

  if docker info >/dev/null 2>&1; then
    return 0
  fi

  echo "[perplexity] failed to connect to Docker daemon."
  echo "[perplexity] start Docker Desktop or Colima, then rerun this script."
  return 1
}

start_perplexity() {
  local disable_val
  disable_val="$(dotenv_get DISABLE_PERPLEXITY "false")"
  if [[ "$disable_val" == "true" ]]; then
    echo "[perplexity] disabled via .env (DISABLE_PERPLEXITY=true); skipping scraper container launch and health check"
    return 0
  fi

  if ! command -v docker >/dev/null 2>&1; then
    echo "[perplexity] docker is not installed or not in PATH"
    return 1
  fi

  ensure_docker_daemon

  if [[ "$PERPLEXITY_REFRESH_ON_START" == "1" ]] && perplexity_env_ready_for_recreate; then
    recreate_perplexity_container_from_env_file
  elif [[ "$PERPLEXITY_REFRESH_ON_START" == "1" ]] && [[ -f "$PERPLEXITY_ENV_FILE" ]]; then
    echo "[perplexity] $PERPLEXITY_ENV_FILE exists but required token fields are blank; skipping auto-recreate"
  fi

  if docker ps --filter "name=^/${PERPLEXITY_CONTAINER}$" --format "{{.Names}}" | grep -q "^${PERPLEXITY_CONTAINER}$"; then
    echo "[perplexity] ${PERPLEXITY_CONTAINER} is already running"
  elif docker ps -a --filter "name=^/${PERPLEXITY_CONTAINER}$" --format "{{.Names}}" | grep -q "^${PERPLEXITY_CONTAINER}$"; then
    docker start "$PERPLEXITY_CONTAINER" >/dev/null
    echo "[perplexity] started ${PERPLEXITY_CONTAINER}"
  elif perplexity_env_ready_for_recreate; then
    recreate_perplexity_container_from_env_file
    echo "[perplexity] created ${PERPLEXITY_CONTAINER} from $PERPLEXITY_ENV_FILE"
  else
    echo "[perplexity] container '${PERPLEXITY_CONTAINER}' does not exist."
    echo "[perplexity] create $PERPLEXITY_ENV_FILE with PERPLEXITY_SESSION_TOKEN + PERPLEXITY_CF_CLEARANCE to auto-create it."
    return 1
  fi

  if is_proxy_healthy; then
    echo "[perplexity] proxy health check passed"
    return 0
  fi

  echo "[perplexity] proxy health check failed."
  if perplexity_env_ready_for_recreate; then
    recreate_perplexity_container_from_env_file
    if is_proxy_healthy; then
      echo "[perplexity] proxy recovered after refresh"
      return 0
    fi
  elif [[ -f "$PERPLEXITY_ENV_FILE" ]]; then
    echo "[perplexity] $PERPLEXITY_ENV_FILE exists but required token fields are blank; cannot auto-refresh proxy"
  fi

  echo "[perplexity] proxy is still unhealthy; refresh cookie values in $PERPLEXITY_ENV_FILE"

  if enable_perplexity_sonar_fallback; then
    if is_proxy_healthy; then
      echo "[perplexity] Sonar fallback health check passed"
      return 0
    fi
    echo "[perplexity] Sonar fallback configured but health check failed"
  else
    echo "[perplexity] no Sonar fallback key configured (set PERPLEXITY_FALLBACK_API_KEY in .env)"
  fi

  return 1
}

start_backend() {
  if is_port_listening "$BACKEND_PORT"; then
    echo "[backend] port ${BACKEND_PORT} already in use; assuming backend is running"
    return 0
  fi

  local python_bin="$ROOT_DIR/.venv/bin/python"
  if [[ ! -x "$python_bin" ]]; then
    echo "[backend] missing Python env at $python_bin"
    echo "[backend] create or activate your .venv first"
    return 1
  fi

  nohup "$python_bin" -m uvicorn backend.main:app --reload --host 0.0.0.0 --port "$BACKEND_PORT" \
    >"$RUN_DIR/backend.log" 2>&1 &
  echo $! >"$RUN_DIR/backend.pid"
  echo "[backend] started on port ${BACKEND_PORT} (log: $RUN_DIR/backend.log)"
}

start_frontend() {
  if is_port_listening "$FRONTEND_PORT"; then
    echo "[frontend] port ${FRONTEND_PORT} already in use; assuming frontend is running"
    return 0
  fi

  if ! command -v npm >/dev/null 2>&1; then
    echo "[frontend] npm is not installed or not in PATH"
    return 1
  fi

  nohup npm --prefix "$ROOT_DIR/frontend" run dev -- --host 0.0.0.0 --port "$FRONTEND_PORT" \
    >"$RUN_DIR/frontend.log" 2>&1 &
  echo $! >"$RUN_DIR/frontend.pid"
  echo "[frontend] started on port ${FRONTEND_PORT} (log: $RUN_DIR/frontend.log)"
}

echo "Starting development stack from $ROOT_DIR"
ensure_aws_sso_session
start_perplexity
start_backend
start_frontend

echo ""
echo "All services are up:"
if [[ "$(dotenv_get DISABLE_PERPLEXITY "false")" != "true" ]]; then
  echo "- Perplexity proxy: http://127.0.0.1:8045"
fi
echo "- Backend API:      http://127.0.0.1:${BACKEND_PORT}"
echo "- Frontend app:     http://127.0.0.1:${FRONTEND_PORT}"