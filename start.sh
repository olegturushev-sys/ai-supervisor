#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR"
FRONTEND_DIR="$ROOT_DIR/frontend"
LOG_DIR="$ROOT_DIR/logs"

BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_HOST="${FRONTEND_HOST:-127.0.0.1}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"

VENV_DIR="${VENV_DIR:-$ROOT_DIR/.venv}"
USE_VENV="${USE_VENV:-auto}" # auto|1|0
INSTALL_DEPS="${INSTALL_DEPS:-auto}" # auto|1|0
INSTALL_ML_DEPS="${INSTALL_ML_DEPS:-auto}" # auto|1|0

MODE="${1:-all}" # all|backend|frontend|check

ts() { date +"%Y-%m-%d_%H-%M-%S"; }
info() { printf "\033[1;34m[INFO]\033[0m %s\n" "$*"; }
warn() { printf "\033[1;33m[WARN]\033[0m %s\n" "$*"; }
err() { printf "\033[1;31m[ERR ]\033[0m %s\n" "$*"; }

have() { command -v "$1" >/dev/null 2>&1; }

require_cmd() {
  local cmd="$1"
  if ! have "$cmd"; then
    err "Missing command: $cmd"
    exit 1
  fi
}

_run_bg_session() {
  local log_file="$1"
  shift
  if have setsid; then
    setsid "$@" >"$log_file" 2>&1 &
  else
    warn "setsid not found; using best-effort background mode."
    "$@" >"$log_file" 2>&1 &
  fi
  RUN_BG_PID=$!
}

_kill_tree() {
  local sig="$1"
  local pid="$2"
  local kids=""
  kids="$(pgrep -P "$pid" 2>/dev/null || true)"
  if [[ -n "${kids:-}" ]]; then
    local k
    for k in $kids; do
      _kill_tree "$sig" "$k"
    done
  fi
  kill "-$sig" "$pid" >/dev/null 2>&1 || true
}

_stop_pidfile() {
  local pid_file="$1"
  local name="$2"
  [[ -f "$pid_file" ]] || return 0

  local pid
  pid="$(cat "$pid_file" 2>/dev/null || true)"
  rm -f "$pid_file" || true

  if [[ -z "${pid:-}" ]]; then
    return 0
  fi
  if ! kill -0 "$pid" >/dev/null 2>&1; then
    return 0
  fi

  local pgid=""
  pgid="$(ps -o pgid= -p "$pid" 2>/dev/null | tr -d ' ' || true)"

  if [[ -n "${pgid:-}" && "$pgid" != "$$" ]]; then
    info "Stopping $name process group $pgid"
    kill -TERM "-$pgid" >/dev/null 2>&1 || true
  else
    info "Stopping $name process tree (pid $pid)"
    _kill_tree TERM "$pid"
  fi

  local i
  for i in {1..25}; do
    if ! kill -0 "$pid" >/dev/null 2>&1; then
      return 0
    fi
    sleep 0.1
  done

  warn "$name still running; sending KILL"
  if [[ -n "${pgid:-}" && "$pgid" != "$$" ]]; then
    kill -KILL "-$pgid" >/dev/null 2>&1 || true
  else
    _kill_tree KILL "$pid"
  fi
}

load_env_file() {
  local env_file="$1"
  [[ -f "$env_file" ]] || return 0

  # shellcheck disable=SC1090
  set -a
  source "$env_file"
  set +a
}

maybe_prompt_hf_token() {
  if [[ -n "${HF_TOKEN:-}" ]]; then
    return 0
  fi

  warn "HF_TOKEN is not set. Optional: needed for WhisperX models or GigaAM longform VAD; diarization uses local/fast engine."
  read -r -p "Enter HF_TOKEN (leave empty to skip): " token || true
  if [[ -z "${token:-}" ]]; then
    return 0
  fi
  export HF_TOKEN="$token"

  read -r -p "Save HF_TOKEN to $ROOT_DIR/.env ? [y/N] " save || true
  if [[ "${save:-}" =~ ^[Yy]$ ]]; then
    # Create or update .env safely (single key).
    if [[ -f "$ROOT_DIR/.env" ]]; then
      if grep -q '^HF_TOKEN=' "$ROOT_DIR/.env"; then
        # macOS-compatible in-place edit.
        sed -i '' "s|^HF_TOKEN=.*$|HF_TOKEN=$HF_TOKEN|" "$ROOT_DIR/.env"
      else
        printf "\nHF_TOKEN=%s\n" "$HF_TOKEN" >>"$ROOT_DIR/.env"
      fi
    else
      printf "HF_TOKEN=%s\n" "$HF_TOKEN" >"$ROOT_DIR/.env"
    fi
    chmod 600 "$ROOT_DIR/.env" || true
    info "Saved HF_TOKEN to .env (chmod 600). Do NOT commit this file."
  fi
}

python_bin() {
  if [[ "$USE_VENV" == "0" ]]; then
    echo "python3"
    return 0
  fi

  if [[ "$USE_VENV" == "1" || "$USE_VENV" == "auto" ]]; then
    if [[ -x "$VENV_DIR/bin/python" ]]; then
      echo "$VENV_DIR/bin/python"
      return 0
    fi
  fi
  echo "python3"
}

ensure_venv() {
  if [[ "$USE_VENV" == "0" ]]; then
    return 0
  fi
  if [[ -x "$VENV_DIR/bin/python" ]]; then
    return 0
  fi
  info "Creating venv at $VENV_DIR"
  python3 -m venv "$VENV_DIR"
}

