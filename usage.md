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

The `Machine` resource represents physical or virtual machines managed by the [NIO (NixOS Infrastructure Operator)](https://github.com/homystack/nio). NICO uses Machine resources to provision Kubernetes cluster nodes.

**For detailed Machine management documentation, see the [NIO repository](https://github.com/homystack/nio).**

### Quick Example

```yaml
apiVersion: nio.homystack.com/v1alpha1
kind: Machine
metadata:
  name: worker-01
  labels:
    role: worker  # Used by NICO for machine selection
spec:
  hostname: worker-01.local
  ipAddress: 192.168.1.100
  sshUser: root
  sshKeySecretRef:
    name: machine-ssh-key
```

## Configuration Management

The `NixosConfiguration` resource defines NixOS configurations applied to machines. This is managed by the [NIO (NixOS Infrastructure Operator)](https://github.com/homystack/nio). NICO automatically creates NixosConfiguration resources for cluster nodes.

**For detailed NixosConfiguration documentation, see the [NIO repository](https://github.com/homystack/nio).**

### Quick Example

```yaml
apiVersion: nio.homystack.com/v1alpha1
kind: NixosConfiguration
metadata:
  name: worker-config
  labels:
    nico.homystack.com/cluster: "my-cluster"  # Added by NICO
    nico.homystack.com/role: "worker"         # Added by NICO
spec:
  gitRepo: "https://github.com/your-org/nixos-configs.git"
  flake: ".#worker-01"
  configurationSubdir: "nix"
  fullInstall: false
  machineRef:
    name: worker-01
  onRemoveFlake: "#minimal"  # Set by NICO for cleanup
```

**Note**: When using NICO for Kubernetes cluster management, you don't need to create NixosConfiguration resources manually - NICO creates them automatically based on your KubernetesCluster specification.

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
  phase: "Ready"  # Provisioning | ControlPlaneReady | Ready | Failed | Deleting
  controlPlaneReady: "3/3"
  dataPlaneReady: "5/5"
  kubeconfigSecret: "production-cluster-kubeconfig"
  appliedMachines:
    cp-01: "production-cluster-cp-01"
    cp-02: "production-cluster-cp-02"
    worker-01: "production-cluster-worker-01"
  conditions:
    - type: "Ready"
      status: "True"
      lastTransitionTime: "2025-01-21T08:30:00Z"
      reason: "AllNodesReady"
      message: "Control plane: 3/3, Workers: 5/5"
```

#### Cluster Phases

NICO tracks cluster lifecycle through the following phases:

1. **Provisioning**: Initial state when NixosConfiguration resources are being created
2. **ControlPlaneReady**: All control plane nodes are configured and ready
3. **Ready**: All nodes (control plane + workers) are configured and ready
4. **Failed**: Cluster provisioning encountered a permanent error
5. **Deleting**: Cluster is being deleted

#### Automatic Kubeconfig Generation

When the control plane reaches "Ready" state, NICO automatically creates a Secret containing the kubeconfig:

```bash
# Access kubeconfig
kubectl get secret production-cluster-kubeconfig -o jsonpath='{.data.kubeconfig}' | base64 -d > cluster-kubeconfig.yaml

# Use with kubectl
export KUBECONFIG=./cluster-kubeconfig.yaml
kubectl get nodes
```

**Kubeconfig Extraction**: NICO extracts kubeconfig from the first control plane node via SSH in a distribution-agnostic way:

1. **Tries standard locations** for different Kubernetes distributions:
   - `/etc/rancher/k3s/k3s.yaml` (k3s)
   - `/var/lib/k0s/pki/admin.conf` (k0s)
   - `/etc/kubernetes/admin.conf` (kubeadm)
   - `/root/.kube/config` (generic)
   - `/etc/kubernetes/kubeconfig` (generic)

2. **Fallback to kubectl**: If no file found, tries `kubectl config view --raw`

3. **SSH Authentication**: Uses the SSH key from `Machine.spec.sshKeySecretRef`

**Note**: Kubeconfig extraction happens automatically when control plane becomes ready. Check operator logs if extraction fails.

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

### Cascade Deletion

NICO implements automatic cascade deletion for cluster resources. When you delete a KubernetesCluster resource:

1. **All NixosConfiguration resources** created by NICO are automatically deleted (via ownerReference)
2. **Machines revert** to `hasConfiguration: false` and become available for reuse
3. **Cleanup configurations** are applied using `onRemoveFlake: "#minimal"`
4. **Secrets** (join-token, kubeconfig) are cleaned up

```bash
# Delete cluster - automatically cleans up all related resources
kubectl delete kubernetescluster production-cluster

# Verify machines are released
kubectl get machines -l role=control-plane -o jsonpath='{.items[*].status.hasConfiguration}'
# Should return: false false false
```

**Important**: The `onRemoveFlake` is set to `#minimal` by default, which should revert machines to a minimal NixOS configuration. Ensure your Git repository provides a `#minimal` flake output for cleanup.

### Removal Configuration

The cleanup configuration is automatically set for cluster resources:

```yaml
# Automatically added by NICO to each NixosConfiguration
spec:
  onRemoveFlake: "#minimal"  # Reverts to minimal config on deletion
```

You can customize the cleanup flake in your Git repository by providing a `#minimal` output in your `flake.nix`.

### Git Credentials

For private repositories, create a secret:

```bash
kubectl create secret generic git-credentials \
  --from-literal=token=your-github-token \
  --namespace=default
```

## Monitoring and Debugging

### Prometheus Metrics

NICO exposes comprehensive Prometheus metrics on port 8080 for monitoring operator health and cluster state.

#### Access Metrics

```bash
# Port forward to metrics endpoint
kubectl port-forward -n nico-operator-system svc/nico-operator-metrics 8080:8080

# View metrics
curl http://localhost:8080/metrics
```

#### Available Metrics

**Cluster Metrics:**
- `nico_clusters_total` - Total number of KubernetesCluster resources
- `nico_clusters_by_phase{namespace, phase}` - Clusters grouped by phase (Provisioning, Ready, etc.)
- `nico_cluster_control_plane_nodes{namespace, cluster, status}` - Control plane node counts (ready/total)
- `nico_cluster_worker_nodes{namespace, cluster, status}` - Worker node counts (ready/total)

**Operation Metrics:**
- `nico_cluster_reconcile_duration_seconds{namespace, cluster}` - Time spent reconciling clusters
- `nico_cluster_reconcile_success_total{namespace, cluster}` - Successful reconciliations
- `nico_cluster_reconcile_errors_total{namespace, cluster, error_type}` - Failed reconciliations

**Configuration Metrics:**
- `nico_nixos_configs_created_total{namespace, cluster, role}` - Created NixosConfigurations
- `nico_nixos_configs_deleted_total{namespace, cluster}` - Deleted NixosConfigurations
- `nico_kubeconfig_generation_success_total{namespace, cluster}` - Successful kubeconfig generations

**Machine Selection Metrics:**
- `nico_machine_selection_duration_seconds{namespace, cluster, role}` - Time to select machines
- `nico_machines_selected{namespace, cluster, role}` - Number of selected machines

#### Prometheus Configuration

If using prometheus-operator, the ServiceMonitor is automatically created:

```yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: nico-operator
  namespace: nico-operator-system
spec:
  selector:
    matchLabels:
      app: nico-operator
  endpoints:
  - port: metrics
    interval: 30s
```

#### Example PromQL Queries

```promql
# Clusters not in Ready state
nico_clusters_by_phase{phase!="Ready"}

# Average reconciliation time
rate(nico_cluster_reconcile_duration_seconds_sum[5m]) / rate(nico_cluster_reconcile_duration_seconds_count[5m])

# Reconciliation error rate
rate(nico_cluster_reconcile_errors_total[5m])

# Control plane readiness
nico_cluster_control_plane_nodes{status="ready"} / nico_cluster_control_plane_nodes{status="total"}
```

### Check Operator Logs

```bash
kubectl logs -l app=nico-operator -n nico-operator-system -f
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
- Restrict access to kubeconfig Secrets

### Reliability

- Use Git tags for production configurations
- Implement health checks for critical services
- Monitor applied commit hashes via Prometheus metrics
- Test configurations in staging first
- Set up alerts for reconciliation errors

### Maintenance

- Regularly update NixOS channels
- Monitor disk usage on target machines
- Keep operator and dependencies updated
- Maintain backup procedures
- Monitor metrics for anomalies

### GitOps Workflow

1. **Development**: Make changes in feature branches
2. **Testing**: Apply to test machines first
3. **Review**: Create pull requests for changes
4. **Production**: Merge to main and apply tags
5. **Monitoring**: Watch applied commit status and Prometheus metrics

## Important Behavior Changes

### Automatic Resource Management

NICO v1alpha1 introduces several automatic behaviors that improve lifecycle management:

#### 1. Cascade Deletion (ownerReference)

All NixosConfiguration resources created by NICO have an `ownerReference` pointing to their parent KubernetesCluster. This means:

- ✅ **Automatic cleanup**: Deleting a cluster automatically removes all its configurations
- ✅ **No orphaned resources**: Machines are automatically released for reuse
- ⚠️ **Cannot delete configs independently**: You cannot manually delete individual NixosConfiguration resources while the cluster exists

```bash
# This will delete the cluster AND all its NixosConfiguration resources
kubectl delete kubernetescluster my-cluster

# This will fail - configs are protected by ownerReference
kubectl delete nixosconfiguration my-cluster-cp-01
# Error: admission webhook denied (or will be recreated by controller)
```

#### 2. Automatic Kubeconfig Generation

When the control plane becomes ready:

- ✅ Kubeconfig Secret is automatically created
- ✅ Named `<cluster-name>-kubeconfig`
- ✅ **Distribution-agnostic extraction**: Works with k3s, k0s, kubeadm, and other distributions
- ✅ **SSH-based**: Extracts via SSH from first control plane node
- ✅ **Multiple fallbacks**: Tries standard paths and kubectl command

```bash
# Secret appears automatically when phase=ControlPlaneReady
kubectl get secret my-cluster-kubeconfig

# Extract and use
kubectl get secret my-cluster-kubeconfig -o jsonpath='{.data.kubeconfig}' | base64 -d > kubeconfig.yaml
export KUBECONFIG=./kubeconfig.yaml
kubectl get nodes
```

**Extraction process**:
1. SSH to first control plane node using Machine's SSH key
2. Try standard kubeconfig locations for different distributions
3. Fallback to `kubectl config view --raw` if files not found
4. Parse and validate YAML format
5. Store in Secret for cluster access

#### 3. Cleanup Configuration

NICO automatically sets cleanup behavior for all cluster machines:

- Uses `onRemoveFlake: "#minimal"` for cleanup
- Your Git repository **must** provide a `#minimal` flake output
- This reverts machines to a minimal state when cluster is deleted

**Required in your flake.nix:**
```nix
{
  outputs = { self, nixpkgs }: {
    # Your cluster node configurations
    nixosConfigurations.cp-01 = ...;
    nixosConfigurations.worker-01 = ...;

    # REQUIRED: Minimal cleanup configuration
    nixosConfigurations.minimal = nixpkgs.lib.nixosSystem {
      system = "x86_64-linux";
      modules = [
        ({ config, pkgs, ... }: {
          # Minimal system configuration
          boot.loader.grub.enable = true;
          fileSystems."/" = { device = "/dev/sda1"; fsType = "ext4"; };
          networking.useDHCP = true;
          services.openssh.enable = true;
        })
      ];
    };
  };
}
```

#### 4. Role Labeling

All NixosConfiguration resources get automatic labels:

```yaml
metadata:
  labels:
    nico.homystack.com/cluster: "my-cluster"
    nico.homystack.com/role: "control-plane"  # or "worker"
```

Use these labels for filtering and debugging:

```bash
# Find all configurations for a cluster
kubectl get nixosconfigurations -l nico.homystack.com/cluster=my-cluster

# Find all control plane configurations
kubectl get nixosconfigurations -l nico.homystack.com/role=control-plane
```

#### 5. Status Monitoring

Cluster status is updated every 30 seconds with real-time node readiness:

```bash
# Watch cluster status in real-time
kubectl get kubernetescluster my-cluster -w

# Check detailed status
kubectl get kubernetescluster my-cluster -o jsonpath='{.status}' | jq
```

### Migration Notes

If upgrading from a previous version:

1. **Backup existing resources** before upgrading
2. **Update Git repositories** to include `#minimal` flake output
3. **Update monitoring** to use new Prometheus metrics endpoint
4. **Review RBAC** - operator now needs permissions for ownerReferences
5. **Test cascade deletion** in non-production environment first

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
