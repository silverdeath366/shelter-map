#!/bin/bash
# Integration test runner with PostgreSQL/PostGIS
# 
# Usage:
#   ./run-integration-tests.sh           # Run all integration tests
#   ./run-integration-tests.sh --keep    # Keep database running after tests
#   ./run-integration-tests.sh --clean   # Clean up containers only
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
COMPOSE_FILE="docker-compose.test.yml"
DB_CONTAINER="geojson-test-db"
MAX_RETRIES=30
RETRY_INTERVAL=2

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

cleanup() {
    log_info "Cleaning up test containers..."
    docker compose -f "$COMPOSE_FILE" down -v --remove-orphans 2>/dev/null || true
}

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
    
    log_error "PostgreSQL failed to become ready within timeout"
    return 1
}

verify_postgis() {
    log_info "Verifying PostGIS extension..."
    
    local result
    result=$(docker exec "$DB_CONTAINER" psql -U postgres -d geojson_test -tAc \
        "SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname = 'postgis');" 2>/dev/null)
    
    if [ "$result" = "t" ]; then
        log_info "PostGIS extension is installed"
        return 0
    else
        log_error "PostGIS extension not found"
        return 1
    fi
}

verify_tables() {
    log_info "Verifying database tables..."
    
    local tables
    tables=$(docker exec "$DB_CONTAINER" psql -U postgres -d geojson_test -tAc \
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_name IN ('geo_features', 'api_keys', 'fines_ledger');" 2>/dev/null)
    
    # Need at least geo_features and api_keys; fines_ledger optional (Phase 5)
    if [ "$tables" -ge 2 ]; then
        log_info "Required tables exist (found $tables)"
        return 0
    else
        log_warn "Expected at least 2 tables (geo_features, api_keys), found $tables"
        return 1
    fi
}

run_tests() {
    log_info "Running integration tests..."
    
    # Activate virtual environment if exists
    if [ -d "venv" ]; then
        source venv/bin/activate
        log_info "Virtual environment activated"
    fi
    
    # Install dependencies if needed
    if ! python3 -c "import pytest" 2>/dev/null; then
        log_info "Installing test dependencies..."
        pip install -q -r requirements.txt
        pip install -q -r requirements-dev.txt
    fi
    
    # Run pytest with integration mode
    export TEST_MODE=integration
    export TEST_DB_HOST=localhost
    export TEST_DB_PORT=5433
    export TEST_DB_NAME=geojson_test
    export TEST_DB_USER=postgres
    export TEST_DB_PASSWORD=postgres
    
    # Run integration tests with verbose output (PostGIS + CityGuard Phase 5)
    pytest tests/test_postgis_integration.py tests/test_cityguard_integration.py \
        -v \
        --tb=short \
        --no-cov \
        -x \
        "$@"
}

# Parse arguments
KEEP_DB=false
CLEAN_ONLY=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --keep)
            KEEP_DB=true
            shift
            ;;
        --clean)
            CLEAN_ONLY=true
            shift
            ;;
        *)
            break
            ;;
    esac
done

# Handle clean only
if [ "$CLEAN_ONLY" = true ]; then
    cleanup
    log_info "Cleanup complete"
    exit 0
fi

# Main execution
main() {
    log_info "Starting integration test suite"
    echo ""
    
    # Clean up any previous containers
    cleanup
    
    # Start the test database
    log_info "Starting PostgreSQL/PostGIS container..."
    docker compose -f "$COMPOSE_FILE" up -d
    
    # Wait for database to be ready
    if ! wait_for_db; then
        log_error "Database failed to start"
        cleanup
        exit 1
    fi
    
    # Verify PostGIS
    if ! verify_postgis; then
        log_error "PostGIS verification failed"
        cleanup
        exit 1
    fi
    
    # Verify tables
    if ! verify_tables; then
        log_warn "Table verification had issues, tests may still work"
    fi
    
    echo ""
    log_info "Database is ready, running tests..."
    echo ""
    
    # Run the tests
    local test_exit_code=0
    run_tests "$@" || test_exit_code=$?
    
    echo ""
    
    # Cleanup unless --keep was specified
    if [ "$KEEP_DB" = false ]; then
        cleanup
    else
        log_info "Keeping database running (use --clean to stop)"
        log_info "Connect with: psql -h localhost -p 5433 -U postgres -d geojson_test"
    fi
    
    # Report results
    if [ $test_exit_code -eq 0 ]; then
        log_info "All integration tests passed!"
    else
        log_error "Some integration tests failed (exit code: $test_exit_code)"
    fi
    
    exit $test_exit_code
}

main "$@"