pip_install_backend_deps() {
  local py
  py="$(python_bin)"
  if [[ "$INSTALL_DEPS" == "0" ]]; then
    return 0
  fi
  if [[ "$INSTALL_DEPS" == "auto" ]]; then
    local extra=""
    if [[ "${DIARIZATION_ENGINE:-}" == "local" || "${DIARIZATION_ENGINE:-}" == "fast" ]]; then
      extra=", sklearn, speechbrain"
    fi
    # Only install if imports succeed.
    # IMPORTANT: backend/requirements.txt includes gigaam runtime deps (hydra-core, omegaconf, soundfile, numpy).
    if "$py" -c "import fastapi, uvicorn, multipart, hydra, omegaconf, soundfile, numpy, sentencepiece${extra}" >/dev/null 2>&1; then
      return 0
    fi
  fi
  info "Installing backend deps from backend/requirements.txt"
  "$py" -m pip install -U pip setuptools wheel
  "$py" -m pip install -r "$ROOT_DIR/backend/requirements.txt"
}

pip_install_ml_deps() {
  local py
  py="$(python_bin)"

  if [[ "$INSTALL_ML_DEPS" == "0" ]]; then
    return 0
  fi

  # Default: if you're using the backend, you likely want transcription to work.
  # In auto mode, only install the heavy stack if it's missing.
  if [[ "$INSTALL_ML_DEPS" == "auto" ]]; then
    if "$py" -c "import torch, numpy, soundfile, hydra" >/dev/null 2>&1; then
      return 0
    fi
  fi

  if [[ -f "$ROOT_DIR/requirements.txt" ]]; then
    info "Installing ML deps from requirements.txt (may take a while)"
    "$py" -m pip install -r "$ROOT_DIR/requirements.txt"
  else
    warn "requirements.txt not found; skipping ML deps install"
  fi
}

ensure_frontend_deps() {
  if [[ "$INSTALL_DEPS" == "0" ]]; then
    return 0
  fi
  if [[ -d "$FRONTEND_DIR/node_modules" ]]; then
    return 0
  fi
  info "Installing frontend deps (npm install)"
  (cd "$FRONTEND_DIR" && npm install)
}

health_check() {
  local url="http://$BACKEND_HOST:$BACKEND_PORT/health"
  info "Health check: $url"
  for i in {1..30}; do
    if curl -fsS "$url" >/dev/null 2>&1; then
      info "Backend is up."
      return 0
    fi
    sleep 0.5
  done
  err "Backend did not become healthy in time."
  return 1
}

start_backend() {
  mkdir -p "$LOG_DIR"
  local py backend_log
  py="$(python_bin)"
  backend_log="$LOG_DIR/backend_$(ts).log"
  info "Starting backend (logs: $backend_log)"
  RUN_BG_PID=""
  _run_bg_session "$backend_log" bash -lc "
    cd \"$BACKEND_DIR\"
    export PYTHONPATH=\"$ROOT_DIR/vendor/gigaam:$ROOT_DIR/vendor/whisperx:${PYTHONPATH:-}\"
    exec \"$py\" -m uvicorn backend.app.main:app --reload --host \"$BACKEND_HOST\" --port \"$BACKEND_PORT\"
  "
  echo "${RUN_BG_PID:-}" >"$LOG_DIR/backend.pid"
}

start_frontend() {
  mkdir -p "$LOG_DIR"
  local fe_log
  fe_log="$LOG_DIR/frontend_$(ts).log"
  info "Starting frontend (logs: $fe_log)"
  RUN_BG_PID=""
  _run_bg_session "$fe_log" bash -lc "
    cd \"$FRONTEND_DIR\"
    exec npm run dev -- --host \"$FRONTEND_HOST\"
  "
  echo "${RUN_BG_PID:-}" >"$LOG_DIR/frontend.pid"
}

stop_all() {
  if [[ "${_STOPPING:-0}" == "1" ]]; then
    return 0
  fi
  _STOPPING=1
  info "Stopping processes..."
  _stop_pidfile "$LOG_DIR/frontend.pid" "frontend"
  _stop_pidfile "$LOG_DIR/backend.pid" "backend"
}

print_urls() {
  printf "\n"
  info "Backend:   http://$BACKEND_HOST:$BACKEND_PORT"
  info "Swagger:   http://$BACKEND_HOST:$BACKEND_PORT/docs"
  info "Frontend:  http://$FRONTEND_HOST:$FRONTEND_PORT (preferred; Vite may pick next free port)"
  printf "\n"
  info "Logs:      $LOG_DIR/"
  printf "\n"
}

on_int() {
  stop_all
  exit 130
}

trap on_int INT
trap stop_all TERM
trap stop_all EXIT

main() {
  require_cmd curl
  require_cmd node
  require_cmd npm
  require_cmd python3

  load_env_file "$ROOT_DIR/.env"
  load_env_file "$FRONTEND_DIR/.env.development"

  maybe_prompt_hf_token

  if [[ "$MODE" == "check" ]]; then
    info "Quick checks"
    info "python: $(python3 -V 2>/dev/null || true)"
    info "node:   $(node -v 2>/dev/null || true)"
    info "npm:    $(npm -v 2>/dev/null || true)"
    info "HF_TOKEN set: $([[ -n "${HF_TOKEN:-}" ]] && echo yes || echo no)"
    exit 0
  fi

  ensure_venv
  pip_install_backend_deps
  pip_install_ml_deps
  ensure_frontend_deps

  case "$MODE" in
    backend)
      start_backend
      health_check
      print_urls
      info "Press Ctrl+C to stop."
      wait
      ;;
    frontend)
      start_frontend
      print_urls
      info "Press Ctrl+C to stop."
      wait
      ;;
    all|*)
      start_backend
      health_check
      start_frontend
      print_urls
      info "Press Ctrl+C to stop."
      wait
      ;;
  esac
}

main "$@"

