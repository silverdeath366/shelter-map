# AWS IAM Setup for EKS Service Account (IRSA)

## Overview

This guide explains how to set up IAM Roles for Service Accounts (IRSA) to allow your EKS pods to access AWS services securely without hardcoded credentials.

## Why IRSA?

**Traditional Approach (❌ Not Recommended):**
- Store AWS credentials in environment variables or secrets
- Credentials can be leaked or compromised
- Difficult to rotate credentials
- No audit trail

**IRSA Approach (✅ Best Practice):**
- Pods use IAM roles, not credentials
- Automatic credential rotation
- Fine-grained permissions per service account
- Full audit trail via CloudTrail
- No credentials in containers

## How IRSA Works

1. **IAM Role**: Create an IAM role with necessary permissions
2. **OIDC Provider**: EKS cluster has an OIDC provider
3. **Service Account**: Annotate service account with IAM role ARN
4. **Token Injection**: EKS automatically injects temporary credentials via STS
5. **AWS SDK**: Applications use boto3 which automatically uses the credentials

## Step-by-Step Setup

### Step 1: Create IAM Role

```bash
# 1. Get your EKS cluster OIDC issuer URL
aws eks describe-cluster --name silver-saas-cluster --query "cluster.identity.oidc.issuer" --output text

# Output: https://oidc.eks.us-east-1.amazonaws.com/id/EXAMPLED539D4633E53DE1B716D304

# 2. Create trust policy for the IAM role
cat > trust-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::YOUR_AWS_ACCOUNT_ID:oidc-provider/oidc.eks.us-east-1.amazonaws.com/id/YOUR_OIDC_ID"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "oidc.eks.us-east-1.amazonaws.com/id/YOUR_OIDC_ID:sub": "system:serviceaccount:default:geojson-ingestion-sa",
          "oidc.eks.us-east-1.amazonaws.com/id/YOUR_OIDC_ID:aud": "sts.amazonaws.com"
        }
      }
    }
  ]
}
EOF

# 3. Create IAM role
aws iam create-role \
  --role-name geojson-ingestion-role \
  --assume-role-policy-document file://trust-policy.json \
  --description "IAM role for GeoJSON ingestion service account"
```

### Step 2: Attach Permissions Policy

```bash
# Create policy for CloudWatch Logs access
cat > cloudwatch-logs-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents",
        "logs:DescribeLogStreams"
      ],
      "Resource": "arn:aws:logs:us-east-1:YOUR_AWS_ACCOUNT_ID:log-group:/aws/eks/geojson-ingestion*"
    }
  ]
}
EOF

# Create the policy
aws iam create-policy \
  --policy-name GeoJSONIngestionCloudWatchPolicy \
  --policy-document file://cloudwatch-logs-policy.json

# Attach policy to role
aws iam attach-role-policy \
  --role-name geojson-ingestion-role \
  --policy-arn arn:aws:iam::YOUR_AWS_ACCOUNT_ID:policy/GeoJSONIngestionCloudWatchPolicy
```

### Step 3: Update Service Account

The service account is already configured in `k8s/service-account.yaml`. Just update the role ARN:

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: geojson-ingestion-sa
  namespace: default
  annotations:
    eks.amazonaws.com/role-arn: arn:aws:iam::YOUR_AWS_ACCOUNT_ID:role/geojson-ingestion-role
```

### Step 4: Apply Service Account

```bash
kubectl apply -f k8s/service-account.yaml
```

### Step 5: Verify

```bash
# Check service account
kubectl describe serviceaccount geojson-ingestion-sa -n default

# Check if pod is using the service account
kubectl get pod -l app=geojson-ingestion -o jsonpath='{.items[0].spec.serviceAccountName}'

# Check environment variables in pod (should see AWS_ROLE_ARN and AWS_WEB_IDENTITY_TOKEN_FILE)
kubectl exec -it <pod-name> -- env | grep AWS
```

## Required Permissions

### CloudWatch Logs (Current Implementation)

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogEvents",
        "logs:PutLogEvents",
        "logs:DescribeLogStreams"
      ],
      "Resource": "arn:aws:logs:*:*:log-group:/aws/eks/geojson-ingestion*"
    }
  ]
}
```

### AWS Secrets Manager (Optional - for future use)

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "secretsmanager:GetSecretValue",
        "secretsmanager:DescribeSecret"
      ],
      "Resource": "arn:aws:secretsmanager:us-east-1:YOUR_AWS_ACCOUNT_ID:secret:geojson-db-credentials-*"
    }
  ]
}
```

## Troubleshooting

### Issue: Pod can't assume role

**Error**: `Unable to locate credentials`

**Solution**:
1. Verify OIDC provider is configured for your cluster
2. Check service account annotation matches role ARN
3. Verify trust policy conditions match your service account

### Issue: Permission denied

**Error**: `AccessDenied` when calling AWS API

**Solution**:
1. Check IAM policy permissions
2. Verify resource ARNs in policy match actual resources
3. Check CloudTrail logs for detailed error messages

### Issue: Role not found

**Error**: `NoSuchEntity` when describing role

**Solution**:
1. Verify role name is correct
2. Check AWS region matches
3. Verify you're using the correct AWS account ID

## Best Practices

1. **Least Privilege**: Only grant necessary permissions
2. **Separate Roles**: Use different roles for different services
3. **Resource Restrictions**: Limit resources in IAM policies (use specific ARNs)
4. **Regular Audits**: Review IAM policies regularly
5. **Use Conditions**: Add conditions to policies for extra security

## Additional Resources

- [AWS EKS IAM Roles for Service Accounts](https://docs.aws.amazon.com/eks/latest/userguide/iam-roles-for-service-accounts.html)
- [IAM Best Practices](https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html)
- [CloudWatch Logs Permissions](https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/iam-identity-based-access-control-cwl.html)

