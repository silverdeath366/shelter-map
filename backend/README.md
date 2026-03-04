# GeoJSON Ingestion Service

A production-ready REST API microservice for ingesting, validating, and querying GeoJSON geographic data using PostgreSQL/PostGIS.

## Overview

This service has been integrated into the existing EKS infrastructure and follows the established patterns:
- ✅ AWS Secrets Manager integration via CSI driver
- ✅ IRSA (IAM Roles for Service Accounts) for secure AWS access
- ✅ Network policies for network isolation
- ✅ ALB Ingress for external access
- ✅ Security contexts for pod hardening
- ✅ CloudWatch logging and monitoring

## Quick Start

### Option 1: Automated Deployment & Testing (Recommended)

```bash
cd services/geojson-ingestion

# 1. Create AWS Secrets Manager secret first (see Prerequisites below)
# 2. Run the automated script
./test-and-deploy.sh
```

This script will handle everything: prerequisites, building, deploying, and testing.

### Option 2: Manual Deployment

See [QUICK_START.md](QUICK_START.md) for detailed manual steps.

### Prerequisites

1. **AWS Secrets Manager Secret**: Create a secret named `geojson-db-credentials` with the following JSON structure:
   ```json
   {
     "DB_HOST": "your-rds-endpoint.rds.amazonaws.com",
     "DB_PORT": "5432",
     "DB_NAME": "geojson_db",
     "DB_USER": "postgres",
     "DB_PASSWORD": "your-password",
     "DB_SSLMODE": "prefer"
   }
   ```

2. **ECR Repository**: Ensure the ECR repository exists:
   ```bash
   aws ecr create-repository --repository-name geojson-ingestion --region us-east-1
   ```

3. **EKS Cluster**: Ensure you're connected to the EKS cluster:
   ```bash
   aws eks update-kubeconfig --name silver-saas-cluster --region us-east-1
   ```

### Deployment

1. **Build and push Docker image**:
   ```bash
   cd services/geojson-ingestion
   
   # Set variables
   export AWS_REGION=us-east-1
   export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
   export ECR_REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
   export IMAGE_NAME="${ECR_REGISTRY}/geojson-ingestion"
   
   # Login to ECR
   aws ecr get-login-password --region $AWS_REGION | \
     docker login --username AWS --password-stdin $ECR_REGISTRY
   
   # Build and push
   docker build -t geojson-ingestion:latest .
   docker tag geojson-ingestion:latest ${IMAGE_NAME}:latest
   docker push ${IMAGE_NAME}:latest
   ```

2. **Update deployment image** (if needed):
   ```bash
   # Update the image in k8s/deployment.yaml or use sed:
   sed -i "s|\${ECR_REGISTRY}|${ECR_REGISTRY}|g" k8s/deployment.yaml
   ```

3. **Deploy to Kubernetes**:
   ```bash
   cd k8s
   ./deploy.sh
   ```

   Or manually:
   ```bash
   kubectl apply -f 01-secretproviderclass.yaml
   kubectl apply -f service-account.yaml
   kubectl apply -f network-policy.yaml
   kubectl apply -f deployment.yaml
   kubectl apply -f service.yaml
   kubectl apply -f hpa.yaml
   ```

4. **Get the ALB URL**:
   ```bash
   kubectl get ingress geojson-ingestion-ingress -o jsonpath='{.status.loadBalancer.ingress[0].hostname}'
   ```

## API Endpoints

- `GET /healthz` - Health check
- `POST /v1/ingest` - Ingest GeoJSON data
- `GET /v1/files` - List all features (paginated)
- `GET /v1/features/bbox` - Query by bounding box
- `GET /v1/features/nearby` - Query by proximity
- `GET /v1/export` - Export all as GeoJSON
- `GET /metrics` - Prometheus metrics
- `GET /v1/docs` - Interactive API documentation

## Architecture

The service integrates with the existing infrastructure:

