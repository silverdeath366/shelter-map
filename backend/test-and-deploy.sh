#!/bin/bash
set -euo pipefail

# Complete Test and Deployment Script for GeoJSON Ingestion Service
# This script handles prerequisites, deployment, and testing

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
AWS_REGION="${AWS_REGION:-us-east-2}"
CLUSTER_NAME="${CLUSTER_NAME:-silver-saas-cluster}"
ECR_REPO_NAME="geojson-ingestion"
SECRET_NAME="geojson-db-credentials"

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."
    
    local missing=0
    
    for cmd in aws kubectl docker; do
        if ! command -v $cmd &> /dev/null; then
            log_error "$cmd is not installed"
            missing=1
        fi
    done
    
    if [ $missing -eq 1 ]; then
        log_error "Please install missing prerequisites"
        exit 1
    fi
    
    # Check AWS credentials
    if ! aws sts get-caller-identity &> /dev/null; then
        log_error "AWS credentials not configured. Run 'aws configure'"
        exit 1
    fi
    
    # Get AWS account ID
    export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
    export ECR_REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
    export IMAGE_NAME="${ECR_REGISTRY}/${ECR_REPO_NAME}"
    
    log_success "All prerequisites met"
    log_info "AWS Account ID: $AWS_ACCOUNT_ID"
    log_info "ECR Registry: $ECR_REGISTRY"
}

# Configure kubectl
configure_kubectl() {
    log_info "Configuring kubectl for EKS cluster..."
    
    if aws eks update-kubeconfig --name "$CLUSTER_NAME" --region "$AWS_REGION" &> /dev/null; then
        log_success "kubectl configured for cluster: $CLUSTER_NAME"
    else
        log_error "Failed to configure kubectl. Check cluster name: $CLUSTER_NAME"
        exit 1
    fi
    
    # Verify access
    if kubectl get nodes &> /dev/null; then
        log_success "Connected to EKS cluster"
        kubectl get nodes --no-headers | wc -l | xargs -I {} log_info "Found {} node(s)"
    else
        log_error "Cannot access EKS cluster"
        exit 1
    fi
}

# Check/create ECR repository
setup_ecr() {
    log_info "Checking ECR repository..."
    
    if aws ecr describe-repositories --repository-names "$ECR_REPO_NAME" --region "$AWS_REGION" &> /dev/null; then
        log_success "ECR repository exists: $ECR_REPO_NAME"
    else
        log_warn "ECR repository not found. Creating..."
        aws ecr create-repository \
            --repository-name "$ECR_REPO_NAME" \
            --region "$AWS_REGION" \
            --image-scanning-configuration scanOnPush=true \
            --encryption-configuration encryptionType=AES256
        
        log_success "ECR repository created: $ECR_REPO_NAME"
    fi
}

# Check/create AWS Secrets Manager secret
setup_secrets() {
    log_info "Checking AWS Secrets Manager secret..."
    
    if aws secretsmanager describe-secret --secret-id "$SECRET_NAME" --region "$AWS_REGION" &> /dev/null; then
        log_success "Secret exists: $SECRET_NAME"
        log_warn "If you need to update the secret, run:"
        echo "  aws secretsmanager update-secret --secret-id $SECRET_NAME --secret-string file://secret.json"
    else
        log_warn "Secret not found: $SECRET_NAME"
        log_info "Creating secret template..."
        
        # Create a template secret file
        cat > /tmp/secret-template.json <<EOF
{
  "DB_HOST": "your-rds-endpoint.rds.amazonaws.com",
  "DB_PORT": "5432",
  "DB_NAME": "geojson_db",
  "DB_USER": "postgres",
  "DB_PASSWORD": "your-password-here",
  "DB_SSLMODE": "prefer"
}
EOF
        
        log_error "Please create the secret manually:"
        echo "  1. Edit /tmp/secret-template.json with your RDS credentials"
        echo "  2. Run: aws secretsmanager create-secret \\"
        echo "       --name $SECRET_NAME \\"
        echo "       --secret-string file:///tmp/secret-template.json \\"
        echo "       --region $AWS_REGION"
        echo ""
        read -p "Press Enter after creating the secret, or Ctrl+C to exit..."
    fi
}

