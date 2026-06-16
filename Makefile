# CopyTrade Sim — dev workflow (Mac/Linux; Windows users: python scripts\dev.py <cmd>)

.PHONY: help up down logs psql migrate test test-unit test-int lint fmt typecheck reset-db seed

help:
	@echo "Available targets:"
	@echo "  up         - Start Postgres + Adminer in Docker"
	@echo "  down       - Stop Docker containers"
	@echo "  logs       - Tail Postgres logs"
	@echo "  psql       - Open psql in the running container"
	@echo "  migrate    - Run alembic upgrade head"
	@echo "  test-unit  - Run only unit tests (no DB needed)"
	@echo "  test-int   - Run only integration tests (requires Docker)"
	@echo "  lint       - ruff check"
	@echo "  fmt        - ruff format"
	@echo "  typecheck  - mypy"
	@echo "  reset-db   - Drop volumes, restart, re-migrate"
	@echo "  seed       - Seed target entities"

up:
	docker compose up -d db

down:
	docker compose down

logs:
	docker compose logs -f db

psql:
	docker compose exec db psql -U copytrade_user -d mirror_db

migrate:
	cd backend && .venv/bin/python -m alembic upgrade head

test-unit:
	cd backend && .venv/bin/python -m pytest -q -m "not integration"

test-int:
	cd backend && .venv/bin/python -m pytest -q -m integration tests/integration/

lint:
	cd backend && .venv/bin/python -m ruff check app alembic/env.py tests

fmt:
	cd backend && .venv/bin/python -m ruff format app alembic/env.py tests

typecheck:
	cd backend && .venv/bin/python -m mypy app

reset-db:
	docker compose down -v
	docker compose up -d db
	@sleep 5
	$(MAKE) migrate

seed:
	cd backend && .venv/bin/python scripts/seed_entities.py
