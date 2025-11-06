# NICO - Development Guide

This document describes tools and processes for developing and debugging NICO (NixOS Infrastructure Cluster Orchestrator).

## 📁 Development Files

### 1. Dockerfile.dev
Development-optimized Docker image with debugpy support and full development dependencies.

**Features:**
- Includes `debugpy` for remote debugging
- Installs `requirements-dev.txt` (linters, formatters, test tools)
- Source code mounted as volume for hot-reload
- Debugger listens on port 5678

### 2. docker-compose.yml
Multi-service development environment with NICO, NIO, and iPXE server.

**Services:**
- **nico** - NICO operator with debugpy enabled (port 5678)
- **nio** - NIO base infrastructure operator
- **nio-ipxe** - PXE boot server for bare-metal provisioning

### 3. kind-setup.sh
Automated script to create a local Kind cluster for NICO development and testing.

**Features:**
- Automatically installs Kind if not present
- Creates dedicated `nico-dev` cluster
- Configures port mappings for ingress (80, 443, 6443)
- Applies NICO CRDs automatically
- Exports kubeconfig to `~/.kube/nico-dev.kubeconfig`
- Interactive mode for cluster recreation

**Usage:**
```bash
chmod +x kind-setup.sh
./kind-setup.sh

# Then export kubeconfig
export KUBECONFIG=~/.kube/nico-dev.kubeconfig
```

### 4. VS Code Configuration (`.vscode/`)
- **launch.json** - Debug configurations for container and local debugging
- **tasks.json** - Automated tasks for Docker Compose operations

## 🐛 Debugging with VS Code

NICO supports full VSCode debugging with breakpoints, variable inspection, and step-through execution.

### Quick Start: Debug in Container

1. **Start the debugger:**
   - Open VSCode in project root
   - Press `Ctrl+Shift+D` (or `Cmd+Shift+D` on Mac)
   - Select **"NICO: Attach to Docker"** from dropdown
   - Press `F5`

2. **What happens automatically:**
   - Runs `docker-compose up -d nico`
   - Builds `Dockerfile.dev` with debugpy
   - Waits for debugger connection on port 5678
   - Attaches VSCode debugger to running container

3. **Set breakpoints:**
   - Open any Python file (e.g., `kubernetescluster_handlers.py`)
   - Click left of line number to add breakpoint
   - Trigger reconciliation by creating/updating KubernetesCluster resource

### Debug Configurations

#### 1. NICO: Attach to Docker (Recommended)
Auto-starts container and attaches debugger. Best for full development workflow.

```json
{
  "name": "NICO: Attach to Docker",
  "type": "debugpy",
  "request": "attach",
  "preLaunchTask": "docker-compose-up"
}
```

**Usage:**
- Press `F5` to start debugging
- Container starts automatically
- Debugger connects when operator initializes

#### 2. NICO: Attach to Running Container
Connects to already-running container. Useful for quick re-attaches.

**Usage:**
```bash
docker-compose up -d nico
# In VSCode, select this config and press F5
```

#### 3. NICO: Local Debug
Runs operator directly on your machine without Docker.

**Prerequisites:**
- Valid KUBECONFIG pointing to test cluster
- Python 3.11+ installed
- Dependencies from `requirements-dev.txt`

**Usage:**
- Select config and press `F5`
- Useful for quick iteration without container overhead

## 🚀 Quick Start

### Option 1: Full Development Setup (Recommended)

Complete setup with Kind cluster, NICO operator, and VSCode debugging:

```bash
# 1. Create Kind cluster with CRDs
./kind-setup.sh

# 2. Export kubeconfig for development
export KUBECONFIG=~/.kube/nico-dev.kubeconfig

# 3. Start NICO operator with debugger
docker-compose up -d nico

# 4. Attach VSCode debugger
# In VSCode: Press F5 → Select "NICO: Attach to Running Container"

# 5. Test with example KubernetesCluster
kubectl apply -f examples/kubernetescluster-example.yaml

# 6. Watch operator logs
docker-compose logs -f nico
```

