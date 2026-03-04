# Backup and Recovery Strategy

This document outlines the backup and recovery strategy for the GeoJSON Ingestion Microservice.

## Overview

The service uses AWS RDS PostgreSQL with PostGIS for data storage. This guide covers backup configuration, recovery procedures, and disaster recovery planning.

## RDS Automated Backups

### Configuration

RDS automated backups are configured via Terraform with the following settings:

```hcl
backup_retention_period = 7  # Days
backup_window          = "03:00-04:00"  # UTC
copy_tags_to_snapshot = true
```

### What's Backed Up

- **Database data:** All tables, indexes, and data
- **Transaction logs:** Continuous backup for point-in-time recovery
- **PostGIS extensions:** Included in backups
- **Database configuration:** Parameters and settings

### Backup Retention

- **Automated backups:** 7 days retention
- **Manual snapshots:** Retained until manually deleted
- **Transaction logs:** Available for point-in-time recovery within retention period

## Manual Snapshots

### Creating a Snapshot

```bash
# Via AWS CLI
aws rds create-db-snapshot \
  --db-instance-identifier geojson-db \
  --db-snapshot-identifier geojson-db-snapshot-$(date +%Y%m%d-%H%M%S) \
  --region us-east-1

# Via AWS Console
# RDS → Databases → Select instance → Actions → Take snapshot
```

### Listing Snapshots

```bash
# List all snapshots
aws rds describe-db-snapshots \
  --db-instance-identifier geojson-db \
  --region us-east-1

# List automated backups
aws rds describe-db-snapshots \
  --snapshot-type automated \
  --db-instance-identifier geojson-db \
  --region us-east-1
```

## Point-in-Time Recovery

### When to Use

- Accidental data deletion
- Data corruption
- Need to restore to specific timestamp

### Recovery Process

```bash
# Restore to specific point in time
aws rds restore-db-instance-to-point-in-time \
  --source-db-instance-identifier geojson-db \
  --target-db-instance-identifier geojson-db-restored \
  --restore-time 2024-12-01T10:00:00Z \
  --region us-east-1
```

**Note:** Creates a new RDS instance. Update application configuration to point to new instance.

## Snapshot Restoration

### Restore from Snapshot

```bash
# Restore from manual snapshot
aws rds restore-db-instance-from-db-snapshot \
  --db-instance-identifier geojson-db-restored \
  --db-snapshot-identifier geojson-db-snapshot-20241201 \
  --region us-east-1
```

### Restore from Automated Backup

```bash
# List available automated backups
aws rds describe-db-snapshots \
  --snapshot-type automated \
  --db-instance-identifier geojson-db \
  --region us-east-1

# Restore from automated backup
aws rds restore-db-instance-from-db-snapshot \
  --db-instance-identifier geojson-db-restored \
  --db-snapshot-identifier rds:geojson-db-2024-12-01-03-00 \
  --region us-east-1
```

## Application-Level Backups

### Export Data

```bash
# Export all data to SQL file
PGPASSWORD="$DB_PASSWORD" pg_dump \
  -h $RDS_ENDPOINT \
  -U postgres \
  -d geojson_db \
  -F c \
  -f backup-$(date +%Y%m%d).dump

# Export to plain SQL
PGPASSWORD="$DB_PASSWORD" pg_dump \
  -h $RDS_ENDPOINT \
  -U postgres \
  -d geojson_db \
  -f backup-$(date +%Y%m%d).sql
```

### Import Data

```bash
# Restore from custom format dump
PGPASSWORD="$DB_PASSWORD" pg_restore \
  -h $RDS_ENDPOINT \
  -U postgres \
  -d geojson_db \
  backup-20241201.dump

# Restore from SQL file
PGPASSWORD="$DB_PASSWORD" psql \
  -h $RDS_ENDPOINT \
  -U postgres \
  -d geojson_db \
  -f backup-20241201.sql
```

## Backup Verification

### Test Restore Procedure

Regularly test backup restoration:

1. Create test RDS instance from snapshot
2. Verify data integrity
3. Test application connectivity
4. Delete test instance

