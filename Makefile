.PHONY: help bootstrap lint typecheck test db-up db-down db-migrate dev-api r0-demo r0-review reset-synthetic-data

SYNTHETIC_URL := postgresql://panestria_synthetic:placeholder-not-a-secret@127.0.0.1:55432/panestria_synthetic
COMPOSE := docker compose -f compose.yaml -p panestria-s3
KNOWN := help bootstrap lint typecheck test db-up db-down db-migrate dev-api r0-demo r0-review reset-synthetic-data

ifneq ($(filter-out $(KNOWN),$(MAKECMDGOALS)),)
$(error unsupported_target)
endif

help:
	@printf '%s\n' $(KNOWN)

bootstrap:
	uv lock --check
	uv sync --frozen --group dev

lint:
	uv run --frozen ruff check src tests

typecheck:
	uv run --frozen mypy

test:
	uv run --frozen pytest -m "not live"

db-up:
	$(COMPOSE) up -d --wait

db-down:
	$(COMPOSE) down

db-migrate:
	@PANESTRIA_DATABASE_URL="$(or $(PANESTRIA_DATABASE_URL),$(SYNTHETIC_URL))" \
	uv run --frozen alembic -c migrations/alembic.ini upgrade head

dev-api:
	@PANESTRIA_DATABASE_URL="$(or $(PANESTRIA_DATABASE_URL),$(SYNTHETIC_URL))" \
	PANESTRIA_TOKEN="$${PANESTRIA_TOKEN:-synthetic-loopback-token}" \
	PANESTRIA_BIND_HOST="$${PANESTRIA_BIND_HOST:-127.0.0.1}" \
	PANESTRIA_BIND_PORT="$${PANESTRIA_BIND_PORT:-8765}" \
	uv run --frozen python -m panestria.api.serve

r0-demo r0-review:
	@PANESTRIA_DATABASE_URL="$(or $(PANESTRIA_DATABASE_URL),$(SYNTHETIC_URL))" \
	PANESTRIA_TOKEN="$${PANESTRIA_TOKEN:-synthetic-loopback-token}" \
	PANESTRIA_BIND_HOST="$${PANESTRIA_BIND_HOST:-127.0.0.1}" \
	PANESTRIA_BIND_PORT="$${PANESTRIA_BIND_PORT:-8765}" \
	uv run --frozen python -m panestria.demo $(if $(filter r0-review,$@),--review,)

reset-synthetic-data:
	$(COMPOSE) down -v