### Option 2: Quick Kind Cluster Setup

Just create a test cluster without NICO operator:

```bash
# Create cluster and apply CRDs
./kind-setup.sh

# Export kubeconfig
export KUBECONFIG=~/.kube/nico-dev.kubeconfig

# Verify cluster
kubectl get nodes
kubectl get crds | grep nico
```

### Option 3: Local Development (No Docker)

Run NICO directly on your machine:

```bash
# Ensure you have a Kubernetes cluster
export KUBECONFIG=~/.kube/nico-dev.kubeconfig

# Install dependencies
pip install -r requirements-dev.txt

# Run operator locally
python main.py

# Or debug in VSCode with "NICO: Local Debug" configuration
```

### Option 4: Docker Compose Only

Run all services (NICO, NIO, iPXE) without debugging:

```bash
# Start all services
docker-compose up -d

# View NICO logs
docker-compose logs -f nico

# Stop services
docker-compose down
```

## 🐛 Advanced Debugging

### Setting Breakpoints

Set breakpoints in key reconciliation functions for NICO:

**In `kubernetescluster_handlers.py`:**
- `reconcile_kubernetes_cluster()` - Main cluster reconciliation loop
- `select_machines_for_cluster()` - Machine selection logic
- `generate_cluster_config()` - Cluster configuration generation
- `create_nixos_configuration_for_machine()` - NixosConfiguration creation
- `extract_kubeconfig()` - Kubeconfig extraction from control plane

**In `main.py`:**
- `@kopf.on.create('kubernetesclusters')` - Cluster creation handler
- `@kopf.on.update('kubernetesclusters')` - Cluster update handler
- `@kopf.on.delete('kubernetesclusters')` - Cluster deletion handler

### Debugging Workflow

1. **Set breakpoints** in handler functions
2. **Start debugger** (F5 in VSCode)
3. **Apply test resource:**
   ```bash
   kubectl apply -f examples/kubernetescluster-example.yaml
   ```
4. **Step through code** when breakpoint hits
5. **Inspect variables** in Debug panel
6. **Evaluate expressions** in Debug Console

### Hot Reload During Development

Code changes are reflected immediately since source is mounted as volume:

```bash
# After editing code, restart container to apply changes
docker-compose restart nico

# Re-attach debugger in VSCode (F5)
```

### Useful Debugging Commands

```bash
# View NICO operator logs
docker-compose logs -f nico

# Check KubernetesCluster resources
kubectl get kubernetesclusters -A -o wide

# Check created NixosConfigurations
kubectl get nixosconfigurations -A

# Describe cluster for detailed status
kubectl describe kubernetescluster <cluster-name>

# View operator events
kubectl get events --field-selector involvedObject.kind=KubernetesCluster

# Check generated kubeconfig Secret
kubectl get secret <cluster-name>-kubeconfig -o yaml
```

### Debug Console Commands

While debugging in VSCode, try these in Debug Console:

```python
# Inspect cluster spec
spec['controlPlane']['count']

# View selected machines
[m['metadata']['name'] for m in machines]

# Check cluster phase
status.get('phase', 'Unknown')

# View generated cluster config
cluster_config
```

## 📋 VS Code Tasks

Available tasks (Terminal → Run Task):

- **docker-compose-up** - Start NICO container with debugger
- **docker-compose-down** - Stop all containers
- **docker-compose-logs** - View NICO logs in real-time
- **docker-compose-restart** - Restart NICO container

**Quick shortcuts:**
- `Ctrl+Shift+P` → "Tasks: Run Task" → Select task
- Tasks run in VSCode integrated terminal

## 🔍 Monitoring

### Prometheus Metrics

NICO exposes Prometheus metrics on port 8080:

```bash
# Port-forward metrics endpoint
kubectl port-forward -n nico-operator-system svc/nico-operator-metrics 8080:8080

# View metrics
curl http://localhost:8080/metrics

# Or from container
docker-compose exec nico curl localhost:8080/metrics
```

