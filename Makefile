GO ?= go
export GOPATH := $(CURDIR)/.cache/gopath
export GOCACHE := $(CURDIR)/.cache/gobuild
.PHONY: setup build lint test bench demo models scan
setup:
	python3 -m venv .venv
	.venv/bin/pip install --upgrade pip==26.2.2
	.venv/bin/pip install -e '.[dev]'
	npm --prefix apps/web ci
	$(GO) mod download
build:
	mkdir -p bin
	$(GO) build -o bin/pulse ./cmd/gateway
	npm --prefix apps/web run build
lint:
	test -z "$$($(GO) fmt ./...)"
	$(GO) vet ./...
	.venv/bin/ruff check worker scripts tests
	.venv/bin/ruff format --check worker scripts tests
	cd apps/web && npm run lint
test:
	$(GO) test -race -timeout 60s -count=1 -v ./...
	.venv/bin/python -m pytest -q
bench:
	.venv/bin/python scripts/bench.py
models:
	.venv/bin/python scripts/fetch_models.py
demo:
	docker compose up --build
scan:
	npm --prefix apps/web audit --audit-level=high
	$(GO) run golang.org/x/vuln/cmd/govulncheck@v1.9.0 ./...
