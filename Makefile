PYTHONPATH_VAR=$(shell pwd)/qa-runner/backend
VENV_BIN=venv/bin

.PHONY: test install build-qa up-qa down-qa

install:
	$(VENV_BIN)/pip install fastapi uvicorn[standard] pyyaml pydantic psycopg2-binary requests streamlit docker pytest pytest-cov pytest-mock pandas watchdog

test:
	export PYTHONPATH=$(PYTHONPATH_VAR) && \
	$(VENV_BIN)/pytest --rootdir=. -v qa-runner/tests/ --cov=runners --cov-report=term-missing

build-qa:
	docker compose -f qa-runner/docker-compose.qa.yml build

up-qa:
	docker compose -f qa-runner/docker-compose.qa.yml up -d

down-qa:
	docker compose -f qa-runner/docker-compose.qa.yml down