**Key metrics:**
- `nico_clusters_total` - Total clusters managed
- `nico_clusters_by_phase` - Clusters grouped by phase
- `nico_cluster_control_plane_nodes` - Control plane node count
- `nico_cluster_worker_nodes` - Worker node count
- `nico_cluster_reconcile_duration_seconds` - Reconciliation duration

### Real-time Monitoring

```bash
# Watch NICO operator logs with color
docker-compose logs -f nico | grep --color -E "ERROR|WARNING|INFO|$"

# Watch KubernetesCluster resources
kubectl get kubernetesclusters -A -w

# Watch all NICO-related resources
kubectl get kubernetesclusters,nixosconfigurations -A -w

# Monitor events
kubectl get events -A --watch --field-selector involvedObject.kind=KubernetesCluster

# Check cluster status in real-time
watch -n 2 "kubectl get kubernetesclusters -A -o wide"
```

## 🛠️ Troubleshooting

### Kind Cluster Issues

**Issue:** `kind-setup.sh` fails with "kind not found"

**Solution:**
```bash
# Install kind manually
curl -Lo ./kind https://kind.sigs.k8s.io/dl/v0.20.0/kind-$(uname -s | tr '[:upper:]' '[:lower:]')-amd64
chmod +x ./kind
sudo mv ./kind /usr/local/bin/kind
```

**Issue:** Cluster already exists

**Solution:**
```bash
# Delete existing cluster
kind delete cluster --name nico-dev

# Recreate
./kind-setup.sh
```

### Debugger Issues

**Issue:** VSCode debugger won't connect

**Solutions:**
1. Check container is running:
   ```bash
   docker ps | grep nico-dev
   ```

2. Check debugpy is listening:
   ```bash
   docker-compose logs nico | grep debugpy
   # Should show: "Waiting for debugger to attach on 0.0.0.0:5678"
   ```

3. Check port is not occupied:
   ```bash
   lsof -i :5678
   # If occupied, kill the process or change port
   ```

4. Restart container and retry:
   ```bash
   docker-compose restart nico
   # Then F5 in VSCode
   ```

**Issue:** Breakpoints show as "unverified" (hollow circles)

**Solutions:**
- Ensure `pathMappings` in `launch.json` is correct
- Verify source code is mounted: `docker-compose exec nico ls /app`
- Set `justMyCode: false` in debug configuration
- Restart debugger after code changes

### KUBECONFIG Issues

**Issue:** Operator can't connect to Kubernetes

**Solutions:**
1. Verify KUBECONFIG is exported:
   ```bash
   echo $KUBECONFIG
   # Should be: /Users/<username>/.kube/nico-dev.kubeconfig
   ```

2. Test cluster access:
   ```bash
   kubectl get nodes
   ```

3. Check kubeconfig is mounted in container:
   ```bash
   docker-compose exec nico cat ~/.kube/config
   ```

4. Recreate kubeconfig:
   ```bash
   kind export kubeconfig --name nico-dev --kubeconfig ~/.kube/nico-dev.kubeconfig
   ```

### CRD Issues

**Issue:** CRDs not found

**Solutions:**
```bash
# Verify CRDs are installed
kubectl get crds | grep nico

# Reinstall CRDs
kubectl apply -f crds/

# Check CRD definition
kubectl get crd kubernetesclusters.nico.homystack.com -o yaml
```

**Issue:** CRD validation errors

**Solutions:**
- Check example manifests: `kubectl apply -f examples/ --dry-run=client`
- Validate against schema: `kubectl explain kubernetescluster.spec`
- Review operator logs for detailed errors

### Cluster Reconciliation Issues

**Issue:** KubernetesCluster stuck in "Provisioning" phase

