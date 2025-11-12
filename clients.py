#!/usr/bin/env python3

import base64
import kubernetes
import logging
import sys
from typing import Dict
import os
from pathlib import Path
logger = logging.getLogger(__name__)


def setup_kubernetes_client():
    kubeconfig_path = os.environ.get("KUBECONFIG", "~/.kube/config")
    expanded_kubeconfig = os.path.expanduser(kubeconfig_path)
    kubeconfig_file = Path(expanded_kubeconfig)

    print(f"Attempting to connect to Kubernetes")
    print(f"KUBECONFIG variable: {kubeconfig_path}")
    print(f"Expanded kubeconfig path: {expanded_kubeconfig}")

    # Check if file exists
    if kubeconfig_file.exists():
        logger.info(f"Kubeconfig file found: {kubeconfig_file}")
        try:
            stat = kubeconfig_file.stat()
            logger.info(f"File permissions: {oct(stat.st_mode)[-3:]}")
            logger.info(f"File size: {stat.st_size} bytes")
        except Exception as e:
            logger.warning(f"Failed to get file metadata: {e}")

        # Try to load kubeconfig
        try:
            kubernetes.config.load_kube_config(config_file=expanded_kubeconfig)
            logger.info("✅ Successfully loaded kubeconfig")
            return
        except kubernetes.config.ConfigException as e:
            logger.warning(f"❌ Failed to load kubeconfig: {e}")
        except Exception as e:
            logger.error(f"❗ Unexpected error loading kubeconfig: {e}", exc_info=True)
    else:
        logger.warning(f"Kubeconfig file NOT found: {kubeconfig_file}")

    # If kubeconfig doesn't work - try in-cluster
    logger.info("Switching to in-cluster connection attempt...")

    # Check for in-cluster environment variables
    host = os.environ.get("KUBERNETES_SERVICE_HOST")
    port = os.environ.get("KUBERNETES_SERVICE_PORT")
    logger.info(f"KUBERNETES_SERVICE_HOST: {host}")
    logger.info(f"KUBERNETES_SERVICE_PORT: {port}")

    if not host or not port:
        logger.error("❌ KUBERNETES_SERVICE_HOST and KUBERNETES_SERVICE_PORT variables not set — in-cluster config impossible")

    try:
        kubernetes.config.load_incluster_config()
        logger.info("✅ Successfully loaded in-cluster config")
    except kubernetes.config.ConfigException as e:
        logger.error(f"❌ In-cluster connection error: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❗ Critical error during in-cluster connection: {e}", exc_info=True)
        sys.exit(1)

# Call initialization
setup_kubernetes_client()

# Global Kubernetes clients
api_client = kubernetes.client.ApiClient()
core_v1 = kubernetes.client.CoreV1Api()
custom_objects_api = kubernetes.client.CustomObjectsApi()


async def get_secret_data(secret_name: str, namespace: str) -> Dict[str, str]:
    """Get data from Kubernetes Secret"""
    try:
        secret = core_v1.read_namespaced_secret(secret_name, namespace)
        if not secret.data:
            return {}
        return {
            key: base64.b64decode(value).decode("utf-8") if value else ""
            for key, value in secret.data.items()
        }
    except Exception as e:
        logger.error(f"Failed to get secret {secret_name}: {e}")
        raise




def get_machine(machine_name: str, namespace: str):
    """Get Machine resource"""
    return custom_objects_api.get_namespaced_custom_object(
        group="nio.homystack.com",
        version="v1alpha1",
        namespace=namespace,
        plural="machines",
        name=machine_name,
    )


def list_machines(namespace: str):
    """List all Machine resources in namespace"""
    try:
        machines = custom_objects_api.list_namespaced_custom_object(
            group="nio.homystack.com",
            version="v1alpha1",
            namespace=namespace,
            plural="machines",
        )
        return machines.get("items", [])
    except Exception as e:
        logger.error(f"Failed to list machines: {e}")
        return []


async def create_secret(secret_name: str, namespace: str, data: Dict[str, str]):
    """Create a Kubernetes Secret"""
    try:
        # Encode data to base64
        encoded_data = {
            key: base64.b64encode(value.encode("utf-8")).decode("utf-8")
            for key, value in data.items()
        }
        
        secret = kubernetes.client.V1Secret(
            metadata=kubernetes.client.V1ObjectMeta(name=secret_name),
            data=encoded_data,
        )
        
        core_v1.create_namespaced_secret(namespace, secret)
        logger.info(f"Created secret: {secret_name}")
    except Exception as e:
        logger.error(f"Failed to create secret {secret_name}: {e}")
        raise


