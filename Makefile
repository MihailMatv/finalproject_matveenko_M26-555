.PHONY: install run parser lint format build check

install:
	uv sync

run:
	uv run valutatrade

parser:
	uv run valutatrade-parser --once

lint:
	uv run ruff check .

format:
	uv run ruff format .

build:
	uv build

check: lint build
	uvx twine check dist/*
