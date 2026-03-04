#!/bin/bash

# Load Testing Script for GeoJSON Ingestion Microservice
# Uses Apache Bench (ab) or curl for load testing

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# Configuration
SERVICE_URL="${SERVICE_URL:-http://localhost:8000}"
API_KEY="${API_KEY:-}"
REQUESTS="${REQUESTS:-1000}"
CONCURRENCY="${CONCURRENCY:-10}"
TEST_TYPE="${TEST_TYPE:-health}"

echo -e "${GREEN}=== Load Testing Script ===${NC}"
echo "Service URL: $SERVICE_URL"
echo "Requests: $REQUESTS"
echo "Concurrency: $CONCURRENCY"
echo "Test Type: $TEST_TYPE"
echo ""

# Create test GeoJSON file
cat > /tmp/load-test-geojson.json << 'EOF'
{
  "type": "FeatureCollection",
  "features": [{
    "type": "Feature",
    "geometry": {
      "type": "Point",
      "coordinates": [-122.4194, 37.7749]
    },
    "properties": {
      "name": "Test Point",
      "load_test": true
    }
  }]
}
EOF

# Function to test health endpoint
test_health() {
    echo -e "${YELLOW}Testing Health Endpoint...${NC}"
    if command -v ab &> /dev/null; then
        ab -n $REQUESTS -c $CONCURRENCY "$SERVICE_URL/healthz"
    else
        echo "Apache Bench not found. Using curl..."
        for i in $(seq 1 $REQUESTS); do
            curl -s -o /dev/null -w "%{http_code}\n" "$SERVICE_URL/healthz" &
            if [ $((i % CONCURRENCY)) -eq 0 ]; then
                wait
            fi
        done
        wait
    fi
}

# Function to test ingestion endpoint
test_ingestion() {
    if [ -z "$API_KEY" ]; then
        echo -e "${RED}Error: API_KEY required for ingestion tests${NC}"
        exit 1
    fi
    
    echo -e "${YELLOW}Testing Ingestion Endpoint...${NC}"
    if command -v ab &> /dev/null; then
        ab -n $REQUESTS -c $CONCURRENCY \
          -H "X-API-Key: $API_KEY" \
          -H "Content-Type: application/json" \
          -p /tmp/load-test-geojson.json \
          -T "application/json" \
          "$SERVICE_URL/v1/ingest"
    else
        echo "Apache Bench not found. Using curl..."
        for i in $(seq 1 $REQUESTS); do
            curl -s -o /dev/null -w "%{http_code}\n" \
              -X POST \
              -H "X-API-Key: $API_KEY" \
              -H "Content-Type: application/json" \
              -d @/tmp/load-test-geojson.json \
              "$SERVICE_URL/v1/ingest" &
            if [ $((i % CONCURRENCY)) -eq 0 ]; then
                wait
            fi
        done
        wait
    fi
}

# Function to test metrics endpoint
test_metrics() {
    echo -e "${YELLOW}Testing Metrics Endpoint...${NC}"
    if command -v ab &> /dev/null; then
        ab -n $REQUESTS -c $CONCURRENCY "$SERVICE_URL/metrics"
    else
        echo "Apache Bench not found. Using curl..."
        for i in $(seq 1 $REQUESTS); do
            curl -s -o /dev/null -w "%{http_code}\n" "$SERVICE_URL/metrics" &
            if [ $((i % CONCURRENCY)) -eq 0 ]; then
                wait
            fi
        done
        wait
    fi
}

# Run test based on type
case $TEST_TYPE in
    health)
        test_health
        ;;
    ingestion)
        test_ingestion
        ;;
    metrics)
        test_metrics
        ;;
    all)
        test_health
        echo ""
        test_metrics
        echo ""
        test_ingestion
        ;;
    *)
        echo -e "${RED}Unknown test type: $TEST_TYPE${NC}"
        echo "Valid types: health, ingestion, metrics, all"
        exit 1
        ;;
esac

# Cleanup
rm -f /tmp/load-test-geojson.json

echo ""
echo -e "${GREEN}Load test completed!${NC}"