```bash
# Monthly backup verification script
#!/bin/bash
SNAPSHOT_ID=$(aws rds describe-db-snapshots \
  --snapshot-type automated \
  --db-instance-identifier geojson-db \
  --query 'DBSnapshots[0].DBSnapshotIdentifier' \
  --output text \
  --region us-east-1)

# Restore to test instance
aws rds restore-db-instance-from-db-snapshot \
  --db-instance-identifier geojson-db-test \
  --db-snapshot-identifier $SNAPSHOT_ID \
  --region us-east-1

# Wait for instance to be available
aws rds wait db-instance-available \
  --db-instance-identifier geojson-db-test \
  --region us-east-1

# Verify data (run queries)
# ...

# Cleanup
aws rds delete-db-instance \
  --db-instance-identifier geojson-db-test \
  --skip-final-snapshot \
  --region us-east-1
```

## Disaster Recovery Plan

### RTO (Recovery Time Objective)
- **Target:** 4 hours
- **Process:** Restore from snapshot or point-in-time recovery

### RPO (Recovery Point Objective)
- **Target:** 1 hour (transaction log backup frequency)
- **Actual:** Up to 5 minutes (continuous backup)

### Recovery Steps

1. **Assess Damage**
   ```bash
   # Check RDS instance status
   aws rds describe-db-instances \
     --db-instance-identifier geojson-db \
     --region us-east-1
   ```

2. **Determine Recovery Method**
   - Point-in-time recovery (if within retention period)
   - Snapshot restoration (if point-in-time not available)
   - Cross-region snapshot (if region failure)

3. **Restore Database**
   - Create new RDS instance from backup
   - Update security groups
   - Update application configuration

4. **Verify Data Integrity**
   ```sql
   -- Check record counts
   SELECT COUNT(*) FROM geo_features;
   
   -- Verify PostGIS extension
   SELECT PostGIS_version();
   
   -- Check recent data
   SELECT * FROM geo_features 
   ORDER BY created_at DESC LIMIT 10;
   ```

5. **Update Application**
   - Update Kubernetes secrets with new RDS endpoint
   - Restart pods
   - Verify health checks

6. **Monitor**
   - Check application logs
   - Monitor metrics
   - Verify ingestion working

## Cross-Region Backup

### Enable Cross-Region Snapshot Copy

```bash
# Copy snapshot to another region
aws rds copy-db-snapshot \
  --source-db-snapshot-identifier rds:geojson-db-2024-12-01-03-00 \
  --target-db-snapshot-identifier geojson-db-dr-snapshot \
  --source-region us-east-1 \
  --target-region us-west-2
```

### Automated Cross-Region Backup

Configure via Terraform or AWS Console:
- Enable automated cross-region snapshot copy
- Set target region
- Configure retention period

## Backup Monitoring

### CloudWatch Alarms

Set up alarms for:
- Backup failures
- Snapshot creation failures
- Backup retention period warnings

```bash
# Create CloudWatch alarm for backup failures
aws cloudwatch put-metric-alarm \
  --alarm-name rds-backup-failure \
  --alarm-description "Alert on RDS backup failures" \
  --metric-name BackupRetentionPeriod \
  --namespace AWS/RDS \
  --statistic Average \
  --period 300 \
  --threshold 7 \
  --comparison-operator LessThanThreshold \
  --evaluation-periods 1 \
  --region us-east-1
```

## Best Practices

1. **Regular Testing:** Test restore procedures monthly
2. **Multiple Backups:** Keep manual snapshots before major changes
3. **Documentation:** Maintain runbooks for recovery procedures
4. **Monitoring:** Set up alerts for backup failures
5. **Retention Policy:** Align retention with business requirements
6. **Encryption:** Ensure backups are encrypted
7. **Cross-Region:** Consider cross-region backups for DR
8. **Automation:** Automate backup verification where possible

## Backup Schedule

- **Automated Backups:** Daily at 03:00 UTC
- **Manual Snapshots:** Before major deployments or changes
- **Verification:** Monthly restore testing
- **Review:** Quarterly backup strategy review

## Cost Considerations

- **Automated Backups:** Included in RDS pricing (within retention period)
- **Manual Snapshots:** Storage costs apply
- **Cross-Region Copies:** Additional storage and transfer costs
- **Point-in-Time Recovery:** No additional cost (within retention)

## References

- [AWS RDS Backup Documentation](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/CHAP_CommonTasks.BackupRestore.html)
- [PostgreSQL Backup Documentation](https://www.postgresql.org/docs/current/backup.html)
- [Terraform RDS Module](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/db_instance)

