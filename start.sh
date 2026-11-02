#!/usr/bin/env bash
# STCS — khởi chạy nhanh.
#   ./start.sh          Chế độ phát triển: backend :8010 + Vite :5173 (hot reload)
#   ./start.sh prod     Build frontend rồi phục vụ toàn bộ hệ thống từ backend :8010
#   ./start.sh test     Chạy bộ kiểm thử backend + typecheck frontend
#   ./start.sh reset    Xoá CSDL và seed lại dữ liệu mẫu khi khởi động
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"
MODE="${1:-dev}"
export STCS_PORT="${STCS_PORT:-8010}"

c_info() { printf "\033[1;34m[STCS]\033[0m %s\n" "$*"; }
c_err() { printf "\033[1;31m[STCS]\033[0m %s\n" "$*" >&2; }

need() { command -v "$1" >/dev/null 2>&1 || { c_err "Thiếu '$1' — hãy cài đặt trước."; exit 1; }; }
need python3
need node
need npm

setup_backend() {
  if [ ! -x "$BACKEND/.venv/bin/python" ]; then
    c_info "Tạo môi trường Python (.venv)…"
    python3 -m venv "$BACKEND/.venv"
  fi
  if ! "$BACKEND/.venv/bin/python" -c "import fastapi, sqlalchemy, jose, bcrypt" >/dev/null 2>&1; then
    c_info "Cài thư viện backend…"
    "$BACKEND/.venv/bin/pip" install -q --upgrade pip
    "$BACKEND/.venv/bin/pip" install -q -r "$BACKEND/requirements.txt"
  fi
}

setup_frontend() {
  if [ ! -d "$FRONTEND/node_modules" ]; then
    c_info "Cài thư viện frontend (npm install)…"
    (cd "$FRONTEND" && npm install --no-audit --no-fund)
  fi
}

port_busy() { (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null && exec 3>&- && return 0 || return 1; }

case "$MODE" in
  reset)
    rm -f "$BACKEND"/data/stcs.db*
    c_info "Đã xoá CSDL. Dữ liệu mẫu sẽ được seed lại ở lần khởi động tới."
    exit 0
    ;;
  test)
    setup_backend
    setup_frontend
    (cd "$BACKEND" && .venv/bin/python -m pytest tests -q)
    (cd "$FRONTEND" && npx tsc -b --noEmit && echo "Frontend typecheck: OK")
    exit 0
    ;;
esac

setup_backend
setup_frontend

if port_busy "$STCS_PORT"; then
  c_err "Cổng $STCS_PORT đang được dùng. Đặt cổng khác: STCS_PORT=8020 ./start.sh"
  exit 1
fi

PIDS=()
cleanup() {
  c_info "Đang dừng hệ thống…"
  for p in "${PIDS[@]:-}"; do kill "$p" 2>/dev/null || true; done
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

if [ "$MODE" = "prod" ]; then
  c_info "Build frontend…"
  (cd "$FRONTEND" && npm run build)
  export STCS_CORS_ORIGINS="http://localhost:$STCS_PORT,http://127.0.0.1:$STCS_PORT"
  c_info "Khởi động STCS tại http://localhost:$STCS_PORT"
  (cd "$BACKEND" && exec .venv/bin/python run.py) &
  PIDS+=($!)
else
  if port_busy 5173; then
    c_err "Cổng 5173 (Vite) đang được dùng."
    exit 1
  fi
  c_info "Khởi động backend tại http://localhost:$STCS_PORT (API docs: /docs)"
  (cd "$BACKEND" && exec .venv/bin/python run.py) &
  PIDS+=($!)
  for _ in $(seq 1 40); do
    port_busy "$STCS_PORT" && break
    sleep 0.5
  done
  c_info "Khởi động giao diện tại http://localhost:5173"
  (cd "$FRONTEND" && STCS_BACKEND="http://127.0.0.1:$STCS_PORT" exec npx vite --port 5173 --strictPort) &
  PIDS+=($!)
fi

c_info "Tài khoản demo: admin/admin123 · operator/operator123 · manager/manager123  (Ctrl+C để dừng)"
wait
