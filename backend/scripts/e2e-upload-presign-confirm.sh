#!/usr/bin/env bash
# E2E: presign → upload to S3 → confirm. Run against a live API (local or in-cluster).
#
# Usage:
#   API_URL=http://localhost:8091 ./scripts/e2e-upload-presign-confirm.sh
#   API_URL=https://your-host ./scripts/e2e-upload-presign-confirm.sh [path/to/small.jpg]
#
# Don't know your API URL? Options:
#   A) Port-forward (no public URL needed):
#        kubectl port-forward -n geojson-ingestion svc/geojson-ingestion 8091:8091
#        Then: API_URL=http://localhost:8091 ./scripts/e2e-upload-presign-confirm.sh
#   B) Ingress host (if ingress is enabled):
#        kubectl get ingress -n geojson-ingestion -o jsonpath='{.items[0].spec.rules[0].host}'
#        Use https://<that-host> as API_URL
#   C) Local run: uvicorn app.main:app --port 8091
#        Then: API_URL=http://localhost:8091 ./scripts/e2e-upload-presign-confirm.sh
#
set -e
API_URL="${API_URL:-http://localhost:8091}"
IMAGE_FILE="${1:-}"

if [ "$API_URL" = "http://localhost:8091" ]; then
  echo "Using API_URL=http://localhost:8091 (set API_URL if your API is elsewhere)"
  echo "  Tip: kubectl port-forward -n geojson-ingestion svc/geojson-ingestion 8091:8091"
  echo ""
fi

# Create a minimal 1x1 JPEG if no file given (hex for a tiny valid JPEG)
create_minimal_jpeg() {
  printf '\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c\x1c $.\x27 ,#\x1c\x1c(7),01444\x1f\'9=82<.7\xff\xd9'
}

echo "=== 1. Presign ==="
RESP=$(curl -s -X POST "${API_URL}/v1/uploads/presign" \
  -H "Content-Type: application/json" \
  -d '{"content_type":"image/jpeg","file_size":1024}')
echo "$RESP" | head -c 500
echo ""

UPLOAD_URL=$(echo "$RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('uploadUrl',''))")
OBJECT_KEY=$(echo "$RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('objectKey',''))")

if [ -z "$UPLOAD_URL" ] || [ -z "$OBJECT_KEY" ]; then
  echo "Presign failed or missing uploadUrl/objectKey"
  exit 1
fi
echo "objectKey=$OBJECT_KEY"

echo ""
echo "=== 2. Upload to S3 (PUT) ==="
if [ -n "$IMAGE_FILE" ] && [ -f "$IMAGE_FILE" ]; then
  SIZE=$(stat -c%s "$IMAGE_FILE" 2>/dev/null || stat -f%z "$IMAGE_FILE" 2>/dev/null)
  curl -s -w "\nHTTP %{http_code}\n" -X PUT -T "$IMAGE_FILE" -H "Content-Type: image/jpeg" "$UPLOAD_URL"
else
  create_minimal_jpeg > /tmp/e2e-minimal.jpg
  SIZE=$(stat -c%s /tmp/e2e-minimal.jpg 2>/dev/null || stat -f%z /tmp/e2e-minimal.jpg 2>/dev/null)
  curl -s -w "\nHTTP %{http_code}\n" -X PUT -T /tmp/e2e-minimal.jpg -H "Content-Type: image/jpeg" "$UPLOAD_URL"
fi
echo ""

echo "=== 3. Confirm ==="
CONFIRM=$(curl -s -w "\nHTTP %{http_code}\n" -X POST "${API_URL}/v1/uploads/confirm" \
  -H "Content-Type: application/json" \
  -d "{\"s3_key\":\"$OBJECT_KEY\",\"content_type\":\"image/jpeg\",\"size_bytes\":$SIZE}")
echo "$CONFIRM"
if echo "$CONFIRM" | grep -q '"ok":\s*true'; then
  echo ""
  echo "=== E2E OK: presign → upload → confirm succeeded ==="
else
  echo "Confirm failed or unexpected response"
  exit 1
fi
