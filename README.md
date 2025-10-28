# NICO - NixOS Infrastructure Cluster Orchestrator

A Kubernetes-native operator for declarative management of bare-metal and virtual machines running NixOS, with built-in Kubernetes cluster provisioning capabilities.

It's based on NIO - NixOS Infrastructure Operator, that operates single NixOS Machine in GitOps approach

## Overview

NICO (NixOS Infrastructure Cluster Orchestrator) provides a GitOps approach to managing infrastructure using NixOS. It extends beyond simple machine management to include complete Kubernetes cluster provisioning and lifecycle management.

## Key Features

- **GitOps Infrastructure**: All configurations managed through Git repositories with commit tracking
- **Multi-Level Management**: Manage individual machines and complete Kubernetes clusters
- **Declarative Configuration**: Define infrastructure state using Kubernetes Custom Resources
- **Reproducibility**: Every system state is tied to specific Git commits for full reproducibility
- **Safe Operations**: Clean state management with safe deletion procedures
- **Two Application Modes**: Full OS installation and existing system updates

## Architecture

NICO + NIO operates at three levels:

1. **Machine Level**: Manage individual physical or virtual machines (NIO Level)
2. **Configuration Level**: Apply NixOS configurations to machines (NIO Level)
3. **Cluster Level**: Provision and manage complete Kubernetes clusters (NICO Level)

## Quick Start

### Prerequisites

- Kubernetes cluster (v1.20+)
- Kubectl configured
- Target machines accessible via SSH

### Installation

```bash
# Apply CRDs
kubectl apply -f crds/

# Install the operator
kubectl apply -f deployment.yaml
```

### Basic Usage

1. **Create a Machine**:
```bash
kubectl apply -f examples/machine-example.yaml
```

2. **Apply Configuration**:
```bash
kubectl apply -f examples/nixosconfiguration-example.yaml
```

3. **Create Kubernetes Cluster**:
```bash
kubectl apply -f examples/kubernetescluster-example.yaml
```

## Custom Resources

### Machine (`machine.nio.homystack.com/v1alpha1`)
Represents physical or virtual machines with SSH connectivity.

### NixosConfiguration (`nixosconfiguration.nio.homystack.com/v1alpha1`)
Defines NixOS configurations to be applied to machines from Git repositories.

### KubernetesCluster (`kubernetescluster.nico.homystack.com/v1alpha1`)
Manages complete Kubernetes clusters with control plane and worker nodes.

## Documentation

- **[Usage Guide](usage.md)** - Complete usage instructions and examples
- **[Configuration Reference](configuration.md)** - Detailed configuration options for all CRDs
- **[Development Guide](DEVELOPMENT.md)** - Development and debugging setup

## Examples

Check the [examples/](examples/) directory for:
- Machine definitions
- NixOS configuration examples
- Kubernetes cluster configurations
- Nix flake configurations

## Project Structure

```
NICO/
├── main.py                          # Main operator entry point
├── clients.py                       # Kubernetes client utilities
├── kubernetescluster_handlers.py    # Kubernetes cluster handlers
├── requirements.txt                 # Python dependencies
├── crds/                           # Custom Resource Definitions
│   ├── machine.yaml
│   ├── nixosconfiguration.yaml
│   └── kubernetescluster.yaml
├── examples/                       # Example configurations
│   ├── machine-example.yaml
│   ├── nixosconfiguration-example.yaml
│   └── kubernetescluster-example.yaml
├── nix/                           # NixOS configurations
│   ├── flake.nix
│   └── nodes/
├── scripts/                       # Helper scripts
└── deployment.yaml               # Operator deployment
```

## Status

Check operator status:
```bash
kubectl get machines,nixosconfigurations,kubernetesclusters --all-namespaces
```

## License

[Add your license information here]

## Contributing

[Add contribution guidelines here]
