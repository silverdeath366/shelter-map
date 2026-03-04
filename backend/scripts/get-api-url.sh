#!/usr/bin/env bash
# Print how to get the geojson-ingestion API URL for E2E / curl.
# Run from anywhere; requires kubectl only for cluster options.

echo "GeoJSON Ingestion API URL options:"
echo ""
echo "1) Port-forward (easiest if you have kubectl + cluster access)"
echo "   kubectl port-forward -n geojson-ingestion svc/geojson-ingestion 8091:8091"
echo "   Then use:  API_URL=http://localhost:8091"
echo ""

if command -v kubectl &>/dev/null; then
  echo "2) Ingress host (if ingress is enabled for geojson-ingestion)"
  HOST=$(kubectl get ingress -n geojson-ingestion -o jsonpath='{.items[0].spec.rules[0].host}' 2>/dev/null || true)
  if [ -n "$HOST" ]; then
    echo "   Ingress host: $HOST"
    echo "   Use:  API_URL=https://$HOST"
  else
    echo "   (No ingress found in geojson-ingestion namespace)"
  fi
  echo ""
  echo "3) LoadBalancer / NodePort (if used)"
  echo "   kubectl get svc -n geojson-ingestion"
else
  echo "2) Ingress: run  kubectl get ingress -n geojson-ingestion  and use the HOST"
  echo ""
fi

echo "4) Local dev"
echo "   uvicorn app.main:app --port 8091"
echo "   Then use:  API_URL=http://localhost:8091"
echo ""
echo "E2E test:  API_URL=<url> ./scripts/e2e-upload-presign-confirm.sh"
