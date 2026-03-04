#!/bin/bash

# Script to help find database credentials
# Checks multiple sources for database host and password

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}=== Database Credentials Finder ===${NC}"
echo ""

# Check 1: Kubernetes secrets
echo -e "${YELLOW}1. Checking Kubernetes secrets...${NC}"
if kubectl get secret geojson-db-secret &>/dev/null; then
    echo -e "${GREEN}✓ Found Kubernetes secret: geojson-db-secret${NC}"
    echo ""
    echo "Database Host:"
    kubectl get secret geojson-db-secret -o jsonpath='{.data.DB_HOST}' | base64 -d 2>/dev/null || echo "Not found"
    echo ""
    echo "Database Port:"
    kubectl get secret geojson-db-secret -o jsonpath='{.data.DB_PORT}' | base64 -d 2>/dev/null || echo "Not found"
    echo ""
    echo "Database Name:"
    kubectl get secret geojson-db-secret -o jsonpath='{.data.DB_NAME}' | base64 -d 2>/dev/null || echo "Not found"
    echo ""
    echo "Database User:"
    kubectl get secret geojson-db-secret -o jsonpath='{.data.DB_USER}' | base64 -d 2>/dev/null || echo "Not found"
    echo ""
    echo "Database Password:"
    kubectl get secret geojson-db-secret -o jsonpath='{.data.DB_PASSWORD}' | base64 -d 2>/dev/null || echo "Not found"
    echo ""
else
    echo -e "${RED}✗ Kubernetes secret not found${NC}"
fi

# Check 2: Terraform outputs
echo ""
echo -e "${YELLOW}2. Checking Terraform outputs...${NC}"
if [ -d "terraform" ] && [ -f "terraform/terraform.tfstate" ]; then
    echo -e "${GREEN}✓ Found Terraform state${NC}"
    cd terraform
    if terraform output rds_host &>/dev/null; then
        echo "RDS Host: $(terraform output -raw rds_host 2>/dev/null)"
    fi
    if terraform output rds_port &>/dev/null; then
        echo "RDS Port: $(terraform output -raw rds_port 2>/dev/null)"
    fi
    cd ..
else
    echo -e "${RED}✗ Terraform state not found${NC}"
fi

# Check 3: Environment variables
echo ""
echo -e "${YELLOW}3. Checking environment variables...${NC}"
if [ -n "$DB_HOST" ]; then
    echo -e "${GREEN}✓ DB_HOST: $DB_HOST${NC}"
else
    echo -e "${RED}✗ DB_HOST not set${NC}"
fi

if [ -n "$DB_PASSWORD" ]; then
    echo -e "${GREEN}✓ DB_PASSWORD: [HIDDEN]${NC}"
else
    echo -e "${RED}✗ DB_PASSWORD not set${NC}"
fi

# Check 4: .env file
echo ""
echo -e "${YELLOW}4. Checking .env file...${NC}"
if [ -f ".env" ]; then
    echo -e "${GREEN}✓ Found .env file${NC}"
    grep "^DB_HOST=" .env 2>/dev/null || echo "DB_HOST not in .env"
    grep "^DB_PASSWORD=" .env 2>/dev/null | sed 's/DB_PASSWORD=.*/DB_PASSWORD=[HIDDEN]/' || echo "DB_PASSWORD not in .env"
else
    echo -e "${RED}✗ .env file not found${NC}"
fi

# Check 5: AWS RDS (if AWS CLI available)
echo ""
echo -e "${YELLOW}5. Checking AWS RDS instances...${NC}"
if command -v aws &> /dev/null; then
    echo "Searching for RDS instances..."
    aws rds describe-db-instances \
        --query 'DBInstances[*].[DBInstanceIdentifier,Endpoint.Address,Endpoint.Port,Engine]' \
        --output table 2>/dev/null || echo "Could not query AWS RDS (check AWS credentials)"
else
    echo -e "${RED}✗ AWS CLI not installed${NC}"
fi

# Check 6: Terraform variables file
echo ""
echo -e "${YELLOW}6. Checking Terraform variables...${NC}"
if [ -f "terraform/terraform.tfvars" ]; then
    echo -e "${GREEN}✓ Found terraform.tfvars${NC}"
    if grep -q "db_password" terraform/terraform.tfvars; then
        echo "db_password found in terraform.tfvars (check the file)"
    fi
else
    echo -e "${RED}✗ terraform.tfvars not found${NC}"
fi

echo ""
echo -e "${BLUE}=== Next Steps ===${NC}"
echo ""
echo "If you found credentials above, you can:"
echo "  1. Export them:"
echo "     export DB_HOST=your-host"
echo "     export DB_PASSWORD=your-password"
echo ""
echo "  2. Or use them directly:"
echo "     ./deploy-simple.sh"
echo ""
echo "If you need to reset the password or create a new database, see:"
echo "  - docs/setup-database.md (if it exists)"
echo "  - Or use a managed PostGIS service"
echo ""

