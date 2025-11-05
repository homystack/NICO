# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

NICO (NixOS Infrastructure Cluster Orchestrator) is a Kubernetes operator written in Python that manages Kubernetes cluster lifecycle on bare-metal NixOS machines. It builds on top of NIO (NixOS Infrastructure Operator) which handles individual machine management.

**Key Concept**: NICO orchestrates Kubernetes clusters by creating `NixosConfiguration` resources for each machine. The actual Kubernetes distribution (k3s, k0s, kubeadm) is defined entirely in Git-based Nix flakes - NICO acts as a coordinator, not an installer.

## Architecture

### Three-Level Management Hierarchy

1. **Machine Level** (NIO): Individual machines with SSH connectivity
2. **Configuration Level** (NIO): NixOS configurations applied via Git flakes
3. **Cluster Level** (NICO): Complete Kubernetes clusters provisioned across multiple machines

### Core Components

- `main.py` - Operator entry point, registers kopf handlers for KubernetesCluster CRD
- `kubernetescluster_handlers.py` - Main reconciliation logic for cluster lifecycle
- `clients.py` - Kubernetes API client wrapper (CoreV1, CustomObjects)
- `utils.py` - Git operations, flake parsing, and directory hashing utilities
- `events.py` - Event handling utilities

### Custom Resource Definitions (CRDs)

The operator manages `KubernetesCluster` resources (`nico.homystack.com/v1alpha1`):
- Selects machines via explicit list OR label selector + count
- Creates per-machine `NixosConfiguration` resources with generated cluster context
- Tracks cluster phase: Provisioning → Ready → Failed → Deleting
- Generates kubeconfig Secret when control plane is ready

### Key Workflows

**Cluster Creation**:
1. Select control plane and worker machines based on spec
2. Generate `cluster.nix` with all node IPs and roles
3. Create `NixosConfiguration` for each machine with:
   - Git repo + flake reference (e.g., `#machine-name`)
   - Inline `cluster.nix` as additionalFile
   - SSH keys and join tokens as Secrets
   - **ownerReference** to KubernetesCluster for cascade deletion
   - Labels: `nico.homystack.com/cluster` and `nico.homystack.com/role`
   - `onRemoveFlake: "#minimal"` for cleanup
4. Wait for all configs to reach Ready status
5. Extract kubeconfig via SSH and create Secret (distribution-agnostic)
6. Update Prometheus metrics continuously

**Machine Selection Priority**:
1. Explicit `machines: [...]` list (highest priority)
2. `machineSelector + count` (selects machines with `hasConfiguration: false`)
3. Empty list if neither specified

**Deletion**:
- All `NixosConfiguration` resources have `ownerReference` to KubernetesCluster
- Deletion cascades automatically, machines revert to available state

## Development Commands

### Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Run operator locally (requires KUBECONFIG or in-cluster config)
python main.py
```

### Docker Compose Development

```bash
# Start complete dev environment with Kind cluster
docker-compose up -d

# View operator logs
docker-compose logs -f nixos-operator-dev

# Stop environment
docker-compose down
```

### Testing with Kind

```bash
# Create Kind cluster and deploy operator
./kind-setup.sh

# Apply CRDs
kubectl apply -f crds/

# Deploy operator
kubectl apply -f deployment.yaml

# Test with examples
kubectl apply -f examples/kubernetescluster-example.yaml
```

### Debugging

```bash
# Watch operator logs
kubectl logs -f deployment/nixos-operator -n nixos-operator-system

# Check cluster status
kubectl get kubernetesclusters -A
kubectl describe kubernetescluster <name>

# Monitor related resources
kubectl get machines,nixosconfigurations -A

# View events
kubectl get events --field-selector involvedObject.kind=KubernetesCluster
```

### Build and Deploy

```bash
# Build Docker image
docker build -t nixos-operator:latest .