# Build and push Docker image
build_and_push() {
    log_info "Building Docker image..."
    
    if [ ! -f Dockerfile ]; then
        log_error "Dockerfile not found in current directory"
        exit 1
    fi
    
    # Build image
    log_info "Building image: geojson-ingestion:latest"
    docker build -t geojson-ingestion:latest .
    
    # Login to ECR
    log_info "Logging into ECR..."
    aws ecr get-login-password --region "$AWS_REGION" | \
        docker login --username AWS --password-stdin "$ECR_REGISTRY"
    
    # Tag and push
    log_info "Tagging image..."
    docker tag geojson-ingestion:latest "${IMAGE_NAME}:latest"
    
    log_info "Pushing image to ECR..."
    docker push "${IMAGE_NAME}:latest"
    
    log_success "Image pushed: ${IMAGE_NAME}:latest"
}

# Update deployment with image
update_deployment_image() {
    log_info "Updating deployment with ECR image..."
    
    cd k8s
    
    # Update image in deployment.yaml
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS
        sed -i '' "s|\${ECR_REGISTRY}|${ECR_REGISTRY}|g" deployment.yaml
    else
        # Linux
        sed -i "s|\${ECR_REGISTRY}|${ECR_REGISTRY}|g" deployment.yaml
    fi
    
    log_success "Deployment image updated"
}

# Deploy to Kubernetes
deploy_kubernetes() {
    log_info "Deploying to Kubernetes..."
    
    cd k8s
    
    # Deploy in order
    log_info "Applying SecretProviderClass..."
    kubectl apply -f 01-secretproviderclass.yaml
    
    log_info "Applying ServiceAccount..."
    kubectl apply -f service-account.yaml
    
    log_info "Applying NetworkPolicy..."
    kubectl apply -f network-policy.yaml
    
    log_info "Applying Deployment..."
    kubectl apply -f deployment.yaml
    
    log_info "Applying Service and Ingress..."
    kubectl apply -f service.yaml
    
    log_info "Applying HPA..."
    kubectl apply -f hpa.yaml
    
    log_success "All Kubernetes resources applied"
    
    cd ..
}

# Wait for deployment
wait_for_deployment() {
    log_info "Waiting for deployment to be ready..."
    
    if kubectl wait --for=condition=available --timeout=300s deployment/geojson-ingestion &> /dev/null; then
        log_success "Deployment is ready!"
    else
        log_warn "Deployment may still be starting. Check status with: kubectl get pods -l app=geojson-ingestion"
    fi
    
    # Show pod status
    log_info "Pod status:"
    kubectl get pods -l app=geojson-ingestion
    
    # Wait a bit more for pods to be fully ready
    sleep 10
}

# Get service URL
get_service_url() {
    log_info "Getting service URL..."
    
    # Try to get ALB URL
    ALB_URL=$(kubectl get ingress geojson-ingestion-ingress -o jsonpath='{.status.loadBalancer.ingress[0].hostname}' 2>/dev/null || echo "")
    
    if [ -n "$ALB_URL" ]; then
        log_success "ALB URL: http://$ALB_URL"
        export SERVICE_URL="http://$ALB_URL"
    else
        log_warn "ALB not ready yet. Setting up port-forward for testing..."
        export SERVICE_URL="http://localhost:8091"
        
        # Start port-forward in background
        log_info "Starting port-forward (Ctrl+C to stop)..."
        kubectl port-forward svc/geojson-ingestion-service 8091:80 &
        PORT_FORWARD_PID=$!
        sleep 5
        
        log_info "Port-forward running (PID: $PORT_FORWARD_PID)"
        log_info "Service accessible at: $SERVICE_URL"
    fi
}

