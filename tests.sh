#!/usr/bin/env bash
# Exit immediately if a command exits with a non-zero status
set -e

echo "Running ruff format check..."
uv run --frozen ruff format --check .

echo -e "\nRunning ruff linter..."
uv run --frozen ruff check .

echo -e "\nRunning mypy type checker..."
uv run --frozen mypy src tests

echo -e "\nRunning pytest..."
uv run --frozen pytest -v
