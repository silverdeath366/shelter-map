#!/bin/bash
# Complete script to build and push Docker image to ECR

set -e

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}=== Building and Pushing GeoJSON Ingestion Image ===${NC}"

# Configuration
AWS_REGION="${AWS_REGION:-us-east-2}"
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
IMAGE_NAME="${ECR_REGISTRY}/geojson-ingestion"
IMAGE_TAG="latest"

echo "AWS Region: $AWS_REGION"
echo "Account ID: $AWS_ACCOUNT_ID"
echo "ECR Registry: $ECR_REGISTRY"
echo "Image: ${IMAGE_NAME}:${IMAGE_TAG}"
echo ""

# Check Docker
if ! docker ps &>/dev/null; then
    echo -e "${RED}Error: Docker daemon is not running${NC}"
    echo "Start Docker and try again"
    exit 1
fi

# Check/create ECR repository
echo -e "${BLUE}[1/4]${NC} Checking ECR repository..."
if aws ecr describe-repositories --repository-names geojson-ingestion --region $AWS_REGION &>/dev/null; then
    echo -e "${GREEN}✓ Repository exists${NC}"
else
    echo "Creating repository..."
    aws ecr create-repository \
        --repository-name geojson-ingestion \
        --region $AWS_REGION \
        --image-scanning-configuration scanOnPush=true \
        --encryption-configuration encryptionType=AES256
    echo -e "${GREEN}✓ Repository created${NC}"
fi

# Login to ECR
echo -e "${BLUE}[2/4]${NC} Logging into ECR..."
ECR_PASSWORD=$(aws ecr get-login-password --region $AWS_REGION)
echo "$ECR_PASSWORD" | docker login --username AWS --password-stdin $ECR_REGISTRY
echo -e "${GREEN}✓ Logged into ECR${NC}"

# Build image
echo -e "${BLUE}[3/4]${NC} Building Docker image..."
docker build -t geojson-ingestion:latest .
echo -e "${GREEN}✓ Image built${NC}"

# Tag and push
echo -e "${BLUE}[4/4]${NC} Tagging and pushing image..."
docker tag geojson-ingestion:latest ${IMAGE_NAME}:${IMAGE_TAG}
docker push ${IMAGE_NAME}:${IMAGE_TAG}
echo -e "${GREEN}✓ Image pushed: ${IMAGE_NAME}:${IMAGE_TAG}${NC}"

echo ""
echo -e "${GREEN}=== Complete! ===${NC}"
echo "Image is ready: ${IMAGE_NAME}:${IMAGE_TAG}"
echo ""
echo "Next steps:"
echo "1. Update deployment.yaml with image: ${IMAGE_NAME}:${IMAGE_TAG}"
echo "2. Deploy to Kubernetes: cd k8s && kubectl apply -f ."