# Update running deployment
kubectl rollout restart deployment/nixos-operator -n nixos-operator-system
```

## Code Architecture Details

### Kubernetes Client Setup (`clients.py`)

The client initialization tries kubeconfig first, then falls back to in-cluster config. All client functions are async-compatible and use the global `custom_objects_api` and `core_v1` clients.

Key functions:
- `get_machine()`, `list_machines()` - Query Machine resources
- `create_nixos_configuration()`, `delete_nixos_configuration()` - Manage NixosConfiguration resources
- `get_secret_data()`, `create_secret()` - Handle Secrets (kubeconfig, SSH keys)
- `update_cluster_status()` - Patch KubernetesCluster status subresource

### Cluster Reconciliation (`kubernetescluster_handlers.py`)

**`reconcile_kubernetes_cluster()`** - Unified handler for create/update/resume/delete:
- Validates machine references exist and are discoverable
- Generates `cluster.nix` with all node IPs and roles
- Creates `NixosConfiguration` per machine with proper `ownerReference`
- Handles deletion by removing all owned resources

**`select_machines_for_cluster()`** - Implements priority-based machine selection:
1. Use explicit `machines` list if provided
2. Otherwise query machines by `machineSelector` labels
3. Filter to only machines with `hasConfiguration: false`
4. Return up to `count` machines

**`generate_cluster_config()`** - Creates Nix expression with:
```nix
{
  clusterName = "production-k8s";
  controlPlane = [
    { name = "cp-01"; ip = "192.168.1.10"; }
    { name = "cp-02"; ip = "192.168.1.11"; }
  ];
  workers = [
    { name = "worker-01"; ip = "192.168.1.20"; }
  ];
}
```

### Git and Flake Utilities (`utils.py`)

- `clone_git_repo()` - Clones repo to predictable path, supports credentials
- `get_workdir_path()` - Generates deterministic working directory based on namespace/name/commit
- `parse_flake_reference()` - Parses `github:owner/repo#output` format
- `calculate_directory_hash()` - SHA256 of directory contents for change detection
- `extract_repo_name_from_url()` - Normalizes Git URLs to `owner/repo` format

### Dependencies

Core Python packages (see `requirements.txt`):
- `kopf>=1.36.0` - Kubernetes operator framework (handles watches, events, retries)
- `kubernetes>=26.1.0` - Official Kubernetes Python client
- `gitpython>=3.1.0` - Git repository operations
- `pyyaml>=6.0` - YAML parsing
- `prometheus-client>=0.19.0` - Prometheus metrics exposition

Development dependencies (see `requirements-dev.txt`):
- `pytest` suite for unit/integration testing
- `black`, `isort`, `flake8` for code formatting and linting
- `pylint`, `mypy` for static analysis

## Important Implementation Notes

### NixosConfiguration Generation

When NICO creates a NixosConfiguration, it includes:
- `flake: "#<machine-name>"` - Machine-specific flake output
- `onRemoveFlake: "#minimal"` - Reverts to minimal config on deletion
- `additionalFiles` with inline `cluster.nix` containing all cluster topology
- `machineRef` pointing to the target Machine resource
- `ownerReference` to KubernetesCluster for cascade deletion

### State Management

NICO is stateless - all state lives in Kubernetes resources:
- Cluster status tracks phase and ready counts
- `appliedMachines` map shows which NixosConfiguration owns each machine
- Machines track `hasConfiguration` to prevent double-assignment
- kopf framework handles retries and conflict resolution

### Rolling Updates

(Not yet fully implemented) - Should update workers first, then control plane while maintaining quorum. Triggered by changes to:
- `gitRepo` or `configurationSubdir`
- Machine lists or selectors
- `credentialsRef`

## Common Development Tasks

### Adding a New CRD Field

1. Update `crds/kubernetescluster.yaml` OpenAPI schema
2. Apply CRD: `kubectl apply -f crds/kubernetescluster.yaml`
3. Update `kubernetescluster_handlers.py` to handle new field
4. Update examples and documentation

