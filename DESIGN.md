
# **PRD: NICO — NixOS Infrastructure Cluster Orchestration**  
*Declarative Kubernetes Cluster Lifecycle on Bare-Metal NixOS*

## **1. Objective**
Build a Kubernetes-native operator **NICO** that orchestrates **Kubernetes clusters** (k3s, k0s, kubeadm, etc.) on machines managed by **NIO**.  
All deployment logic—including the choice of Kubernetes distribution—is defined entirely within a **Git flake**. NICO acts solely as a coordinator: it manages cluster lifecycle and generates machine-specific configurations, delegating actual provisioning to NIO.

---

## **2. CRD: `KubernetesCluster` (`kubernetescluster.nico.homystack.com/v1alpha1`)**

### **2.1. Spec**

```yaml
spec:
  # Git repository containing flakes (optional)
  # If omitted, a default repository is used
  gitRepo: "https://github.com/user/cluster-flakes.git"

  # Subdirectory within the repository (optional; root by default)
  configurationSubdir: "clusters/prod"

  # Reference to credentials for private repositories (optional)
  credentialsRef:
    name: git-creds

  # Control Plane
  controlPlane:
    # Priority 1: explicit list of Machine names
    machines: ["cp-01", "cp-02", "cp-03"]
    # Priority 2: if 'machines' is empty, use selector + count
    machineSelector:
      matchLabels:
        role: "control-plane"
    count: 3  # ignored if 'machines' is specified

  # Data Plane (Workers)
  dataPlane:
    machines: []  # explicit list (optional)
    machineSelector:
      matchLabels:
        role: "worker"
    count: 5
```

> **Important**:  
> - The `machines` field **takes precedence** over `machineSelector` + `count`.  
> - All referenced `Machine` resources must exist and be `discoverable: true`.  
> - NICO **does not create** `Machine` resources—it only consumes existing ones.

---

### **2.2. Status**

```yaml
status:
  # Overall lifecycle phase
  phase: "Provisioning"  # Provisioning | Ready | Failed | Deleting

  # Control plane status
  controlPlane:
    ready: 2
    total: 3
    # List of Machine names with successfully applied NixosConfiguration
    readyMachines: ["cp-01", "cp-02"]

  # Data plane status
  dataPlane:
    ready: 4
    total: 5
    readyMachines: ["worker-01", "worker-02", "worker-03", "worker-04"]

  # Secret containing kubeconfig (created after control plane is ready)
  kubeconfigSecret: "my-cluster-kubeconfig"

  # Kubernetes-style conditions
  conditions:
    - type: ControlPlaneReady
      status: "False"
      reason: "WaitingForMachines"
      message: "3/3 control plane machines ready"
    - type: DataPlaneReady
      status: "True"
      lastTransitionTime: "2025-10-22T12:00:00Z"
```

---

## **3. Operator Behavior**

### **3.1. On `KubernetesCluster` Creation**
1. **Validate machines**:
   - If `controlPlane.machines` is non-empty, use it.
   - Otherwise, select up to `controlPlane.count` machines via `controlPlane.machineSelector` where `Machine.status.hasConfiguration: false`.
   - Apply the same logic for `dataPlane`.
2. **Generate a `NixosConfiguration`** for each machine:
   - `gitRepo`: from spec or default,
   - `flake: "#<machine-name>"`,
   - `configurationSubdir` from spec or none
   - `onRemoveFlake: "#minimal"`,
   - `additionalFiles` includes:
     - `cluster.nix` (inline) — listing all nodes grouped by role,
     - `join-token` (from a Secret generated for the control plane).
     - `machine-ssh-key` (a private ssh key for accessing machine)
3. **Wait** for all `NixosConfiguration` resources to reach `Ready`.
4. **Create a Secret** `<cluster-name>-kubeconfig`.

Example of NixosConfiguration
```
apiVersion: nio.homystack.com/v1alpha1
kind: NixosConfiguration
metadata:
  name: ultra-flake-config
  namespace: default
spec:
  gitRepo: "https://github.com/homystack/NIO"
  flake: "#custom-server"
  onRemoveFlake: "#minimal"
  configurationSubdir: "examples/nix" 
  
  # Ссылка на машину
  machineRef:
    name: machine-b0-41-6f-10-7e-42
  
  # Настройки для флейков
  fullInstall: false 
  
  # Примеры использования additionalFiles (PRD requirement)
  additionalFiles:
    # Inline файл - статическое содержимое
    - path: "config/static-config.nix"
      valueType: Inline
      inline: |
        { config, pkgs, ... }:
        {
          # Статическая конфигурация
          networking.hostName = "custom-server";
          services.nginx.enable = true;
        }
    
    # SecretRef - machine
    - path: "flake-ssh-private-key"
      valueType: SecretRef
      secretRef:
        name: ssh-private-key-b0-41-6f-10-7e-42
```

### **3.2. Rolling Updates**
- Triggered when any of the following change:
  - `gitRepo`, `configurationSubdir`,
  - Machine lists,
  - `credentialsRef`.
- Update sequence:
  - Workers first (one at a time),
  - Then control plane nodes (while preserving quorum).

### **3.3. On Deletion**
- Delete all `NixosConfiguration` resources created by NICO (with `ownerReference`).
- Machines automatically revert to `hasConfiguration: false`.
- Delete the `kubeconfig` Secret.

---

## **4. Integration with NIO**
- NICO **creates and owns** `NixosConfiguration` resources.
- NICO **reads** `Machine` status (especially `discoverable` and `hasConfiguration`).
- All OS-level operations (installation, rebuild, cleanup) are delegated to NIO.

---

## **5. Flake Requirements**
The flake in `gitRepo` **must**:
- Expose an output for each node: `#<machine-name>`,
- Support importing `cluster.nix` (containing node lists by role),
- Implement the desired Kubernetes distribution (k3s/k0s/kubeadm) **within the Nix configuration itself**.

> NICO **does not know or manage** the Kubernetes distribution—this is entirely handled by the flake.

---

## **6. Success Criteria**
- User creates a `KubernetesCluster` → cluster reaches `Ready` within ~10 minutes.
- `kubectl --kubeconfig=<secret-data> get nodes` works immediately.
- Updating `gitRepo` triggers a safe rolling update.
- Deleting the resource cleanly releases all machines for reuse.