**Debug steps:**
```bash
# 1. Check cluster status
kubectl describe kubernetescluster <name>

# 2. Check if NixosConfigurations were created
kubectl get nixosconfigurations -l nico.homystack.com/cluster=<cluster-name>

# 3. Check if machines are discoverable
kubectl get machines -o json | jq '.items[] | {name: .metadata.name, discoverable: .status.discoverable}'

# 4. Check operator logs
docker-compose logs nico | grep -i error

# 5. Check events
kubectl get events --field-selector involvedObject.name=<cluster-name>
```

**Issue:** Kubeconfig not generated

**Solutions:**
- Ensure control plane NixosConfigurations are Ready
- Check SSH connectivity to control plane machines
- Verify kubeconfig path in cluster spec
- Check operator has permissions to create Secrets

## 🏗️ Project Structure

```
NICO/
├── main.py                          # Operator entry point, kopf handlers
├── kubernetescluster_handlers.py    # KubernetesCluster reconciliation logic
├── clients.py                       # Kubernetes API client wrappers
├── utils.py                         # Git operations, flake parsing, hashing
├── events.py                        # Event handling utilities
├── metrics.py                       # Prometheus metrics definitions
│
├── Dockerfile                       # Production Docker image
├── Dockerfile.dev                   # Development Docker image with debugpy
├── docker-compose.yml               # Multi-service dev environment
├── kind-setup.sh                    # Automated Kind cluster setup
│
├── requirements.txt                 # Production dependencies
├── requirements-dev.txt             # Development dependencies (debugpy, linters)
│
├── crds/                            # Custom Resource Definitions
│   └── kubernetescluster.yaml       # KubernetesCluster CRD
│
├── examples/                        # Example manifests
│   └── kubernetescluster-example.yaml
│
├── .vscode/                         # VS Code configuration
│   ├── launch.json                  # Debug configurations
│   └── tasks.json                   # Automated tasks
│
├── CLAUDE.md                        # Instructions for Claude Code
├── DEVELOPMENT.md                   # This file
├── DESIGN.md                        # PRD and architectural decisions
├── USAGE.md                         # Usage guide and examples
└── README.md                        # Project overview
```

**Key files for debugging:**
- `main.py:1` - Entry point, registers kopf handlers
- `kubernetescluster_handlers.py:45` - Main reconciliation function
- `clients.py:1` - All Kubernetes API interactions
- `.vscode/launch.json:6` - VSCode debug configurations

## 🔄 Development Workflow

### 1. Initial Setup
```bash
# Clone the repository
git clone <repository-url>
cd NICO

# Create Kind cluster and apply CRDs
./kind-setup.sh

# Export kubeconfig
export KUBECONFIG=~/.kube/nico-dev.kubeconfig

# Install development dependencies
pip install -r requirements-dev.txt
```

### 2. Start Development Environment
```bash
# Start NICO operator in debug mode
docker-compose up -d nico

# Attach VSCode debugger (F5 → "NICO: Attach to Running Container")

# View logs in separate terminal
docker-compose logs -f nico
```

### 3. Make Code Changes
1. **Edit Python files** - Changes are reflected immediately (mounted as volume)
2. **Set breakpoints** in VSCode
3. **Trigger reconciliation:**
   ```bash
   kubectl apply -f examples/kubernetescluster-example.yaml
   ```
4. **Step through code** when breakpoint hits
5. **Restart container** after major changes:
   ```bash
   docker-compose restart nico
   # Re-attach debugger (F5)
   ```

### 4. Test Changes

```bash
# Apply test KubernetesCluster
kubectl apply -f examples/kubernetescluster-example.yaml

# Watch cluster provisioning
kubectl get kubernetesclusters -w

# Check created NixosConfigurations
kubectl get nixosconfigurations -l nico.homystack.com/cluster=test-cluster

# Verify kubeconfig Secret created
kubectl get secret test-cluster-kubeconfig

# Clean up
kubectl delete kubernetescluster test-cluster
```

### 5. Update CRDs

If you change the KubernetesCluster API:

```bash
# Edit CRD
vim crds/kubernetescluster.yaml

# Apply changes
kubectl apply -f crds/kubernetescluster.yaml

# Verify
kubectl explain kubernetescluster.spec
```

