#!/bin/bash

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
CLUSTER_NAME="nico-dev"
KUBECONFIG_DIR="${HOME}/.kube"
KUBECONFIG_FILE="${KUBECONFIG_DIR}/config"
KIND_VERSION="v0.20.0"

echo -e "${GREEN}=== NICO Kind Cluster Setup ===${NC}"

# Check if kind is installed
if ! command -v kind &> /dev/null; then
    echo -e "${YELLOW}kind not found. Installing kind ${KIND_VERSION}...${NC}"

    # Detect OS and architecture
    OS=$(uname -s | tr '[:upper:]' '[:lower:]')
    ARCH=$(uname -m)

    if [ "$ARCH" = "x86_64" ]; then
        ARCH="amd64"
    elif [ "$ARCH" = "aarch64" ] || [ "$ARCH" = "arm64" ]; then
        ARCH="arm64"
    fi

    # Download and install kind
    curl -Lo ./kind "https://kind.sigs.k8s.io/dl/${KIND_VERSION}/kind-${OS}-${ARCH}"
    chmod +x ./kind
    sudo mv ./kind /usr/local/bin/kind

    echo -e "${GREEN}✓ kind installed successfully${NC}"
else
    echo -e "${GREEN}✓ kind is already installed ($(kind version))${NC}"
fi

# Check if kubectl is installed
if ! command -v kubectl &> /dev/null; then
    echo -e "${RED}✗ kubectl not found. Please install kubectl first.${NC}"
    echo -e "Visit: https://kubernetes.io/docs/tasks/tools/"
    exit 1
fi

echo -e "${GREEN}✓ kubectl is installed ($(kubectl version --client -o json | jq -r .clientVersion.gitVersion))${NC}"

# Check if cluster already exists
if kind get clusters | grep -q "^${CLUSTER_NAME}$"; then
    echo -e "${YELLOW}Cluster '${CLUSTER_NAME}' already exists.${NC}"
    read -p "Do you want to delete and recreate it? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo -e "${YELLOW}Deleting existing cluster...${NC}"
        kind delete cluster --name "${CLUSTER_NAME}"
    else
        echo -e "${YELLOW}Using existing cluster.${NC}"
        # Export kubeconfig for existing cluster
        kind export kubeconfig --name "${CLUSTER_NAME}" --kubeconfig "${KUBECONFIG_FILE}"

        # Fix server address to use 127.0.0.1 instead of 0.0.0.0
        sed -i 's|https://0.0.0.0:6443|https://127.0.0.1:6443|g' "${KUBECONFIG_FILE}"
        echo -e "${GREEN}✓ Kubeconfig exported to ${KUBECONFIG_FILE}${NC}"

        # Apply CRDs
        echo -e "${YELLOW}Applying CRDs...${NC}"
        kubectl --kubeconfig="${KUBECONFIG_FILE}" apply -f crds/
        echo -e "${GREEN}✓ CRDs applied${NC}"

        exit 0
    fi
fi

# Create Kind cluster with custom configuration
echo -e "${YELLOW}Creating Kind cluster '${CLUSTER_NAME}'...${NC}"

# Create temporary kind config
cat > /tmp/kind-config.yaml <<EOF
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
name: ${CLUSTER_NAME}
nodes:
  - role: control-plane
    kubeadmConfigPatches:
      - |
        kind: InitConfiguration
        nodeRegistration:
          kubeletExtraArgs:
            node-labels: "ingress-ready=true"
    extraPortMappings:
      - containerPort: 80
        hostPort: 80
        protocol: TCP
      - containerPort: 443
        hostPort: 443
        protocol: TCP
      - containerPort: 6443
        hostPort: 6443
        protocol: TCP
EOF

# Create the cluster
kind create cluster --config /tmp/kind-config.yaml --wait 5m

# Clean up temp config
rm /tmp/kind-config.yaml

echo -e "${GREEN}✓ Kind cluster created${NC}"

# Export kubeconfig to dedicated file
echo -e "${YELLOW}Exporting kubeconfig...${NC}"
mkdir -p "${KUBECONFIG_DIR}"
kind export kubeconfig --name "${CLUSTER_NAME}" --kubeconfig "${KUBECONFIG_FILE}"

# Fix server address to use 127.0.0.1 instead of 0.0.0.0
sed -i 's|https://0.0.0.0:6443|https://127.0.0.1:6443|g' "${KUBECONFIG_FILE}"

echo -e "${GREEN}✓ Kubeconfig saved to ${KUBECONFIG_FILE}${NC}"

# Apply CRDs
echo -e "${YELLOW}Applying NICO CRDs...${NC}"
kubectl --kubeconfig="${KUBECONFIG_FILE}" apply -f crds/

echo -e "${GREEN}✓ CRDs applied successfully${NC}"

# Wait for API server to be ready
echo -e "${YELLOW}Waiting for API server...${NC}"
kubectl --kubeconfig="${KUBECONFIG_FILE}" wait --for=condition=Ready nodes --all --timeout=120s

echo -e "${GREEN}✓ Cluster is ready${NC}"

# Display cluster info
echo ""
echo -e "${GREEN}=== Cluster Information ===${NC}"
echo -e "Cluster Name: ${CLUSTER_NAME}"
echo -e "Kubeconfig:   ${KUBECONFIG_FILE}"
echo ""
echo -e "${YELLOW}To use this cluster, run:${NC}"
echo -e "  export KUBECONFIG=${KUBECONFIG_FILE}"
echo ""
echo -e "${YELLOW}Or use with kubectl:${NC}"
echo -e "  kubectl --kubeconfig=${KUBECONFIG_FILE} get nodes"
echo ""
echo -e "${YELLOW}To delete the cluster:${NC}"
echo -e "  kind delete cluster --name ${CLUSTER_NAME}"
echo ""
echo -e "${GREEN}=== Next Steps ===${NC}"
echo -e "1. Export KUBECONFIG: ${YELLOW}export KUBECONFIG=${KUBECONFIG_FILE}${NC}"
echo -e "2. Start NICO operator: ${YELLOW}docker-compose up -d nico${NC}"
echo -e "3. Debug in VSCode: ${YELLOW}F5 → 'NICO: Attach to Running Container'${NC}"
echo -e "4. Apply example: ${YELLOW}kubectl apply -f examples/kubernetescluster-example.yaml${NC}"
echo ""
echo -e "${GREEN}✓ Setup complete!${NC}"
