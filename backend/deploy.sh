#!/bin/bash
set -euo pipefail

# Production Deployment Script for GeoJSON Ingestion Microservice
# This script handles the complete deployment process

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
AWS_REGION="${AWS_REGION:-us-east-2}"
CLUSTER_NAME="${CLUSTER_NAME:-silver-saas-cluster}"
PROJECT_NAME="${PROJECT_NAME:-silver-saas-geojson-ingestion}"
ECR_REGISTRY="${AWS_ACCOUNT_ID:?set AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
IMAGE_NAME="${ECR_REGISTRY}/${PROJECT_NAME}"
IMAGE_TAG="${IMAGE_TAG:-latest}"

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_prerequisites() {
    log_info "Checking prerequisites..."
    
    local missing=0
    
    for cmd in aws terraform kubectl docker; do
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
    
    log_info "All prerequisites met"
}

deploy_infrastructure() {
    log_info "Deploying infrastructure with Terraform..."
    
    cd terraform
    
    # Check if terraform.tfvars exists
    if [ ! -f terraform.tfvars ]; then
        log_warn "terraform.tfvars not found. Creating from example..."
        if [ -f terraform.tfvars.example ]; then
            cp terraform.tfvars.example terraform.tfvars
            log_error "Please edit terraform.tfvars and set db_password before continuing"
            exit 1
        else
            log_error "terraform.tfvars.example not found"
            exit 1
        fi
    fi
    
    # Initialize Terraform
    terraform init
    
    # Plan
    log_info "Running terraform plan..."
    terraform plan -out=tfplan
    
    # Apply
    log_info "Applying Terraform configuration..."
    terraform apply tfplan
    
    # Get outputs
    log_info "Getting Terraform outputs..."
    export RDS_ENDPOINT=$(terraform output -raw rds_host)
    export RDS_PORT=$(terraform output -raw rds_port)
    export SERVICE_ACCOUNT_ROLE_ARN=$(terraform output -raw service_account_role_arn)
    export ECR_REPO_URL=$(terraform output -raw ecr_repository_url)
    
    log_info "Infrastructure deployed successfully"
    log_info "RDS Endpoint: $RDS_ENDPOINT"
    log_info "Service Account Role: $SERVICE_ACCOUNT_ROLE_ARN"
    
    cd ..
}

configure_kubectl() {
    log_info "Configuring kubectl..."
    
    aws eks update-kubeconfig --name "$CLUSTER_NAME" --region "$AWS_REGION"
    
    # Verify access
    if kubectl get nodes &> /dev/null; then
        log_info "kubectl configured successfully"
    else
        log_error "Failed to access EKS cluster"
        exit 1
    fi
}

setup_database() {
    log_info "Setting up database..."
    
    # Get RDS endpoint from Terraform
    if [ -z "${RDS_ENDPOINT:-}" ]; then
        cd terraform
        export RDS_ENDPOINT=$(terraform output -raw rds_host)
        export RDS_PORT=$(terraform output -raw rds_port)
        cd ..
    fi
    
    # Get password from terraform.tfvars
    DB_PASSWORD=$(grep -E '^\s*db_password\s*=' terraform/terraform.tfvars | cut -d'"' -f2)
    
    if [ -z "$DB_PASSWORD" ]; then
        log_error "Could not find db_password in terraform.tfvars"
        exit 1
    fi
    
    # Create Kubernetes secret
    log_info "Creating Kubernetes secret for database..."
    kubectl create secret generic geojson-db-secret \
        --from-literal=DB_HOST="$RDS_ENDPOINT" \
        --from-literal=DB_PORT="${RDS_PORT:-5432}" \
        --from-literal=DB_NAME=geojson_db \
        --from-literal=DB_USER=postgres \
        --from-literal=DB_PASSWORD="$DB_PASSWORD" \
        --from-literal=DB_SSLMODE=require \
        --dry-run=client -o yaml | kubectl apply -f -
    
    log_info "Database secret created"
    
    # Initialize PostGIS if not already done
    log_info "Initializing PostGIS extension..."
    if command -v psql &> /dev/null; then
        PGPASSWORD="$DB_PASSWORD" psql -h "$RDS_ENDPOINT" -U postgres -d geojson_db -c "CREATE EXTENSION IF NOT EXISTS postgis;" 2>/dev/null || {
            log_warn "Could not initialize PostGIS via psql. Will be initialized by application on first connection."
        }
    else
        log_warn "psql not available. PostGIS will be initialized by application on first connection."
    fi
}