```
AWS EKS Cluster
├── GeoJSON Ingestion Service
│   ├── Deployment (2 replicas, auto-scaling 2-10)
│   ├── Service (ClusterIP)
│   ├── Ingress (ALB - internet-facing)
│   ├── NetworkPolicy (default-deny with explicit allows)
│   ├── ServiceAccount (IRSA for AWS access)
│   └── SecretProviderClass (AWS Secrets Manager integration)
│
├── AWS Services
│   ├── Secrets Manager (database credentials)
│   ├── CloudWatch (logs and metrics)
│   └── Application Load Balancer (ingress)
│
└── RDS PostgreSQL/PostGIS
    └── Database for spatial data storage
```

## Configuration

### Environment Variables

The service uses the following environment variables (configured via Secrets Manager):

- `DB_HOST` - PostgreSQL host
- `DB_PORT` - PostgreSQL port (default: 5432)
- `DB_NAME` - Database name
- `DB_USER` - Database user
- `DB_PASSWORD` - Database password
- `DB_SSLMODE` - SSL mode (prefer/require)
- `LOG_LEVEL` - Logging level (INFO/DEBUG)
- `AWS_REGION` - AWS region

### Resource Limits

- **Requests**: 100m CPU, 256Mi memory
- **Limits**: 250m CPU, 512Mi memory
- **Auto-scaling**: 2-10 replicas based on CPU usage (70% threshold)

## Monitoring

- **Logs**: Available in CloudWatch Logs group `/aws/eks/geojson-ingestion`
- **Metrics**: Prometheus metrics available at `/metrics` endpoint
- **Health Checks**: Liveness and readiness probes on `/healthz`

## Security

- ✅ Non-root user (UID 1000)
- ✅ Read-only root filesystem (where possible)
- ✅ Dropped capabilities (ALL)
- ✅ Network policies (default-deny)
- ✅ IRSA for AWS access (no static credentials)
- ✅ Secrets from AWS Secrets Manager (not in etcd)

## Testing

### Quick Test

After deployment, run the test script:

```bash
cd services/geojson-ingestion
./test-service.sh
```

Or test manually:

```bash
# Get service URL
kubectl get ingress geojson-ingestion-ingress -o jsonpath='{.status.loadBalancer.ingress[0].hostname}'

# Test health
curl http://<ALB-URL>/healthz

# Or use port-forward
kubectl port-forward svc/geojson-ingestion-service 8091:80
curl http://localhost:8091/healthz
```

See [TESTING_GUIDE.md](TESTING_GUIDE.md) for comprehensive testing instructions.

## Troubleshooting

### Pods not starting

```bash
# Check pod events
kubectl describe pod -l app=geojson-ingestion

# Check logs
kubectl logs -l app=geojson-ingestion
```

### Database connection issues

```bash
# Verify secret exists
kubectl get secret geojson-db-secret

# Check SecretProviderClass
kubectl get secretproviderclass geojson-db-secrets-store-class

# Verify secrets are mounted
kubectl exec -it deployment/geojson-ingestion -- ls -la /mnt/secrets-store/
```

### ALB not provisioning

```bash
# Check ingress status
kubectl describe ingress geojson-ingestion-ingress

# Check AWS Load Balancer Controller logs
kubectl logs -n kube-system -l app.kubernetes.io/name=aws-load-balancer-controller
```

## Documentation

- [Project Summary](PROJECT_SUMMARY.md) - Detailed project overview
- [Deployment Plan](DEPLOYMENT_PLAN.md) - Production deployment guide
- [Cursor Guide](CURSOR_GUIDE.md) - AI assistant context

## Integration with Existing Infrastructure

This service follows the same patterns as other services in the infrastructure:

1. **Secrets Management**: Uses AWS Secrets Manager via CSI driver (not plain Kubernetes secrets)
2. **Service Accounts**: Uses IRSA for AWS access
3. **Network Policies**: Follows default-deny pattern with explicit allows
4. **Ingress**: Uses ALB Ingress Controller (not LoadBalancer service)
5. **Security**: Applies security contexts matching existing patterns
6. **Monitoring**: Integrates with CloudWatch Container Insights and Fluent Bit

## Next Steps

1. Create the AWS Secrets Manager secret with database credentials
2. Build and push the Docker image to ECR
3. Deploy using the provided scripts
4. Configure DNS to point to the ALB URL
5. Set up monitoring dashboards in CloudWatch
