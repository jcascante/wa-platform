.PHONY: install dev test test-live lint typecheck fmt migrate migration up down package

install:
	pip install -e ".[dev]"

dev:
	uvicorn wa_platform.api.app:app --reload --port 8000 --app-dir src

test:
	pytest

# Hits the real Meta Graph API — needs META_TEST_* env vars, see tests/live/README.md.
# Never run by CI; `test` above excludes this directory via pyproject's testpaths.
test-live:
	pytest tests/live

lint:
	ruff check src tests

fmt:
	ruff format src tests
	ruff check --fix src tests

typecheck:
	mypy

migrate:
	alembic upgrade head

migration:
	alembic revision --autogenerate -m "$(m)"

up:
	docker compose up -d

down:
	docker compose down

# Builds the one Lambda deployment zip all three lambda_api/lambda_worker/lambda_migrate
# modules point at (infra/terraform/envs/*/terraform.tfvars `package_path`). linux/x86_64
# wheels are required since Lambda's runtime doesn't match an arbitrary dev machine (e.g.
# macOS/arm64). alembic.ini + migrations/ are bundled so the migrate Lambda can run
# `alembic upgrade head` in-place (see lambda_handlers/migrate_handler.py).
package:
	rm -rf build/package dist
	mkdir -p build/package dist
	pip install . --target build/package \
		--platform manylinux2014_x86_64 --python-version 3.12 --only-binary=:all:
	cp -r src/wa_platform build/package/
	cp -r migrations alembic.ini build/package/
	cd build/package && zip -rq ../../dist/wa-platform.zip .
