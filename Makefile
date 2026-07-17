.PHONY: up up-build down logs test test-security migrate seed seed-dev backend frontend agent build demo-sprint1 installer-linux

COMPOSE = docker compose -f deploy/docker-compose.yml

# Start stack using local images (does not contact Docker Hub).
up:
	$(COMPOSE) up -d

# Rebuild images then start. Uses host network so pulls prefer working IPv4
# when the machine's IPv6 route to Docker Hub is broken.
up-build:
	$(COMPOSE) build --network=host
	$(COMPOSE) up -d

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f api

migrate:
	cd backend && alembic upgrade head

seed:
	cd backend && . .venv/bin/activate && python scripts/seed_platform_admin.py && python scripts/seed_dev_tenant.py

seed-dev:
	cd backend && . .venv/bin/activate && python scripts/seed_dev_tenant.py

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
	$(COMPOSE) build --network=host
