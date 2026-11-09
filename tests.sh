#!/usr/bin/env bash
# Shared local and GitHub Actions checks. Live-device tests run separately.
set -euo pipefail

cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

PYTHON_VERSIONS=(3.11 3.12 3.13 3.14 3.15)
CHECK_PYTHON=3.13
# Include Emscripten to cover the additional dependency branch in uv.lock.
AUDIT_PLATFORMS=(linux macos windows wasm32-pyodide2025)

usage() {
    printf 'Usage: %s [all|checks|audit|test PYTHON_VERSION|--help]\n' "$0"
    printf '  all (default): checks, full lock-file audit, and Python 3.11–3.15 tests\n'
    printf '  checks: Ruff, mypy, Bandit, and installed-environment pip-audit on Python 3.13\n'
    printf '  audit: uv audit --frozen across the Python and platform matrices\n'
    printf '  test PYTHON_VERSION: non-live pytest; 98%% coverage gate on Python 3.13\n'
}

validate_python() {
    local supported
    for supported in "${PYTHON_VERSIONS[@]}"; do
        if [[ "$1" == "$supported" ]]; then
            return 0
        fi
    done
    printf 'Unsupported test Python version: %s\n' "$1" >&2
    return 2
}

run_checks() {
    uv sync --frozen --python "$CHECK_PYTHON"
    printf '\nRunning Ruff format check...\n'
    uv run --frozen --python "$CHECK_PYTHON" ruff format --check .
    printf '\nRunning Ruff linter...\n'
    uv run --frozen --python "$CHECK_PYTHON" ruff check .
    printf '\nRunning mypy...\n'
    uv run --frozen --python "$CHECK_PYTHON" mypy src tests
    printf '\nRunning Bandit security scan...\n'
    uv run --frozen --python "$CHECK_PYTHON" bandit -r src/
    printf '\nAuditing the installed environment with pip-audit...\n'
    uv run --frozen --python "$CHECK_PYTHON" pip-audit
}

audit_lock() {
    local version platform
    for version in "${PYTHON_VERSIONS[@]}"; do
        for platform in "${AUDIT_PLATFORMS[@]}"; do
            printf '\nAuditing uv.lock: Python %s, %s...\n' "$version" "$platform"
            uv audit --frozen --python-version "$version" --python-platform "$platform"
        done
    done
}

run_tests() {
    local version="$1"
    local pytest_args=(-v)
    if [[ "$version" == "$CHECK_PYTHON" ]]; then
        pytest_args+=(--cov=netmiko_mcp --cov-report=term-missing --cov-fail-under=98)
    fi
    printf '\nRunning non-live tests: Python %s...\n' "$version"
    uv run --frozen --isolated --python "$version" pytest "${pytest_args[@]}"
}

mode="${1:-all}"
case "$mode" in
    --help|-h)
        usage
        exit 0
        ;;
    all|checks|audit)
        if [[ "$#" -gt 1 ]]; then
            usage >&2
            exit 2
        fi
        ;;
    test)
        if [[ "$#" -ne 2 ]]; then
            usage >&2
            exit 2
        fi
        validate_python "$2"
        ;;
    *)
        usage >&2
        exit 2
        ;;
esac

# An inherited live-test flag must not turn local/CI checks into device operations.
unset RUN_LIVE_TESTS
uv lock --check

case "$mode" in
    all)
        run_checks
        audit_lock
        for version in "${PYTHON_VERSIONS[@]}"; do
            run_tests "$version"
        done
        ;;
    checks) run_checks ;;
    audit) audit_lock ;;
    test) run_tests "$2" ;;
esac
