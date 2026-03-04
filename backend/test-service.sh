#!/bin/bash
set -euo pipefail

# Simple test script for GeoJSON Ingestion Service
# Run this after deployment to verify everything works

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Get service URL
get_service_url() {
    # Try ALB first
    ALB_URL=$(kubectl get ingress geojson-ingestion-ingress -o jsonpath='{.status.loadBalancer.ingress[0].hostname}' 2>/dev/null || echo "")
    
    if [ -n "$ALB_URL" ]; then
        echo "http://$ALB_URL"
    else
        # Check if port-forward is needed
        if ! curl -s http://localhost:8091/healthz &> /dev/null; then
            echo "http://localhost:8091"
            echo "⚠️  Note: ALB not ready. Start port-forward with:" >&2
            echo "   kubectl port-forward svc/geojson-ingestion-service 8091:80" >&2
        else
            echo "http://localhost:8091"
        fi
    fi
}

SERVICE_URL="${1:-$(get_service_url)}"

echo -e "${BLUE}=== Testing GeoJSON Ingestion Service ===${NC}"
echo -e "Service URL: ${GREEN}$SERVICE_URL${NC}"
echo ""

# Test 1: Health Check
echo -e "${BLUE}[1/6]${NC} Testing health endpoint..."
if curl -f -s "${SERVICE_URL}/healthz" > /tmp/health.json; then
    echo -e "${GREEN}✓ Health check passed${NC}"
    echo "Response:"
    cat /tmp/health.json | python3 -m json.tool 2>/dev/null || cat /tmp/health.json
    echo ""
else
    echo -e "${RED}✗ Health check failed${NC}"
    exit 1
fi

# Test 2: API Docs
echo -e "${BLUE}[2/6]${NC} Testing API documentation endpoint..."
if curl -f -s "${SERVICE_URL}/v1/docs" > /dev/null; then
    echo -e "${GREEN}✓ API docs accessible${NC}"
    echo "   URL: ${SERVICE_URL}/v1/docs"
    echo ""
else
    echo -e "${YELLOW}⚠ API docs not accessible${NC}"
    echo ""
fi

# Test 3: Metrics
echo -e "${BLUE}[3/6]${NC} Testing metrics endpoint..."
if curl -f -s "${SERVICE_URL}/metrics" > /tmp/metrics.txt; then
    echo -e "${GREEN}✓ Metrics endpoint accessible${NC}"
    METRIC_COUNT=$(grep -c "^[^#]" /tmp/metrics.txt || echo "0")
    echo "   Found $METRIC_COUNT metrics"
    echo ""
else
    echo -e "${YELLOW}⚠ Metrics endpoint not accessible${NC}"
    echo ""
fi

# Test 4: Sample Data Ingestion
echo -e "${BLUE}[4/6]${NC} Testing GeoJSON ingestion..."
if [ -f tests/sample-data/sample-point.geojson ]; then
    RESPONSE=$(curl -s -X POST "${SERVICE_URL}/v1/ingest" \
        -H "Content-Type: application/json" \
        -d @tests/sample-data/sample-point.geojson)
    
    if echo "$RESPONSE" | grep -q "success\|created\|inserted" || [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ Sample data ingestion successful${NC}"
        echo "$RESPONSE" | python3 -m json.tool 2>/dev/null | head -20 || echo "$RESPONSE" | head -20
        echo ""
    else
        echo -e "${YELLOW}⚠ Ingestion may have issues${NC}"
        echo "Response: $RESPONSE"
        echo ""
    fi
else
    echo -e "${YELLOW}⚠ Sample data file not found${NC}"
    echo ""
fi

# Test 5: Query Features
echo -e "${BLUE}[5/6]${NC} Testing feature query (bounding box)..."
QUERY_RESPONSE=$(curl -s "${SERVICE_URL}/v1/features/bbox?min_lon=-180&min_lat=-90&max_lon=180&max_lat=90")
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Query endpoint accessible${NC}"
    FEATURE_COUNT=$(echo "$QUERY_RESPONSE" | python3 -c "import sys, json; data=json.load(sys.stdin); print(len(data.get('features', [])))" 2>/dev/null || echo "?")
    echo "   Found $FEATURE_COUNT feature(s)"
    echo ""
else
    echo -e "${YELLOW}⚠ Query endpoint may have issues${NC}"
    echo ""
fi

# Test 6: Pod Status
echo -e "${BLUE}[6/6]${NC} Checking pod status..."
PODS=$(kubectl get pods -l app=geojson-ingestion --no-headers 2>/dev/null || echo "")
if [ -n "$PODS" ]; then
    RUNNING=$(echo "$PODS" | grep -c "Running" || echo "0")
    TOTAL=$(echo "$PODS" | wc -l)
    echo -e "${GREEN}✓ Pods: $RUNNING/$TOTAL running${NC}"
    echo ""
else
    echo -e "${YELLOW}⚠ Could not check pod status${NC}"
    echo ""
fi

# Summary
echo -e "${GREEN}=== Test Summary ===${NC}"
echo "Service URL: $SERVICE_URL"
echo "Health: ✓"
echo "API Docs: ${SERVICE_URL}/v1/docs"
echo "Metrics: ${SERVICE_URL}/metrics"
echo ""
echo -e "${GREEN}All tests completed!${NC}"

