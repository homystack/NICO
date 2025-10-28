#!/usr/bin/env python3

import kopf
import logging
import os

from kubernetescluster_handlers import reconcile_kubernetes_cluster, monitor_cluster_status
from clients import update_cluster_status

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
print("starting NICO operator")

# --- Add Nix path to PATH ---
nix_bin_path = "/nix/var/nix/profiles/default/bin"
current_path = os.environ.get("PATH", "")
if nix_bin_path not in current_path:
    os.environ["PATH"] = f"{nix_bin_path}:{current_path}"
    logger.info(f"Added Nix path to PATH: {nix_bin_path}")


# KubernetesCluster handlers
@kopf.on.create("nico.homystack.com", "v1alpha1", "kubernetesclusters")
@kopf.on.update("nico.homystack.com", "v1alpha1", "kubernetesclusters")
@kopf.on.resume("nico.homystack.com", "v1alpha1", "kubernetesclusters")
@kopf.on.delete("nico.homystack.com", "v1alpha1", "kubernetesclusters")
async def unified_kubernetes_cluster_handler(body, spec, name, namespace, **kwargs):
    """Унифицированный обработчик для всех операций с KubernetesCluster"""
    await reconcile_kubernetes_cluster(body, spec, name, namespace, **kwargs)


# Already defined in kubernetescluster_handlers.py, no need to redefine here
# @kopf.timer("nico.homystack.com", "v1alpha1", "kubernetesclusters", interval=30.0)
# async def monitor_cluster_status(body, spec, name, namespace, **kwargs):
#     """Monitor and update cluster status based on machine states"""
#     await monitor_cluster_status(body, spec, name, namespace, **kwargs)


@kopf.on.startup()
def configure(settings: kopf.OperatorSettings, **_):
    settings.posting.level = logging.WARNING


if __name__ == "__main__":
    kopf.run()
