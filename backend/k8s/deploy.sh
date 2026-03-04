#!/bin/bash

# GeoJSON Ingestion Service - Kubernetes Deployment Script
set -e

echo "🚀 Deploying GeoJSON Ingestion Service to Kubernetes"

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if kubectl is available
check_kubectl() {
    print_status "Checking kubectl availability..."
    if ! command -v kubectl &> /dev/null; then
        print_error "kubectl is not installed or not in PATH"
        exit 1
    fi
    
    if ! kubectl cluster-info &> /dev/null; then
        print_error "Cannot connect to Kubernetes cluster"
        exit 1
    fi
    
    print_success "Connected to Kubernetes cluster"
}

# Check prerequisites
check_prerequisites() {
    print_status "Checking prerequisites..."
    
    # Check if SecretProviderClass exists (CSI Secrets Store)
    if ! kubectl get secretproviderclass geojson-db-secrets-store-class &> /dev/null; then
        print_warning "SecretProviderClass not found. Make sure AWS Secrets Manager secret 'geojson-db-credentials' exists."
        print_status "Creating SecretProviderClass..."
        kubectl apply -f 01-secretproviderclass.yaml
    else
        print_success "SecretProviderClass exists"
    fi
}

# Deploy to Kubernetes
deploy() {
    print_status "Deploying to Kubernetes in correct order..."
    
    # 1. SecretProviderClass (for AWS Secrets Manager integration)
    print_status "Applying SecretProviderClass..."
    kubectl apply -f 01-secretproviderclass.yaml
    
    # 2. ServiceAccount (for IRSA)
    print_status "Applying ServiceAccount..."
    kubectl apply -f service-account.yaml
    
    # 3. NetworkPolicy (for network isolation)
    print_status "Applying NetworkPolicy..."
    kubectl apply -f network-policy.yaml
    
    # 4. Deployment (main application)
    print_status "Applying Deployment..."
    kubectl apply -f deployment.yaml
    
    # 5. Service (ClusterIP)
    print_status "Applying Service..."
    kubectl apply -f service.yaml
    
    # 6. HPA (Horizontal Pod Autoscaler)
    print_status "Applying Horizontal Pod Autoscaler..."
    kubectl apply -f hpa.yaml
    
    print_success "All manifests applied successfully!"
}

# Wait for deployment to be ready
wait_for_deployment() {
    print_status "Waiting for deployment to be ready..."
    kubectl wait --for=condition=available --timeout=300s deployment/geojson-ingestion
    
    print_success "Deployment is ready!"
}

# Get service information
get_service_info() {
    print_status "Getting service information..."
    
    echo ""
    echo "📊 Service Status:"
    kubectl get service geojson-ingestion-service
    
    echo ""
    echo "🔍 Pod Status:"
    kubectl get pods -l app=geojson-ingestion
    
    echo ""
    echo "📈 HPA Status:"
    kubectl get hpa geojson-ingestion-hpa
    
    echo ""
    print_success "Deployment complete! Your service should be accessible via the LoadBalancer IP above."
}

# Get service information
get_service_info() {
    print_status "Getting service information..."
    
    echo ""
    echo "📊 Service Status:"
    kubectl get service geojson-ingestion-service
    
    echo ""
    echo "🌐 Ingress Status:"
    kubectl get ingress geojson-ingestion-ingress
    
    echo ""
    echo "🔍 Pod Status:"
    kubectl get pods -l app=geojson-ingestion
    
    echo ""
    echo "📈 HPA Status:"
    kubectl get hpa geojson-ingestion-hpa
    
    echo ""
    print_status "To get the ALB URL, run:"
    echo "  kubectl get ingress geojson-ingestion-ingress -o jsonpath='{.status.loadBalancer.ingress[0].hostname}'"
    echo ""
    print_success "Deployment complete! Your service should be accessible via the ALB URL above."
}

# Main execution
main() {
    print_status "Starting Kubernetes deployment..."
    
    check_kubectl
    check_prerequisites
    deploy
    wait_for_deployment
    get_service_info
    
    print_success "🎉 GeoJSON Ingestion Service deployed successfully!"
}

# Run main function
main "$@"
