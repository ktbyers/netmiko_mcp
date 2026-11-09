#!/usr/bin/env bash
# Local equivalents of the explicit GitHub Actions checks. Live tests run separately.
set -euo pipefail

cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

PYTHON_VERSIONS=(3.11 3.12 3.13 3.14 3.15)
CHECK_PYTHON=3.13
# Include Emscripten to cover the additional dependency branch in uv.lock.
AUDIT_PLATFORMS=(linux macos windows wasm32-pyodide2025)

usage() {
    printf 'Usage: %s [all|checks|audit [PYTHON_VERSION PLATFORM]|test PYTHON_VERSION|--help]\n' "$0"
    printf '  all (default): checks, full lock-file audit, and Python 3.11–3.15 tests\n'
    printf '  checks: Ruff, mypy, and Bandit on Python 3.13\n'
    printf '  audit: full audit matrix, or one Python/platform combination when specified\n'
    printf '  test PYTHON_VERSION: non-live pytest; 98%% coverage gate on Python 3.13\n'
}

validate_python() {
    local supported
    for supported in "${PYTHON_VERSIONS[@]}"; do
        if [[ "$1" == "$supported" ]]; then
            return 0
        fi
    done
    printf 'Unsupported Python version: %s\n' "$1" >&2
    return 2
}

validate_platform() {
    local supported
    for supported in "${AUDIT_PLATFORMS[@]}"; do
        if [[ "$1" == "$supported" ]]; then
            return 0
        fi
    done
    printf 'Unsupported audit platform: %s\n' "$1" >&2
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
}

audit_target() {
    printf '\nAuditing uv.lock: Python %s, %s...\n' "$1" "$2"
    uv audit --frozen --python-version "$1" --python-platform "$2"
}

audit_lock() {
    local version platform
    for version in "${PYTHON_VERSIONS[@]}"; do
        for platform in "${AUDIT_PLATFORMS[@]}"; do
            audit_target "$version" "$platform"
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
    all|checks)
        if [[ "$#" -gt 1 ]]; then
            usage >&2
            exit 2
        fi
        ;;
    audit)
        if [[ "$#" -eq 3 ]]; then
            validate_python "$2"
            validate_platform "$3"
        elif [[ "$#" -ne 1 ]]; then
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
    audit)
        if [[ "$#" -eq 3 ]]; then
            audit_target "$2" "$3"
        else
            audit_lock
        fi
        ;;
    test) run_tests "$2" ;;
esac
