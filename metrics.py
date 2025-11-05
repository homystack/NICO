#!/usr/bin/env python3
"""
Prometheus metrics for NICO operator
"""

import logging
from prometheus_client import Counter, Gauge, Histogram, Info
import kopf

logger = logging.getLogger(__name__)

# Cluster metrics
clusters_total = Gauge(
    "nico_clusters_total",
    "Total number of KubernetesCluster resources",
    ["namespace"],
)

clusters_by_phase = Gauge(
    "nico_clusters_by_phase",
    "Number of clusters by phase",
    ["namespace", "phase"],
)

cluster_control_plane_nodes = Gauge(
    "nico_cluster_control_plane_nodes",
    "Number of control plane nodes per cluster",
    ["namespace", "cluster", "status"],
)

cluster_worker_nodes = Gauge(
    "nico_cluster_worker_nodes",
    "Number of worker nodes per cluster",
    ["namespace", "cluster", "status"],
)

# Operation metrics
cluster_reconcile_duration = Histogram(
    "nico_cluster_reconcile_duration_seconds",
    "Time spent reconciling a cluster",
    ["namespace", "cluster"],
)

cluster_reconcile_errors = Counter(
    "nico_cluster_reconcile_errors_total",
    "Total number of cluster reconciliation errors",
    ["namespace", "cluster", "error_type"],
)

cluster_reconcile_success = Counter(
    "nico_cluster_reconcile_success_total",
    "Total number of successful cluster reconciliations",
    ["namespace", "cluster"],
)

# NixosConfiguration metrics
nixos_configs_created = Counter(
    "nico_nixos_configs_created_total",
    "Total number of NixosConfiguration resources created",
    ["namespace", "cluster", "role"],
)

nixos_configs_deleted = Counter(
    "nico_nixos_configs_deleted_total",
    "Total number of NixosConfiguration resources deleted",
    ["namespace", "cluster"],
)

# Machine selection metrics
machine_selection_duration = Histogram(
    "nico_machine_selection_duration_seconds",
    "Time spent selecting machines for a cluster",
    ["namespace", "cluster", "role"],
)

machines_selected = Gauge(
    "nico_machines_selected",
    "Number of machines selected for cluster role",
    ["namespace", "cluster", "role"],
)

# Kubeconfig generation metrics
kubeconfig_generation_success = Counter(
    "nico_kubeconfig_generation_success_total",
    "Total number of successful kubeconfig generations",
    ["namespace", "cluster"],
)

kubeconfig_generation_errors = Counter(
    "nico_kubeconfig_generation_errors_total",
    "Total number of kubeconfig generation errors",
    ["namespace", "cluster"],
)

# Operator info
operator_info = Info(
    "nico_operator",
    "NICO operator information",
)


def init_metrics():
    """Initialize operator metrics"""
    operator_info.info(
        {
            "version": "v1alpha1",
            "name": "nico-operator",
            "description": "NixOS Infrastructure Cluster Orchestrator",
        }
    )
    logger.info("Prometheus metrics initialized")


def update_cluster_metrics(namespace: str, cluster_name: str, status: dict):
    """Update metrics for a cluster based on its status"""
    try:
        phase = status.get("phase", "Unknown")

        # Update phase metrics
        for p in ["Provisioning", "Ready", "Failed", "Deleting", "ControlPlaneReady"]:
            if p == phase:
                clusters_by_phase.labels(namespace=namespace, phase=p).inc()
            else:
                # Reset other phases for this cluster
                clusters_by_phase.labels(namespace=namespace, phase=p).set(0)

        # Update node metrics
        control_plane_ready_str = status.get("controlPlaneReady", "0/0")
        data_plane_ready_str = status.get("dataPlaneReady", "0/0")

        try:
            cp_ready, cp_total = map(int, control_plane_ready_str.split("/"))
            cluster_control_plane_nodes.labels(
                namespace=namespace, cluster=cluster_name, status="ready"
            ).set(cp_ready)
            cluster_control_plane_nodes.labels(
                namespace=namespace, cluster=cluster_name, status="total"
            ).set(cp_total)
        except (ValueError, AttributeError):
            pass

        try:
            dp_ready, dp_total = map(int, data_plane_ready_str.split("/"))
            cluster_worker_nodes.labels(
                namespace=namespace, cluster=cluster_name, status="ready"
            ).set(dp_ready)
            cluster_worker_nodes.labels(
                namespace=namespace, cluster=cluster_name, status="total"
            ).set(dp_total)
        except (ValueError, AttributeError):
            pass

    except Exception as e:
        logger.warning(f"Failed to update cluster metrics: {e}")


def record_reconcile_success(namespace: str, cluster_name: str):
    """Record successful cluster reconciliation"""
    cluster_reconcile_success.labels(
        namespace=namespace, cluster=cluster_name
    ).inc()


def record_reconcile_error(namespace: str, cluster_name: str, error_type: str):
    """Record cluster reconciliation error"""
    cluster_reconcile_errors.labels(
        namespace=namespace, cluster=cluster_name, error_type=error_type
    ).inc()


def record_nixos_config_created(namespace: str, cluster_name: str, role: str):
    """Record NixosConfiguration creation"""
    nixos_configs_created.labels(
        namespace=namespace, cluster=cluster_name, role=role
    ).inc()


def record_nixos_config_deleted(namespace: str, cluster_name: str):
    """Record NixosConfiguration deletion"""
    nixos_configs_deleted.labels(namespace=namespace, cluster=cluster_name).inc()


def record_kubeconfig_generated(namespace: str, cluster_name: str, success: bool):
    """Record kubeconfig generation attempt"""
    if success:
        kubeconfig_generation_success.labels(
            namespace=namespace, cluster=cluster_name
        ).inc()
    else:
        kubeconfig_generation_errors.labels(
            namespace=namespace, cluster=cluster_name
        ).inc()


def record_machines_selected(
    namespace: str, cluster_name: str, role: str, count: int
):
    """Record number of machines selected for role"""
    machines_selected.labels(
        namespace=namespace, cluster=cluster_name, role=role
    ).set(count)
