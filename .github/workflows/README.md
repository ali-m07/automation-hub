# CI/CD Workflows

This directory contains GitHub Actions workflows for automated testing, building, and deployment.

## 📋 Workflows

### ci-cd.yml

Main CI/CD pipeline that runs on:
- Push to `main` or `develop` branches
- Pull requests
- Release creation

**Jobs:**
1. **test** - Runs linting and tests
2. **build** - Builds and pushes Docker image
3. **deploy-dev** - Deploys to development on `develop` branch
4. **deploy-prod** - Deploys to production on release
5. **security-scan** - Runs Trivy vulnerability scanner

### k8s-deploy.yml

Manual deployment workflow for:
- Deploying to specific environments
- Deploying specific image tags
- Manual rollouts

**Usage:**
```bash
gh workflow run k8s-deploy.yml \
  -f environment=production \
  -f image_tag=v1.0.0
```

## 🔐 Required Secrets

Configure these in GitHub repository settings:

- `KUBECONFIG_DEV` - Kubernetes config for development environment
- `KUBECONFIG_PROD` - Kubernetes config for production environment
- `GITHUB_TOKEN` - Automatically provided by GitHub

## 🚀 Setup Instructions

1. **Configure Image Registry**

   Update `.github/workflows/ci-cd.yml`:
   ```yaml
   env:
     REGISTRY: ghcr.io  # or your registry
     IMAGE_NAME: ${{ github.repository }}
   ```

2. **Add Kubernetes Secrets**

   - Go to repository Settings → Secrets and variables → Actions
   - Add `KUBECONFIG_DEV` and `KUBECONFIG_PROD`
   - Get kubeconfig: `kubectl config view --flatten`

3. **Update Ingress URLs**

   Edit `.github/workflows/ci-cd.yml`:
   ```yaml
   environment:
     url: https://your-domain.com
   ```

## 📊 Workflow Triggers

| Event | Action |
|-------|--------|
| Push to `develop` | Test → Build → Deploy to Dev |
| Push to `main` | Test → Build (tag as `latest`) |
| Create Release | Test → Build → Deploy to Prod |
| Pull Request | Test only |
| Manual (k8s-deploy) | Deploy to specified environment |

## 🔍 Monitoring

View workflow runs:
- GitHub Actions tab in repository
- Check logs for each job
- View deployment status

## 🛠️ Customization

### Change Build Platforms

Edit `ci-cd.yml`:
```yaml
platforms: linux/amd64,linux/arm64  # Add/remove platforms
```

### Add More Environments

1. Add environment in `k8s-deploy.yml` options
2. Create corresponding Kubernetes namespace
3. Add KUBECONFIG secret for new environment

### Customize Tests

Edit test job in `ci-cd.yml`:
```yaml
- name: Run tests
  run: |
    pytest --cov=. --cov-report=xml
```
