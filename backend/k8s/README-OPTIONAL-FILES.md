# Optional Kubernetes Files

## Files That Require Additional Setup

### `external-secret-example.yaml`

This file requires the **External Secrets Operator** to be installed in your cluster.

**To use it:**
1. Install External Secrets Operator:
   ```bash
   helm repo add external-secrets https://charts.external-secrets.io
   helm install external-secrets external-secrets/external-secrets -n external-secrets-system --create-namespace
   ```

2. Then apply:
   ```bash
   kubectl apply -f external-secret-example.yaml
   ```

**For now:** This file is optional. The application uses regular Kubernetes secrets (from `secret.yaml`).

---

### `pod-security-policy.yaml`

This file contains:
- ✅ **Pod Security Standards** (applied via namespace labels) - **This works!**
- ❌ **PodSecurityPolicy** (deprecated, removed in K8s 1.25+) - **This doesn't work on EKS 1.28**

The Pod Security Standards part is already applied via namespace labels, so you don't need the PSP part.

---

## Current Deployment

The main deployment files that work:
- ✅ `deployment.yaml` - Main application deployment
- ✅ `service.yaml` - Service for the application
- ✅ `secret.yaml` - Database secrets
- ✅ `service-account.yaml` - Service account with IRSA
- ✅ `network-policy.yaml` - Network policies
- ✅ `hpa.yaml` - Horizontal Pod Autoscaler
- ✅ `init-db-job.yaml` - Database initialization (fixed)

---

**You can safely ignore the warnings about external-secret-example.yaml and pod-security-policy.yaml!** ✅

