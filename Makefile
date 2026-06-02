.PHONY: dev dev-backend dev-frontend install clean

# ── Start everything ──────────────────────────────────────
dev:
	@echo "Starting Unorthodox Writer..."
	@echo "  Backend  → http://localhost:8000"
	@echo "  Frontend → http://localhost:5173"
	@echo ""
	@# Start backend in background
	cd backend && .venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000 --reload &
	@# Start frontend in background
	cd frontend && npm run dev &
	@echo ""
	@echo "Both services running. Press Ctrl+C to stop."
	@wait

# ── Individual services ───────────────────────────────────
dev-backend:
	cd backend && .venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000 --reload

dev-frontend:
	cd frontend && npm run dev

# ── Setup ─────────────────────────────────────────────────
install:
	@echo "Setting up backend venv..."
	cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
	@echo ""
	@echo "Setting up engine..."
	cd backend && .venv/bin/pip install httpx
	@echo ""
	@echo "Setting up frontend..."
	cd frontend && npm install
	@echo ""
	@echo "✓ All dependencies installed."
	@echo ""
	@echo "To start: make dev"

# ── Cleanup ───────────────────────────────────────────────
clean:
	rm -rf backend/__pycache__ backend/routes/__pycache__ backend/middleware/__pycache__ backend/.pytest_cache
	rm -rf engine/__pycache__ engine/backends/__pycache__
	rm -rf frontend/dist frontend/node_modules/.vite
	@echo "Cleaned."
