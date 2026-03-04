#!/bin/bash
# Unified test runner for GeoJSON Ingestion Service
#
# Usage:
#   ./run-tests.sh unit          # Run unit tests only (fast, no database needed)
#   ./run-tests.sh integration   # Run integration tests (requires Docker)
#   ./run-tests.sh all           # Run both unit and integration tests
#   ./run-tests.sh coverage      # Run unit tests with coverage report
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_section() {
    echo ""
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE} $1${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo ""
}

setup_venv() {
    # Activate virtual environment if it exists
    if [ -d "venv" ]; then
        source venv/bin/activate
        log_info "Virtual environment activated"
    fi
    
    # Check if dependencies are installed
    if ! python3 -c "import pytest" 2>/dev/null; then
        log_info "Installing dependencies..."
        pip install -q -r requirements.txt
        pip install -q -r requirements-dev.txt
        log_info "Dependencies installed"
    fi
}

run_unit_tests() {
    log_section "Running Unit Tests"
    
    pytest tests/test_unit.py tests/test_rate_limiter.py tests/test_services.py \
        -v \
        --tb=short \
        --no-cov \
        "$@"
}

run_integration_tests() {
    log_section "Running Integration Tests"
    
    # Use the dedicated integration test runner
    ./run-integration-tests.sh "$@"
}

run_all_tests() {
    log_section "Running All Tests"
    
    local unit_exit=0
    local integration_exit=0
    
    # Run unit tests first
    log_info "Phase 1: Unit Tests"
    run_unit_tests --no-cov || unit_exit=$?
    
    # Run integration tests
    log_info "Phase 2: Integration Tests"
    run_integration_tests || integration_exit=$?
    
    # Report results
    echo ""
    log_section "Test Summary"
    
    if [ $unit_exit -eq 0 ]; then
        echo -e "${GREEN}Unit tests:        PASSED${NC}"
    else
        echo -e "${RED}Unit tests:        FAILED${NC}"
    fi
    
    if [ $integration_exit -eq 0 ]; then
        echo -e "${GREEN}Integration tests: PASSED${NC}"
    else
        echo -e "${RED}Integration tests: FAILED${NC}"
    fi
    
    # Return non-zero if any failed
    if [ $unit_exit -ne 0 ] || [ $integration_exit -ne 0 ]; then
        exit 1
    fi
}

run_with_coverage() {
    log_section "Running Tests with Coverage"
    
    local COMPOSE_FILE="docker-compose.test.yml"
    local DB_CONTAINER="geojson-test-db"
    local MAX_RETRIES=30
    local RETRY_INTERVAL=2
    
    # Function to wait for database
    wait_for_db() {
        log_info "Waiting for PostgreSQL/PostGIS to be ready..."
        local retries=0
        
        while [ $retries -lt $MAX_RETRIES ]; do
            if docker exec "$DB_CONTAINER" pg_isready -U postgres -d geojson_test >/dev/null 2>&1; then
                log_info "PostgreSQL is ready!"
                return 0
            fi
            
            retries=$((retries + 1))
            log_info "Waiting for database... ($retries/$MAX_RETRIES)"
            sleep $RETRY_INTERVAL
        done
        
        echo -e "${RED}[ERROR]${NC} PostgreSQL failed to become ready within timeout"
        return 1
    }
    
    # Clean up any previous containers
    log_info "Cleaning up test containers..."
    docker compose -f "$COMPOSE_FILE" down -v --remove-orphans 2>/dev/null || true
    
    # Start the test database
    log_info "Starting PostgreSQL/PostGIS container..."
    docker compose -f "$COMPOSE_FILE" up -d
    
    # Wait for database to be ready
    if ! wait_for_db; then
        echo -e "${RED}[ERROR]${NC} Database failed to start"
        docker compose -f "$COMPOSE_FILE" down -v --remove-orphans 2>/dev/null || true
        exit 1
    fi
    
    # Verify PostGIS (with retry since init scripts may still be running)
    log_info "Verifying PostGIS extension..."
    local postgis_retries=0
    local max_postgis_retries=10
    local result=""
    
    while [ $postgis_retries -lt $max_postgis_retries ]; do
        result=$(docker exec "$DB_CONTAINER" psql -U postgres -d geojson_test -tAc \
            "SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname = 'postgis');" 2>/dev/null || echo "")
        
        if [ "$result" = "t" ]; then
            break
        fi
        
        postgis_retries=$((postgis_retries + 1))
        log_info "Waiting for PostGIS extension... ($postgis_retries/$max_postgis_retries)"
        sleep 2
    done
    
    if [ "$result" != "t" ]; then
        echo -e "${RED}[ERROR]${NC} PostGIS extension not found after $max_postgis_retries attempts"
        docker compose -f "$COMPOSE_FILE" down -v --remove-orphans 2>/dev/null || true
        exit 1
    fi
    log_info "PostGIS extension is installed"
    
    # Set environment variables for integration tests
    export TEST_MODE=integration
    export TEST_DB_HOST=localhost
    export TEST_DB_PORT=5433
    export TEST_DB_NAME=geojson_test
    export TEST_DB_USER=postgres
    export TEST_DB_PASSWORD=postgres
    
    echo ""
    log_info "Database is ready, running tests with coverage..."
    echo ""
    
    local test_exit_code=0
    pytest tests/test_postgis_integration.py tests/test_unit.py tests/test_coverage_boost.py tests/test_services.py tests/test_rate_limiter.py \
        -v \
        --tb=short \
        --cov=app \
        --cov-report=html \
        --cov-report=term-missing \
        --cov-report=xml \
        --cov-fail-under=74 \
        "$@" || test_exit_code=$?
    
    # Cleanup
    log_info "Cleaning up test containers..."
    docker compose -f "$COMPOSE_FILE" down -v --remove-orphans 2>/dev/null || true
    
    if [ $test_exit_code -eq 0 ]; then
        log_info "Coverage report generated: htmlcov/index.html"
    fi
    
    exit $test_exit_code
}

show_usage() {
    echo "GeoJSON Ingestion Service - Test Runner"
    echo ""
    echo "Usage: $0 <command> [options]"
    echo ""
    echo "Commands:"
    echo "  unit          Run unit tests only (fast, no database needed)"
    echo "  integration   Run integration tests (requires Docker)"
    echo "  all           Run both unit and integration tests"
    echo "  coverage      Run unit tests with coverage report"
    echo ""
    echo "Options:"
    echo "  --keep        Keep test database running after integration tests"
    echo "  -k EXPR       Run only tests matching expression"
    echo "  -x            Stop on first failure"
    echo ""
    echo "Examples:"
    echo "  $0 unit                    # Quick unit tests"
    echo "  $0 integration --keep      # Integration tests, keep DB"
    echo "  $0 all                     # Full test suite"
    echo "  $0 coverage                # Unit tests with coverage"
    echo "  $0 unit -k 'health'        # Run tests matching 'health'"
    echo ""
}

# Main
setup_venv

case "${1:-}" in
    unit)
        shift
        run_unit_tests "$@"
        ;;
    integration)
        shift
        run_integration_tests "$@"
        ;;
    all)
        shift
        run_all_tests "$@"
        ;;
    coverage)
        shift
        run_with_coverage "$@"
        ;;
    -h|--help|help)
        show_usage
        ;;
    "")
        echo -e "${YELLOW}No command specified. Running unit tests by default.${NC}"
        echo ""
        run_unit_tests
        ;;
    *)
        echo -e "${RED}Unknown command: $1${NC}"
        echo ""
        show_usage
        exit 1
        ;;
esac
