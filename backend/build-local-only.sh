#!/bin/bash
# Build image locally only (skip ECR push for now)
# You can push manually later or use port-forward to test

set -e

echo "=== Building GeoJSON Ingestion Image Locally ==="
echo ""

# Build image
echo "Building Docker image..."
docker build -t geojson-ingestion:latest .

echo ""
echo "✓ Image built: geojson-ingestion:latest"
echo ""
echo "To test locally:"
echo "  docker run -p 8091:8091 geojson-ingestion:latest"
echo ""
echo "To push to ECR later (when Docker login works):"
echo "  1. Fix Docker login issue"
echo "  2. Tag: docker tag geojson-ingestion:latest <ECR_REGISTRY>/geojson-ingestion:latest"
echo "  3. Push: docker push <ECR_REGISTRY>/geojson-ingestion:latest"
echo ""
echo "Or use port-forward to test with local image in Kubernetes:"
echo "  kubectl port-forward svc/geojson-ingestion-service 8091:80"