### 6. Code Quality

```bash
# Run linters
black .
isort .
flake8 .
pylint *.py

# Type checking
mypy main.py kubernetescluster_handlers.py clients.py

# Run all checks
black . && isort . && flake8 . && mypy *.py
```

## 🧪 Testing

### Manual Testing

```bash
# Create test cluster
kubectl apply -f examples/kubernetescluster-example.yaml

# Verify phases: Provisioning → Ready
kubectl get kubernetescluster test-cluster -w

# Check created resources
kubectl get nixosconfigurations,secrets -l nico.homystack.com/cluster=test-cluster

# Test deletion
kubectl delete kubernetescluster test-cluster

# Verify cleanup (NixosConfigurations should be deleted)
kubectl get nixosconfigurations -l nico.homystack.com/cluster=test-cluster
```

### Unit Tests

```bash
# Run tests (when implemented)
pytest tests/

# With coverage
pytest --cov=. --cov-report=html tests/

# Specific test file
pytest tests/test_handlers.py -v
```

### Integration Tests

```bash
# Test full cluster lifecycle
kubectl apply -f examples/kubernetescluster-example.yaml
kubectl wait --for=jsonpath='{.status.phase}'=Ready kubernetescluster/test-cluster --timeout=10m
kubectl delete kubernetescluster test-cluster
```

## 📝 Code Style

NICO follows standard Python conventions:

- **PEP 8** for code style
- **Type hints** for all function signatures
- **Docstrings** for public functions and classes
- **Black** for formatting (line length: 100)
- **isort** for import sorting
- **flake8** for linting
- **mypy** for static type checking

**Pre-commit checks:**
```bash
# Format code
black --line-length 100 .

# Sort imports
isort .

# Check style
flake8 --max-line-length 100 .

# Type check
mypy --ignore-missing-imports *.py
```

## 🔧 Dependencies

### Runtime Dependencies (requirements.txt)
- **kopf** (>=1.36.0) - Kubernetes operator framework
- **kubernetes** (>=26.1.0) - Kubernetes Python client
- **gitpython** (>=3.1.0) - Git repository operations
- **pyyaml** (>=6.0) - YAML parsing
- **prometheus-client** (>=0.19.0) - Metrics exposition

### Development Dependencies (requirements-dev.txt)
- **debugpy** (>=1.8.0) - Remote debugging
- **pytest** suite - Testing framework
- **black**, **isort**, **flake8** - Code formatting and linting
- **pylint**, **mypy** - Static analysis

**Install commands:**
```bash
# Production dependencies only
pip install -r requirements.txt

# Development dependencies (includes production)
pip install -r requirements-dev.txt
```

## 🚀 Deployment

### Development Deployment (Docker Compose)
```bash
# Start all services
docker-compose up -d

# Stop services
docker-compose down

# Rebuild after Dockerfile changes
docker-compose build
docker-compose up -d
```

### Production Deployment (Kubernetes)
```bash
# Build and push production image
docker build -t ghcr.io/homystack/nico:latest .
docker push ghcr.io/homystack/nico:latest

# Apply CRDs
kubectl apply -f crds/

# Deploy operator
kubectl apply -f deployment.yaml

# Verify deployment
kubectl get pods -n nico-operator-system
kubectl logs -f deployment/nico-operator -n nico-operator-system
```

### Local Testing (No Container)
```bash
# Ensure KUBECONFIG is set
export KUBECONFIG=~/.kube/nico-dev.kubeconfig

# Run operator directly
python main.py

# Or with debugpy for remote debugging
python -m debugpy --listen 0.0.0.0:5678 main.py
```

## 📚 Additional Resources

- [Kopf Documentation](https://kopf.readthedocs.io/)
- [Kubernetes Operators](https://kubernetes.io/docs/concepts/extend-kubernetes/operator/)
- [NixOS Documentation](https://nixos.org/learn/)
- [Kind Documentation](https://kind.sigs.k8s.io/)
