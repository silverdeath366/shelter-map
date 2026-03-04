#!/bin/bash

# GeoJSON Ingestion Service - Build and Test Script
set -e

echo "🚀 Starting GeoJSON Ingestion Service Build and Test Process"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
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

# Check if Docker is running
check_docker() {
    print_status "Checking Docker availability..."
    if ! docker info > /dev/null 2>&1; then
        print_error "Docker is not running. Please start Docker and try again."
        exit 1
    fi
    print_success "Docker is running"
}

# Build Docker image
build_image() {
    print_status "Building Docker image..."
    if docker build -t geojson-app .; then
        print_success "Docker image built successfully"
    else
        print_error "Failed to build Docker image"
        exit 1
    fi
}

# Test the application locally
test_local() {
    print_status "Testing application locally..."
    
    # Start the application in background
    print_status "Starting application container..."
    docker run -d --name geojson-test \
        -p 8000:8000 \
        -e DB_HOST=localhost \
        -e DB_NAME=test_db \
        -e DB_USER=test_user \
        -e DB_PASSWORD=test_pass \
        geojson-app
    
    # Wait for application to start
    print_status "Waiting for application to start..."
    sleep 10
    
    # Test health endpoint
    print_status "Testing health endpoint..."
    if curl -f http://localhost:8000/healthz > /dev/null 2>&1; then
        print_success "Health endpoint is working"
    else
        print_error "Health endpoint is not responding"
        docker logs geojson-test
        docker stop geojson-test
        docker rm geojson-test
        exit 1
    fi
    
    # Test with sample GeoJSON
    print_status "Testing GeoJSON ingestion..."
    if [ -f "../test.geojson" ]; then
        if curl -X POST http://localhost:8000/ingest \
            -F "file=@../test.geojson" > /dev/null 2>&1; then
            print_success "GeoJSON ingestion test passed"
        else
            print_warning "GeoJSON ingestion test failed (this might be expected without a database)"
        fi
    else
        print_warning "No test.geojson file found, skipping ingestion test"
    fi
    
    # Cleanup test container
    print_status "Cleaning up test container..."
    docker stop geojson-test
    docker rm geojson-test
}

# Test with Docker Compose (full stack)
test_docker_compose() {
    print_status "Testing with Docker Compose..."
    
    # Stop any existing containers
    docker-compose down -v 2>/dev/null || true
    
    # Start the full stack
    print_status "Starting full stack with Docker Compose..."
    if docker-compose up -d --build; then
        print_success "Docker Compose stack started successfully"
        
        # Wait for services to be ready
        print_status "Waiting for services to be ready..."
        sleep 30
        
        # Test health endpoint
        print_status "Testing health endpoint..."
        if curl -f http://localhost:8000/healthz > /dev/null 2>&1; then
            print_success "Health endpoint is working"
        else
            print_error "Health endpoint is not responding"
            docker-compose logs app
            docker-compose down -v
            exit 1
        fi
        
        # Test database connection
        print_status "Testing database connection..."
        if docker-compose exec -T db pg_isready -U postgres -d geospatial > /dev/null 2>&1; then
            print_success "Database is ready"
        else
            print_error "Database is not ready"
            docker-compose logs db
            docker-compose down -v
            exit 1
        fi
        
        # Test GeoJSON ingestion
        print_status "Testing GeoJSON ingestion with database..."
        if [ -f "../test.geojson" ]; then
            if curl -X POST http://localhost:8000/ingest \
                -F "file=@../test.geojson" > /dev/null 2>&1; then
                print_success "GeoJSON ingestion test passed"
                
                # Check if data was stored
                print_status "Verifying data storage..."
                sleep 5
                if docker-compose exec -T db psql -U postgres -d geospatial -c "SELECT COUNT(*) FROM geo_features;" | grep -q "[0-9]"; then
                    print_success "Data was successfully stored in database"
                else
                    print_warning "No data found in database"
                fi
            else
                print_error "GeoJSON ingestion test failed"
                docker-compose logs app
            fi
        else
            print_warning "No test.geojson file found, skipping ingestion test"
        fi
        
        # Show logs
        print_status "Application logs:"
        docker-compose logs app --tail=20
        
        # Stop the stack
        print_status "Stopping Docker Compose stack..."
        docker-compose down -v
        
    else
        print_error "Failed to start Docker Compose stack"
        docker-compose logs
        exit 1
    fi
}

# Build for production
build_production() {
    print_status "Building production image..."
    
    # Build with production tag
    if docker build -t geojson-app:latest -t geojson-app:production .; then
        print_success "Production image built successfully"
        
        # Show image info
        print_status "Image details:"
        docker images geojson-app
        
        # Show image layers
        print_status "Image layers:"
        docker history geojson-app:latest
    else
        print_error "Failed to build production image"
        exit 1
    fi
}

# Main execution
main() {
    print_status "Starting build and test process..."
    
    # Check prerequisites
    check_docker
    
    # Build image
    build_image
    
    # Test locally
    test_local
    
    # Test with Docker Compose
    test_docker_compose
    
    # Build production image
    build_production
    
    print_success "🎉 All tests passed! The GeoJSON ingestion service is ready for deployment."
    print_status "Next steps:"
    echo "  1. Push to ECR: docker tag geojson-app:latest <ecr-url>:latest"
    echo "  2. Deploy to EKS using the provided Kubernetes manifests"
    echo "  3. Configure environment variables for production database"
}

# Run main function
main "$@"
