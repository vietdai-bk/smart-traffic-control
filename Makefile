.PHONY: help install dev prod backend frontend build test typecheck reset docker-up docker-down clean

PY := backend/.venv/bin/python
PORT ?= 8010

help:
	@echo "STCS — các lệnh:"
	@echo "  make install    Cài thư viện backend (.venv) và frontend (node_modules)"
	@echo "  make dev        Chạy backend :$(PORT) + frontend :5173 (hot reload)"
	@echo "  make prod       Build frontend và phục vụ toàn bộ từ backend :$(PORT)"
	@echo "  make test       Pytest backend + typecheck frontend"
	@echo "  make build      Build frontend production (frontend/dist)"
	@echo "  make reset      Xoá CSDL SQLite (seed lại khi khởi động)"
	@echo "  make docker-up  Chạy bằng docker compose (http://localhost:8080)"

install:
	python3 -m venv backend/.venv
	backend/.venv/bin/pip install -q --upgrade pip
	backend/.venv/bin/pip install -q -r backend/requirements.txt
	cd frontend && npm install --no-audit --no-fund

dev:
	./start.sh dev

prod:
	./start.sh prod

backend:
	cd backend && STCS_PORT=$(PORT) .venv/bin/python run.py

frontend:
	cd frontend && STCS_BACKEND=http://127.0.0.1:$(PORT) npx vite --port 5173

build:
	cd frontend && npm run build

typecheck:
	cd frontend && npx tsc -b --noEmit

test:
	cd backend && .venv/bin/python -m pytest tests -q
	cd frontend && npx tsc -b --noEmit

reset:
	rm -f backend/data/stcs.db*

docker-up:
	docker compose up --build -d
	@echo "STCS đang chạy tại http://localhost:8080"

docker-down:
	docker compose down

clean:
	rm -rf frontend/dist backend/.pytest_cache
	find backend -name __pycache__ -type d -prune -exec rm -rf {} +