# Test the service
test_service() {
    log_info "Testing GeoJSON Ingestion Service..."
    
    if [ -z "${SERVICE_URL:-}" ]; then
        get_service_url
    fi
    
    # Test health endpoint
    log_info "Testing health endpoint..."
    if curl -f -s "${SERVICE_URL}/healthz" > /dev/null; then
        log_success "Health check passed!"
        curl -s "${SERVICE_URL}/healthz" | python3 -m json.tool 2>/dev/null || curl -s "${SERVICE_URL}/healthz"
        echo ""
    else
        log_error "Health check failed"
        log_info "Checking pod logs..."
        kubectl logs -l app=geojson-ingestion --tail=20
        return 1
    fi
    
    # Test API docs
    log_info "Testing API documentation endpoint..."
    if curl -f -s "${SERVICE_URL}/v1/docs" > /dev/null; then
        log_success "API docs accessible at: ${SERVICE_URL}/v1/docs"
    else
        log_warn "API docs endpoint not accessible"
    fi
    
    # Test metrics endpoint
    log_info "Testing metrics endpoint..."
    if curl -f -s "${SERVICE_URL}/metrics" > /dev/null; then
        log_success "Metrics endpoint accessible at: ${SERVICE_URL}/metrics"
    else
        log_warn "Metrics endpoint not accessible"
    fi
    
    # Test sample data ingestion if available
    if [ -f tests/sample-data/sample-point.geojson ]; then
        log_info "Testing GeoJSON ingestion with sample data..."
        
        RESPONSE=$(curl -s -X POST "${SERVICE_URL}/v1/ingest" \
            -H "Content-Type: application/json" \
            -d @tests/sample-data/sample-point.geojson)
        
        if echo "$RESPONSE" | grep -q "success\|created\|inserted" || [ $? -eq 0 ]; then
            log_success "Sample data ingestion test completed"
            echo "$RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$RESPONSE"
        else
            log_warn "Ingestion test may have failed. Response:"
            echo "$RESPONSE"
        fi
    else
        log_warn "Sample data not found. Skipping ingestion test."
    fi
}

# Show status
show_status() {
    log_info "=== Deployment Status ==="
    echo ""
    
    echo "📊 Pods:"
    kubectl get pods -l app=geojson-ingestion
    echo ""
    
    echo "🌐 Service:"
    kubectl get svc geojson-ingestion-service
    echo ""
    
    echo "🔀 Ingress:"
    kubectl get ingress geojson-ingestion-ingress
    echo ""
    
    echo "📈 HPA:"
    kubectl get hpa geojson-ingestion-hpa
    echo ""
    
    if [ -n "${SERVICE_URL:-}" ]; then
        echo "🔗 Service URL: $SERVICE_URL"
        echo "   Health: ${SERVICE_URL}/healthz"
        echo "   API Docs: ${SERVICE_URL}/v1/docs"
        echo "   Metrics: ${SERVICE_URL}/metrics"
    fi
    echo ""
}

# Main execution
main() {
    log_info "=== GeoJSON Ingestion Service - Test and Deploy ==="
    echo ""
    
    check_prerequisites
    configure_kubectl
    setup_ecr
    setup_secrets
    build_and_push
    update_deployment_image
    deploy_kubernetes
    wait_for_deployment
    get_service_url
    test_service
    show_status
    
    log_success "🎉 Deployment and testing complete!"
    echo ""
    log_info "Next steps:"
    echo "  - View logs: kubectl logs -l app=geojson-ingestion -f"
    echo "  - Check metrics: curl ${SERVICE_URL}/metrics"
    echo "  - Access API docs: ${SERVICE_URL}/v1/docs"
    echo "  - Test ingestion: curl -X POST ${SERVICE_URL}/v1/ingest -H 'Content-Type: application/json' -d @tests/sample-data/sample-point.geojson"
    
    if [ -n "${PORT_FORWARD_PID:-}" ]; then
        echo ""
        log_warn "Port-forward is running (PID: $PORT_FORWARD_PID)"
        log_info "To stop port-forward: kill $PORT_FORWARD_PID"
    fi
}

# Run main function
main "$@"