async def delete_secret(secret_name: str, namespace: str):
    """Delete a Kubernetes Secret"""
    try:
        core_v1.delete_namespaced_secret(secret_name, namespace)
        logger.info(f"Deleted secret: {secret_name}")
    except Exception as e:
        logger.error(f"Failed to delete secret {secret_name}: {e}")
        raise


async def create_nixos_configuration(config_name: str, namespace: str, spec: Dict):
    """Create NixosConfiguration resource"""
    try:
        body = {
            "apiVersion": "nio.homystack.com/v1alpha1",
            "kind": "NixosConfiguration",
            "metadata": {"name": config_name},
            "spec": spec,
        }

        custom_objects_api.create_namespaced_custom_object(
            group="nio.homystack.com",
            version="v1alpha1",
            namespace=namespace,
            plural="nixosconfigurations",
            body=body,
        )
        logger.info(f"Created NixosConfiguration: {config_name}")
    except Exception as e:
        logger.error(f"Failed to create NixosConfiguration {config_name}: {e}")
        raise


async def create_nixos_configuration_with_owner(
    config_name: str, namespace: str, spec: Dict,
    owner_name: str, owner_uid: str, role: str
):
    """Create NixosConfiguration resource with ownerReference for cascade deletion"""
    try:
        body = {
            "apiVersion": "nio.homystack.com/v1alpha1",
            "kind": "NixosConfiguration",
            "metadata": {
                "name": config_name,
                "labels": {
                    "nico.homystack.com/cluster": owner_name,
                    "nico.homystack.com/role": role,
                },
                "ownerReferences": [
                    {
                        "apiVersion": "nico.homystack.com/v1alpha1",
                        "kind": "KubernetesCluster",
                        "name": owner_name,
                        "uid": owner_uid,
                        "controller": True,
                        "blockOwnerDeletion": True,
                    }
                ],
            },
            "spec": spec,
        }

        custom_objects_api.create_namespaced_custom_object(
            group="nio.homystack.com",
            version="v1alpha1",
            namespace=namespace,
            plural="nixosconfigurations",
            body=body,
        )
        logger.info(f"Created NixosConfiguration with owner: {config_name}")
    except Exception as e:
        logger.error(f"Failed to create NixosConfiguration {config_name}: {e}")
        raise


async def delete_nixos_configuration(config_name: str, namespace: str):
    """Delete NixosConfiguration resource"""
    try:
        custom_objects_api.delete_namespaced_custom_object(
            group="nio.homystack.com",
            version="v1alpha1",
            namespace=namespace,
            plural="nixosconfigurations",
            name=config_name,
        )
        logger.info(f"Deleted NixosConfiguration: {config_name}")
    except Exception as e:
        logger.error(f"Failed to delete NixosConfiguration {config_name}: {e}")
        raise


def get_nixos_configuration(config_name: str, namespace: str):
    """Get NixosConfiguration resource"""
    try:
        return custom_objects_api.get_namespaced_custom_object(
            group="nio.homystack.com",
            version="v1alpha1",
            namespace=namespace,
            plural="nixosconfigurations",
            name=config_name,
        )
    except Exception as e:
        logger.error(f"Failed to get NixosConfiguration {config_name}: {e}")
        raise


async def patch_nixos_configuration_spec(
    config_name: str, namespace: str, spec_updates: Dict
):
    """
    Patch NixosConfiguration spec fields using JSON Merge Patch

    This allows setting fields to null to remove them from the spec.
    """
    try:
        body = {"spec": spec_updates}

        # Use JSON Merge Patch content type to support field removal with null
        custom_objects_api.patch_namespaced_custom_object(
            group="nio.homystack.com",
            version="v1alpha1",
            namespace=namespace,
            plural="nixosconfigurations",
            name=config_name,
            body=body,
            content_type="application/merge-patch+json",
        )
        logger.info(f"Patched NixosConfiguration {config_name} spec: {list(spec_updates.keys())}")
    except Exception as e:
        logger.error(f"Failed to patch NixosConfiguration {config_name}: {e}")
        raise


async def update_cluster_status(
    cluster_name: str, namespace: str, status_updates: Dict
):
    """Update KubernetesCluster resource status"""
    try:
        body = {"status": status_updates}

        custom_objects_api.patch_namespaced_custom_object_status(
            group="nico.homystack.com",
            version="v1alpha1",
            namespace=namespace,
            plural="kubernetesclusters",
            name=cluster_name,
            body=body,
        )
        logger.debug(f"Updated cluster status: {cluster_name}")

    except Exception as e:
        logger.error(f"Failed to update cluster status: {e}")
        raise