### Debugging Cluster Provisioning

Check in order:
1. KubernetesCluster status and conditions
2. Machine resources are discoverable (`status.discoverable: true`)
3. NixosConfiguration resources exist and have correct specs
4. NixosConfiguration status shows applied commit hash
5. Machine status shows `hasConfiguration: true`

### Testing Machine Selection Logic

```python
# In kubernetescluster_handlers.py:select_machines_for_cluster()
# Add logging to see selection process:
logger.info(f"Selector: {machine_selector}, Available: {len(machines)}, Selected: {len(selected_machines)}")
```

### Working with Secrets

SSH keys and join tokens are stored as Kubernetes Secrets. When referencing in NixosConfiguration `additionalFiles`:
```yaml
additionalFiles:
  - path: "flake-ssh-private-key"
    valueType: SecretRef
    secretRef:
      name: ssh-key-secret
```

## Flake Repository Requirements

The Git repository specified in `KubernetesCluster.spec.gitRepo` must:
1. Contain a `flake.nix` in the root or `configurationSubdir`
2. Export outputs for each machine name: `#machine-01`, `#machine-02`, etc.
3. Import the generated `cluster.nix` to access cluster topology
4. Implement the actual Kubernetes setup (k3s/k0s/kubeadm) in Nix configurations

NICO does not know or care about the Kubernetes distribution - this is entirely handled by the flake.

## Monitoring and Observability

### Prometheus Metrics

NICO exposes comprehensive Prometheus metrics on port 8080 (configurable via `METRICS_PORT` env var).

**Metrics file**: `metrics.py` contains all metric definitions and helper functions.

**Key metrics**:
- Cluster lifecycle: `nico_clusters_total`, `nico_clusters_by_phase`
- Node tracking: `nico_cluster_control_plane_nodes`, `nico_cluster_worker_nodes`
- Operations: `nico_cluster_reconcile_duration_seconds`, `nico_cluster_reconcile_errors_total`
- Configurations: `nico_nixos_configs_created_total`, `nico_nixos_configs_deleted_total`
- Kubeconfig: `nico_kubeconfig_generation_success_total`

**Accessing metrics**:
```bash
kubectl port-forward -n nico-operator-system svc/nico-operator-metrics 8080:8080
curl http://localhost:8080/metrics
```

**Integration points**:
- `main.py` - Initializes metrics server on startup
- `kubernetescluster_handlers.py` - Records metrics during reconciliation
- `deployment.yaml` - Exposes metrics port, includes ServiceMonitor for prometheus-operator

## CI/CD Pipeline

GitHub Actions workflows in `.github/workflows/`:

**ci.yml** - Runs on every push/PR:
- Code linting (black, isort, flake8, pylint)
- Unit tests with pytest
- Kubernetes manifest validation with kubeval
- Docker image build
- Uploads build artifacts

**release.yml** - Runs on version tags (`v*.*.*`):
- Multi-arch Docker builds (amd64, arm64)
- Pushes to GitHub Container Registry
- Creates GitHub release with changelog
- Generates combined `install.yaml` manifest

**Creating a release**:
```bash
git tag v1.0.0
git push origin v1.0.0
# Workflow automatically builds and releases
```

## Documentation Structure

- `README.md` - High-level project overview and quick start
- `USAGE.md` - Complete usage guide with examples, troubleshooting, and behavior changes
- `DESIGN.md` - PRD and architectural decisions (KubernetesCluster CRD design)
- `DEVELOPMENT.md` - Development setup, debugging, VS Code configuration
- `configuration.md` - Detailed CRD field reference
- `examples/` - Working example manifests
- `crds/` - Custom Resource Definition YAML files
- `tests/` - Unit tests for handlers and metrics

## Related Projects

This operator builds on **NIO** (NixOS Infrastructure Operator), which provides the `Machine` and `NixosConfiguration` CRDs. NICO depends on NIO being deployed in the same cluster.
