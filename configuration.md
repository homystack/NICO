# NICO Configuration Reference

Complete configuration reference for the KubernetesCluster Custom Resource Definition (CRD) in the NixOS Infrastructure Cluster Orchestrator.

## Table of Contents

- [KubernetesCluster Resource](#kubernetescluster-resource)
- [Common Patterns](#common-patterns)
- [Best Practices](#best-practices)

## KubernetesCluster Resource

The `KubernetesCluster` resource manages complete Kubernetes clusters with control plane and worker nodes.

### API Version
- **Group**: `nico.homystack.com`
- **Version**: `v1alpha1`
- **Kind**: `KubernetesCluster`

### Full Specification

```yaml
apiVersion: nico.homystack.com/v1alpha1
kind: KubernetesCluster
metadata:
  name: string                  # Required: Unique cluster name
  namespace: string             # Required: Kubernetes namespace
spec:
  gitRepo: string               # Required: Git repository URL with cluster configs
  configurationSubdir: string   # Optional: Subdirectory for cluster configurations
  controlPlane:                 # Required: Control plane configuration
    machines:                   # Option A: Explicit machine list
      - string                  # Machine names
    machineSelector:            # Option B: Label selector
      matchLabels:              # Label matching criteria
        key: value
    count: integer              # Option C: Number of machines to select
  dataPlane:                    # Required: Worker node configuration
    machines:                   # Option A: Explicit machine list
      - string                  # Machine names
    machineSelector:            # Option B: Label selector
      matchLabels:              # Label matching criteria
        key: value
    count: integer              # Option C: Number of machines to select
  credentialsRef:               # Optional: Git credentials secret
    name: string                # Required: Secret name
    namespace: string           # Optional: Secret namespace
```

### Status Fields

```yaml
status:
  phase: string                 # "Provisioning", "Ready", "Failed", "Deleting"
  controlPlaneReady: string     # Ready control plane nodes (e.g., "3/3")
  dataPlaneReady: string        # Ready worker nodes (e.g., "5/5")
  kubeconfigSecret: string      # Name of secret containing kubeconfig
  appliedMachines:              # Map of machine to configuration
    machine-name: config-name   # Machine name to NixosConfiguration mapping
  conditions:                   # Detailed conditions
    - type: string              # Condition type
      status: string            # "True", "False", or "Unknown"
      lastTransitionTime: string
      reason: string
      message: string
```

### Example

```yaml
apiVersion: nico.homystack.com/v1alpha1
kind: KubernetesCluster
metadata:
  name: production-k8s
  namespace: production
spec:
  gitRepo: "https://github.com/company/kubernetes-configs.git"
  configurationSubdir: "clusters/production"
  controlPlane:
    machineSelector:
      matchLabels:
        role: control-plane
        environment: production
    count: 3
  dataPlane:
    machineSelector:
      matchLabels:
        role: worker
        environment: production
    count: 10
  credentialsRef:
    name: git-credentials
```

## Common Patterns

### Machine Selection Patterns

#### Explicit Machine List
```yaml
controlPlane:
  machines:
    - cp-01
    - cp-02
    - cp-03
```

#### Label-Based Selection
```yaml
dataPlane:
  machineSelector:
    matchLabels:
      role: worker
      environment: staging
  count: 5
```

#### Mixed Selection
```yaml
controlPlane:
  machines: [cp-01, cp-02]  # Always include these
  machineSelector:
    matchLabels:
      role: control-plane
  count: 3                  # Ensure at least 3 total
```

### Git Repository Patterns

#### Public Repository
```yaml
gitRepo: "https://github.com/nixos/nixpkgs.git"
```

#### Private Repository with Token
```yaml
gitRepo: "https://github.com/company/private-configs.git"
credentialsRef:
  name: github-token
```

#### Specific Branch or Tag
```yaml
gitRepo: "https://github.com/company/configs.git?ref=production"
```

## Best Practices

### Naming Conventions

- **Clusters**: Include environment and purpose (`production-k8s`, `staging-cluster`)

### Labeling Strategy

```yaml
# Machine labels example for cluster nodes
labels:
  role: control-plane          # or "worker"
  environment: production      # Environment
  datacenter: us-east-1       # Location
  team: platform-engineering  # Owning team
```

### Security Configuration

#### Git Credentials
```yaml
# Use fine-grained tokens with minimal permissions
credentialsRef:
  name: github-deploy-token
  namespace: git-secrets
```

### Resource Organization

#### Namespace Strategy
- **Development**: `dev`, `staging`
- **Production**: `production`, `prod-backup`
- **Infrastructure**: `nico-system`, `monitoring`

#### Configuration Hierarchy
```
kubernetes-configs/
├── clusters/                 # Kubernetes cluster configurations
│   ├── production/
│   └── staging/
└── modules/                 # Reusable Kubernetes modules
```

### Performance Optimization

#### Configuration Caching
```yaml
# Use specific Git commits for production
gitRepo: "https://github.com/company/configs.git?rev=abc123def456"
```

### Monitoring Configuration

#### Status Monitoring
```bash
# Watch cluster resources
kubectl get kubernetesclusters --all-namespaces -w

# Check cluster status
kubectl get kubernetescluster production-k8s -o jsonpath='{.status.phase}'
```

#### Alerting Conditions
- Cluster `phase` stuck in "Provisioning" for extended period
- `controlPlaneReady` less than required count
- `dataPlaneReady` less than expected count

## Field Reference Tables

### KubernetesCluster Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `spec.gitRepo` | string | Yes | Git repository URL |
| `spec.controlPlane` | object | Yes | Control plane configuration |
| `spec.dataPlane` | object | Yes | Worker node configuration |
| `spec.credentialsRef` | object | No | Git credentials |

### Control Plane Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `machines` | array | No | Explicit machine names |
| `machineSelector` | object | No | Label selector for machines |
| `count` | integer | No | Number of machines to select |

### Data Plane Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `machines` | array | No | Explicit machine names |
| `machineSelector` | object | No | Label selector for machines |
| `count` | integer | No | Number of machines to select |

## Validation Rules

### KubernetesCluster Validation
- `controlPlane.count` must be at least 1
- `dataPlane.count` must be at least 0
- At least one selection method must be provided for each plane
- `gitRepo` must be a valid URL

## Related Documentation

- [Usage Guide](usage.md) - Practical usage examples and workflows
- [Development Guide](DEVELOPMENT.md) - Development and debugging information
- [Kubernetes CRDs](https://kubernetes.io/docs/tasks/extend-kubernetes/custom-resources/custom-resource-definitions/) - Custom Resource Definition concepts