build_and_push_image() {
    log_info "Building Docker image..."
    
    docker build -t "${PROJECT_NAME}:${IMAGE_TAG}" .
    
    log_info "Logging into ECR..."
    aws ecr get-login-password --region "$AWS_REGION" | \
        docker login --username AWS --password-stdin "$ECR_REGISTRY"
    
    log_info "Tagging image..."
    docker tag "${PROJECT_NAME}:${IMAGE_TAG}" "${IMAGE_NAME}:${IMAGE_TAG}"
    
    log_info "Pushing image to ECR..."
    docker push "${IMAGE_NAME}:${IMAGE_TAG}"
    
    log_info "Image pushed successfully: ${IMAGE_NAME}:${IMAGE_TAG}"
}

deploy_kubernetes() {
    log_info "Deploying to Kubernetes..."
    
    cd k8s
    
    # Update service account with IAM role
    if [ -n "${SERVICE_ACCOUNT_ROLE_ARN:-}" ]; then
        log_info "Updating service account with IAM role..."
        kubectl annotate serviceaccount geojson-ingestion-sa \
            eks.amazonaws.com/role-arn="$SERVICE_ACCOUNT_ROLE_ARN" \
            --overwrite -n default || true
    fi
    
    # Apply manifests in order
    log_info "Applying Kubernetes manifests..."
    kubectl apply -f service-account.yaml
    kubectl apply -f secret.yaml
    kubectl apply -f network-policy.yaml
    
    # Initialize database if init-db-job.yaml exists
    if [ -f init-db-job.yaml ]; then
        log_info "Running database initialization job..."
        kubectl apply -f init-db-job.yaml
        kubectl wait --for=condition=complete --timeout=300s job/init-db || log_warn "Database init job may still be running"
    fi
    
    kubectl apply -f deployment.yaml
    kubectl apply -f service.yaml
    kubectl apply -f hpa.yaml
    
    log_info "Waiting for deployment to be ready..."
    kubectl wait --for=condition=available --timeout=300s deployment/geojson-ingestion
    
    log_info "Deployment complete"
    cd ..
}

verify_deployment() {
    log_info "Verifying deployment..."
    
    # Check pods
    log_info "Checking pods..."
    kubectl get pods -l app=geojson-ingestion
    
    # Wait for pods to be ready
    log_info "Waiting for pods to be ready..."
    kubectl wait --for=condition=ready pod -l app=geojson-ingestion --timeout=300s
    
    # Check service
    log_info "Checking service..."
    kubectl get svc geojson-ingestion-service
    
    # Get service URL
    SERVICE_URL=$(kubectl get svc geojson-ingestion-service -o jsonpath='{.status.loadBalancer.ingress[0].hostname}' 2>/dev/null || echo "")
    
    if [ -z "$SERVICE_URL" ]; then
        log_warn "LoadBalancer not ready yet. Waiting..."
        sleep 30
        SERVICE_URL=$(kubectl get svc geojson-ingestion-service -o jsonpath='{.status.loadBalancer.ingress[0].hostname}' 2>/dev/null || echo "")
    fi
    
    if [ -n "$SERVICE_URL" ]; then
        log_info "Service URL: http://$SERVICE_URL"
        
        # Test health endpoint
        log_info "Testing health endpoint..."
        sleep 10
        if curl -f -s "http://$SERVICE_URL/healthz" > /dev/null; then
            log_info "Health check passed"
        else
            log_warn "Health check failed (service may still be starting)"
        fi
    else
        log_warn "LoadBalancer not ready. Check with: kubectl get svc geojson-ingestion-service"
    fi
    
    # Check logs
    log_info "Recent logs:"
    kubectl logs -l app=geojson-ingestion --tail=20
}

main() {
    log_info "Starting production deployment..."
    
    check_prerequisites
    
    # Check if infrastructure already exists
    cd terraform
    if terraform state list &> /dev/null; then
        log_info "Terraform state exists. Skipping infrastructure deployment."
        log_info "To redeploy infrastructure, run: cd terraform && terraform apply"
        export RDS_ENDPOINT=$(terraform output -raw rds_host 2>/dev/null || echo "")
        export RDS_PORT=$(terraform output -raw rds_port 2>/dev/null || echo "")
        export SERVICE_ACCOUNT_ROLE_ARN=$(terraform output -raw service_account_role_arn 2>/dev/null || echo "")
        cd ..
    else
        deploy_infrastructure
    fi
    
    configure_kubectl
    setup_database
    build_and_push_image
    deploy_kubernetes
    verify_deployment
    
    log_info "Deployment complete!"
    log_info "Service URL: http://$(kubectl get svc geojson-ingestion-service -o jsonpath='{.status.loadBalancer.ingress[0].hostname}' 2>/dev/null || echo 'pending')"
    log_info "View logs: kubectl logs -l app=geojson-ingestion -f"
    log_info "View pods: kubectl get pods -l app=geojson-ingestion"
}

main "$@"

