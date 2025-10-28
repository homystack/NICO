# NICO Usage Guide

Complete usage instructions and examples for the NixOS Infrastructure Control Operator.

## Table of Contents

- [Quick Start](#quick-start)
- [Machine Management](#machine-management)
- [Configuration Management](#configuration-management)
- [Kubernetes Cluster Management](#kubernetes-cluster-management)
- [Advanced Features](#advanced-features)
- [Troubleshooting](#troubleshooting)

## Quick Start

### Prerequisites

- Kubernetes cluster (v1.20+)
- Kubectl configured with cluster access
- Target machines accessible via SSH
- Git repository with NixOS configurations

### Installation

```bash
# Apply Custom Resource Definitions
kubectl apply -f crds/

# Deploy the operator
kubectl apply -f deployment.yaml

# Verify operator is running
kubectl get pods -l app=nico-operator
```

### Basic Workflow

1. **Create SSH Key Secret**
```bash
kubectl create secret generic machine-ssh-key \
  --from-file=ssh-privatekey=~/.ssh/id_rsa \
  --namespace=default
```

2. **Create Machine Resource**
```bash
kubectl apply -f examples/machine-example.yaml
```

3. **Apply NixOS Configuration**
```bash
kubectl apply -f examples/nixosconfiguration-example.yaml
```

4. **Create Kubernetes Cluster (Optional)**
```bash
kubectl apply -f examples/kubernetescluster-example.yaml
```

## Machine Management

### Machine Resource

The `Machine` resource represents a physical or virtual machine that can be managed by NICO.

#### Example Machine Definition

```yaml
apiVersion: nio.homystack.com/v1alpha1
kind: Machine
metadata:
  name: worker-01
  namespace: default
spec:
  hostname: worker-01.local
  ipAddress: 192.168.1.100
  sshUser: root
  sshKeySecretRef:
    name: machine-ssh-key
    namespace: default
  labels:
    role: worker
    environment: production
```

#### Machine Status

Check machine status:
```bash
kubectl get machine worker-01 -o yaml
```

Expected status:
```yaml
status:
  discoverable: true
  hasConfiguration: true
  appliedConfiguration: "worker-config"
  appliedCommit: "a1b2c3d4e5f6..."
  lastAppliedTime: "2025-01-21T08:30:00Z"
```

## Configuration Management

### NixosConfiguration Resource

The `NixosConfiguration` resource defines NixOS configurations to be applied to machines.

#### Example Configuration

```yaml
apiVersion: nio.homystack.com/v1alpha1
kind: NixosConfiguration
metadata:
  name: worker-config
  namespace: default
spec:
  gitRepo: "https://github.com/your-org/nixos-configs.git"
  flake: ".#worker"
  configurationSubdir: "nix"
  fullInstall: false
  machineRef:
    name: worker-01
  credentialsRef:
    name: git-credentials
  additionalFiles:
    - path: "secrets/database-password"
      value:
        secretRef:
          name: db-secret
    - path: "config/custom.nix"
      value:
        inline: |
          { config, pkgs, ... }:
          {
            services.postgresql.enable = true;
          }
```

#### Configuration Modes

1. **Full Installation** (`fullInstall: true`):
   - Uses `nixos-anywhere --kexec`
   - Complete OS reinstallation
   - Suitable for initial setup

2. **Update Mode** (`fullInstall: false`):
   - Uses `nixos-rebuild switch --flake`
   - Updates existing system
   - Preserves data and state

#### Configuration Status

Check configuration status:
```bash
kubectl get nixosconfiguration worker-config -o yaml
```

## Kubernetes Cluster Management

### KubernetesCluster Resource

The `KubernetesCluster` resource manages complete Kubernetes clusters with control plane and worker nodes.

#### Example Cluster Definition

```yaml
apiVersion: nico.homystack.com/v1alpha1
kind: KubernetesCluster
metadata:
  name: production-cluster
  namespace: default
spec:
  gitRepo: "https://github.com/your-org/kubernetes-configs.git"
  configurationSubdir: "clusters/production"
  controlPlane:
    machineSelector:
      matchLabels:
        role: control-plane
    count: 3
  dataPlane:
    machineSelector:
      matchLabels:
        role: worker
    count: 5
  credentialsRef:
    name: git-credentials
```

#### Cluster Status

Check cluster status:
```bash
kubectl get kubernetescluster production-cluster -o yaml
```

Expected status:
```yaml
status:
  phase: "Ready"
  controlPlaneReady: "3/3"
  dataPlaneReady: "5/5"
  kubeconfigSecret: "production-cluster-kubeconfig"
  conditions:
    - type: "ControlPlaneReady"
      status: "True"
      lastTransitionTime: "2025-01-21T08:30:00Z"
```

## Advanced Features

### Additional Files

Inject additional files into the configuration:

```yaml
additionalFiles:
  # From Kubernetes secret
  - path: "secrets/api-key"
    value:
      secretRef:
        name: api-secret
        key: api-key
  
  # Inline Nix configuration
  - path: "config/network.nix"
    value:
      inline: |
        { config, pkgs, ... }:
        {
          networking.hostName = "server-01";
          networking.firewall.enable = true;
        }
  
  # From NixOS facter
  - path: "facts/system-info"
    value:
      nixosFacter: true
```

### Removal Configuration

Define cleanup configuration for resource deletion:

```yaml
spec:
  onRemoveFlake: "hosts/minimal.nix"
```

### Git Credentials

For private repositories, create a secret:

```bash
kubectl create secret generic git-credentials \
  --from-literal=token=your-github-token \
  --namespace=default
```

## Monitoring and Debugging

### Check Operator Logs

```bash
kubectl logs -l app=nico-operator -f
```

### Monitor Events

```bash
kubectl get events --field-selector involvedObject.kind=NixosConfiguration
kubectl get events --field-selector involvedObject.kind=KubernetesCluster
```

### Verify SSH Connectivity

```bash
# Test SSH connection manually
ssh -i ~/.ssh/id_rsa root@192.168.1.100 "hostname"
```

### Check Applied Configurations

```bash
# List all applied configurations
kubectl get machines -o custom-columns=NAME:.metadata.name,CONFIG:.status.appliedConfiguration,COMMIT:.status.appliedCommit

# Check specific machine
kubectl describe machine worker-01
```

## Troubleshooting

### Common Issues

#### Machine Not Discoverable

**Symptoms:**
- Machine status shows `discoverable: false`
- SSH connection failures

**Solutions:**
- Verify network connectivity
- Check SSH key configuration
- Ensure SSH service is running on target machine
- Verify SSH user permissions

#### Configuration Not Applied

**Symptoms:**
- Configuration status shows errors
- No commit hash recorded

**Solutions:**
- Check Git repository accessibility
- Verify flake path correctness
- Review operator logs for specific errors
- Check disk space on target machine

#### Cluster Provisioning Failed

**Symptoms:**
- Cluster phase stuck in "Provisioning"
- Control plane nodes not ready

**Solutions:**
- Check machine resources (CPU, memory)
- Verify network connectivity between nodes
- Review Kubernetes component logs
- Check etcd cluster health

### Debugging Commands

```bash
# Get detailed resource information
kubectl describe nixosconfiguration <name>
kubectl describe kubernetescluster <name>

# Check operator pod status
kubectl get pods -l app=nico-operator

# View operator logs with timestamps
kubectl logs -l app=nico-operator --tail=100 --timestamps

# Check events for specific resource
kubectl get events --field-selector involvedObject.name=<resource-name>
```

### Performance Optimization

1. **Use Git Tags**: For production, use specific Git tags instead of branches
2. **Optimize Flakes**: Keep flake configurations minimal and focused
3. **Monitor Resources**: Ensure target machines have adequate resources
4. **Batch Operations**: Apply configurations during maintenance windows

## Best Practices

### Security

- Use dedicated SSH keys for operator access
- Store sensitive data in Kubernetes secrets
- Limit SSH user permissions to necessary commands
- Regularly rotate credentials

### Reliability

- Use Git tags for production configurations
- Implement health checks for critical services
- Monitor applied commit hashes
- Test configurations in staging first

### Maintenance

- Regularly update NixOS channels
- Monitor disk usage on target machines
- Keep operator and dependencies updated
- Maintain backup procedures

### GitOps Workflow

1. **Development**: Make changes in feature branches
2. **Testing**: Apply to test machines first
3. **Review**: Create pull requests for changes
4. **Production**: Merge to main and apply tags
5. **Monitoring**: Watch applied commit status

## Examples Directory

The [examples/](examples/) directory contains:

- `machine-example.yaml` - Basic machine definition
- `nixosconfiguration-example.yaml` - Configuration application
- `kubernetescluster-example.yaml` - Complete cluster setup
- Various NixOS configuration examples

## Next Steps

- Review the [Configuration Reference](configuration.md) for detailed options
- Check the [Development Guide](DEVELOPMENT.md) for debugging and development
- Explore the Nix configurations in the [nix/](nix/) directory
