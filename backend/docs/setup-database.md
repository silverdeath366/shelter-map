# Database Setup Guide

Options for setting up a database for the GeoJSON Ingestion Microservice.

---

## Option 1: Quick Local PostGIS (Docker) - Easiest for Testing

**Best for:** Development, testing, quick setup

```bash
# Run PostGIS in Docker
docker run -d \
  --name postgis-geojson \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=geojson_db \
  -e POSTGRES_USER=postgres \
  -p 5432:5432 \
  postgis/postgis:15-3.3

# Enable PostGIS extension
docker exec -it postgis-geojson psql -U postgres -d geojson_db -c "CREATE EXTENSION IF NOT EXISTS postgis;"

# Verify
docker exec -it postgis-geojson psql -U postgres -d geojson_db -c "SELECT PostGIS_version();"
```

**Credentials:**
- Host: `localhost` (or your Docker host IP)
- Port: `5432`
- Database: `geojson_db`
- User: `postgres`
- Password: `postgres`

**Use in deployment:**
```bash
export DB_HOST=localhost
export DB_PASSWORD=postgres
```

---

## Option 2: AWS RDS PostgreSQL with PostGIS

**Best for:** Production, AWS users

### Create RDS Instance

```bash
# Via AWS CLI
aws rds create-db-instance \
  --db-instance-identifier geojson-db \
  --db-instance-class db.t3.micro \
  --engine postgres \
  --engine-version 15.4 \
  --master-username postgres \
  --master-user-password YourSecurePassword123! \
  --allocated-storage 20 \
  --storage-type gp2 \
  --vpc-security-group-ids sg-xxxxx \
  --db-subnet-group-name default \
  --backup-retention-period 7 \
  --region us-east-1

# Wait for instance to be available (10-15 minutes)
aws rds wait db-instance-available --db-instance-identifier geojson-db
```

### Get RDS Endpoint

```bash
# Get endpoint
aws rds describe-db-instances \
  --db-instance-identifier geojson-db \
  --query 'DBInstances[0].Endpoint.Address' \
  --output text

# Example output: geojson-db.xxxxx.us-east-1.rds.amazonaws.com
```

### Enable PostGIS Extension

```bash
# Connect and enable PostGIS
export RDS_ENDPOINT=$(aws rds describe-db-instances \
  --db-instance-identifier geojson-db \
  --query 'DBInstances[0].Endpoint.Address' \
  --output text)

psql -h $RDS_ENDPOINT -U postgres -d postgres << EOF
CREATE DATABASE geojson_db;
\c geojson_db
CREATE EXTENSION IF NOT EXISTS postgis;
SELECT PostGIS_version();
EOF
```

**Credentials:**
- Host: `geojson-db.xxxxx.us-east-1.rds.amazonaws.com` (from AWS)
- Port: `5432`
- Database: `geojson_db`
- User: `postgres` (or what you set)
- Password: `YourSecurePassword123!` (what you set)

---

## Option 3: Managed PostGIS Services

### DigitalOcean Managed PostgreSQL

1. Create database in DigitalOcean dashboard
2. Enable PostGIS extension in database settings
3. Get connection details from dashboard

### Heroku Postgres

```bash
# Create Heroku app
heroku create your-app-name

# Add PostGIS addon
heroku addons:create heroku-postgresql:mini

# Enable PostGIS
heroku pg:psql -c "CREATE EXTENSION IF NOT EXISTS postgis;"
```

### Supabase

1. Create project at supabase.com
2. Go to SQL Editor
3. Run: `CREATE EXTENSION IF NOT EXISTS postgis;`
4. Get connection string from Settings → Database

---

## Option 4: Reset RDS Password

If you forgot your RDS password:

```bash
# Reset password
aws rds modify-db-instance \
  --db-instance-identifier geojson-db \
  --master-user-password YourNewPassword123! \
  --apply-immediately

# Wait for modification to complete
aws rds wait db-instance-available --db-instance-identifier geojson-db
```

**Note:** This will cause a brief connection interruption.

---

## Option 5: Find Existing Database

### Check Kubernetes Secrets

```bash
# View secret
kubectl get secret geojson-db-secret -o yaml

# Decode values
kubectl get secret geojson-db-secret -o jsonpath='{.data.DB_HOST}' | base64 -d
kubectl get secret geojson-db-secret -o jsonpath='{.data.DB_PASSWORD}' | base64 -d
```

### Check Terraform Outputs

```bash
cd terraform
terraform output rds_host
terraform output rds_port
```

### Check AWS RDS

```bash
# List all RDS instances
aws rds describe-db-instances \
  --query 'DBInstances[*].[DBInstanceIdentifier,Endpoint.Address,Engine]' \
  --output table

# Get specific instance details
aws rds describe-db-instances \
  --db-instance-identifier your-db-name \
  --query 'DBInstances[0].Endpoint.Address' \
  --output text
```

### Check Environment Variables

```bash
# Check current environment
env | grep DB_

# Check .env file
cat .env | grep DB_
```

---

## Quick Setup Script

Create a new database quickly:

```bash
#!/bin/bash
# quick-db-setup.sh

# Option 1: Local Docker
if [ "$1" = "local" ]; then
    docker run -d \
      --name postgis-geojson \
      -e POSTGRES_PASSWORD=postgres \
      -e POSTGRES_DB=geojson_db \
      -p 5432:5432 \
      postgis/postgis:15-3.3
    
    sleep 5
    docker exec -it postgis-geojson psql -U postgres -d geojson_db -c "CREATE EXTENSION IF NOT EXISTS postgis;"
    
    echo "Database ready!"
    echo "Host: localhost"
    echo "Password: postgres"
    exit 0
fi

# Option 2: AWS RDS
if [ "$1" = "rds" ]; then
    read -p "Enter RDS instance name: " INSTANCE_NAME
    read -sp "Enter password: " PASSWORD
    echo ""
    
    aws rds create-db-instance \
      --db-instance-identifier $INSTANCE_NAME \
      --db-instance-class db.t3.micro \
      --engine postgres \
      --engine-version 15.4 \
      --master-username postgres \
      --master-user-password $PASSWORD \
      --allocated-storage 20 \
      --region us-east-1
    
    echo "RDS instance creating... (10-15 minutes)"
    echo "Check status: aws rds describe-db-instances --db-instance-identifier $INSTANCE_NAME"
fi
```

---

## Test Database Connection

```bash
# Test connection
psql -h $DB_HOST -U postgres -d geojson_db -c "SELECT version();"

# Test PostGIS
psql -h $DB_HOST -U postgres -d geojson_db -c "SELECT PostGIS_version();"
```

---

## Common Issues

### "Connection refused"
- Check if database is running
- Verify host and port
- Check firewall/security groups

### "Authentication failed"
- Verify username and password
- Check if user exists
- Verify database name

### "Extension postgis does not exist"
- Run: `CREATE EXTENSION IF NOT EXISTS postgis;`
- Verify PostGIS is installed on database server

---

## Recommended Setup

**For Development/Testing:**
- Use Option 1 (Local Docker) - Fastest, easiest

**For Production:**
- Use Option 2 (AWS RDS) or Option 3 (Managed Service)
- Enable backups
- Use strong passwords
- Enable SSL/TLS

---

## Next Steps

Once you have database credentials:

```bash
export DB_HOST=your-host
export DB_PASSWORD=your-password
./deploy-simple.sh
```

Or use the find script:
```bash
./scripts/find-db-credentials.sh
```

