.PHONY: up up-build down logs test test-security migrate seed seed-dev backend frontend agent build demo-sprint1 installer-linux deploy-ubuntu

COMPOSE = docker compose -f deploy/docker-compose.yml

# One-shot Ubuntu bootstrap (Docker + env + build + up + health).
deploy-ubuntu:
	bash scripts/deploy-ubuntu.sh

# Start stack using local images (does not contact Docker Hub).
up:
	$(COMPOSE) up -d

# Rebuild images then start.
up-build:
	$(COMPOSE) build
	$(COMPOSE) up -d

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f api

# Prefer Docker API container (matches Compose DB). Host venv is a fallback.
migrate:
	@$(COMPOSE) exec -T api alembic upgrade head || (cd backend && . .venv/bin/activate && alembic upgrade head)

seed:
	@$(COMPOSE) exec -T api python scripts/seed_platform_admin.py
	@$(COMPOSE) exec -T api python scripts/seed_dev_tenant.py

seed-dev:
	@$(COMPOSE) exec -T api python scripts/seed_dev_tenant.py

test-security:
	cd backend && . .venv/bin/activate && pytest tests/security/ -v

test:
	cd backend && . .venv/bin/activate && pytest -v

backend-dev:
	cd backend && . .venv/bin/activate && uvicorn ai_spm.main:app --reload --app-dir src --port 8000

frontend-dev:
	cd frontend && npm run dev

agent-build:
	cd agent && cargo build --release -p agent-service -p agent-installer

installer-linux:
	bash scripts/build-linux-installer.sh

certs:
	bash scripts/generate-certs.sh

demo-sprint1:
	bash scripts/demo-sprint1.sh

build:
	$(COMPOSE) build
