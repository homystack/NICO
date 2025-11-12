#!/usr/bin/env python3

import kopf
import logging
import asyncio
from datetime import datetime
from typing import List, Dict, Optional
import time
import os

from clients import (
    get_machine,
    list_machines,
    create_secret,
    delete_secret,
    get_secret_data,
    update_cluster_status,
    create_nixos_configuration,
    create_nixos_configuration_with_owner,
    delete_nixos_configuration,
    get_nixos_configuration,
    patch_nixos_configuration_spec,
)

from metrics import (
    record_reconcile_success,
    record_reconcile_error,
    record_nixos_config_created,
    record_nixos_config_deleted,
    record_kubeconfig_generated,
    record_machines_selected,
    update_cluster_metrics,
    cluster_reconcile_duration,
    machine_selection_duration,
)

logger = logging.getLogger(__name__)


async def select_machines_for_cluster(
    cluster_spec: dict, namespace: str, role: str, cluster_name: str = "",
    current_status: dict = None
) -> List[str]:
    """
    Select machines for cluster role (controlPlane or dataPlane)
    Priority:
    1. Explicit machines list from spec
    2. Previously selected machines from status (preserves first control plane)
    3. New selection via machineSelector + count

    IMPORTANT: Once machines are selected, they are persisted in cluster status
    to ensure the first control plane node never changes.
    """
    start_time = time.time()

    role_spec = cluster_spec.get(role, {})

    # If explicit machines list is provided, use it
    if role_spec.get("machines"):
        selected = role_spec["machines"]
        if cluster_name:
            record_machines_selected(namespace, cluster_name, role, len(selected))
        return selected

    # Check if we have previously selected machines in status
    if current_status:
        # Map role names to status field names
        if role == "controlPlane":
            status_key = "selectedControlPlaneMachines"
        elif role == "dataPlane":
            status_key = "selectedDataPlaneMachines"
        else:
            status_key = None

        if status_key:
            previously_selected = current_status.get(status_key, [])

            # If we have previously selected machines, reuse them
            # This ensures first control plane node never changes
            if previously_selected:
                logger.info(f"Reusing previously selected {role} machines: {previously_selected}")
                if cluster_name:
                    record_machines_selected(namespace, cluster_name, role, len(previously_selected))
                return previously_selected

    # Otherwise use machineSelector and count
    machine_selector = role_spec.get("machineSelector", {})
    count = role_spec.get("count", 0)

    if count == 0:
        return []

    # Get all machines in namespace
    machines = list_machines(namespace)

    # Filter by selector and hasConfiguration: false
    selected_machines = []
    for machine in machines:
        # Check selector match
        match = True
        machine_labels = machine.get("metadata", {}).get("labels", {})
        for key, value in machine_selector.get("matchLabels", {}).items():
            if machine_labels.get(key) != value:
                match = False
                break

        # Check machine is available (no configuration applied)
        if match and not machine.get("status", {}).get("hasConfiguration", True):
            selected_machines.append(machine["metadata"]["name"])

    # Sort alphabetically for deterministic initial selection
    selected_machines.sort()

    # Return up to count machines
    selected = selected_machines[:count]

    # Record metrics
    if cluster_name:
        duration = time.time() - start_time
        machine_selection_duration.labels(
            namespace=namespace, cluster=cluster_name, role=role
        ).observe(duration)
        record_machines_selected(namespace, cluster_name, role, len(selected))

    logger.info(f"Selected new {role} machines for cluster {cluster_name}: {selected}")
    return selected


def generate_cluster_config(
    cluster_name: str, 
    control_plane_nodes: List[str], 
    worker_nodes: List[str],
    machines_info: Dict[str, Dict]
) -> str:
    """Generate cluster.nix configuration with all nodes including IP addresses"""
    
    # Generate control plane nodes with IPs
    control_plane_with_ips = []
    for node_name in control_plane_nodes:
        machine_info = machines_info.get(node_name, {})
        ip_address = machine_info.get("ipAddress") or machine_info.get("hostname", "unknown")
        control_plane_with_ips.append({
            "name": node_name,
            "ip": ip_address
        })
    
    # Generate worker nodes with IPs
    workers_with_ips = []
    for node_name in worker_nodes:
        machine_info = machines_info.get(node_name, {})
        ip_address = machine_info.get("ipAddress") or machine_info.get("hostname", "unknown")
        workers_with_ips.append({
            "name": node_name,
            "ip": ip_address
        })
    
    # Format as Nix expression
    control_plane_nix = "[\n" + "\n".join(
        f'    {{ name = "{node["name"]}"; ip = "{node["ip"]}"; }}'
        for node in control_plane_with_ips
    ) + "\n  ]"
    
    workers_nix = "[\n" + "\n".join(
        f'    {{ name = "{node["name"]}"; ip = "{node["ip"]}"; }}'
        for node in workers_with_ips
    ) + "\n  ]"
    
    return f"""
{{ config, pkgs, ... }}:
{{
  # Cluster configuration generated by NICO
  # Includes IP addresses for HAProxy configuration at build time
  cluster = {{
    name = "{cluster_name}";
    controlPlane = {control_plane_nix};
    workers = {workers_nix};
  }};
}}
"""


async def create_join_token_secret(
    cluster_name: str, namespace: str
) -> str:
    """Create a secret with join token for cluster nodes (idempotent)"""
    # In a real implementation, this would generate actual tokens
    # For now, we'll create a placeholder
    token_content = f"join-token-for-{cluster_name}"

    secret_name = f"{cluster_name}-join-token"

    # Check if secret already exists
    try:
        from kubernetes.client.rest import ApiException
        from clients import core_v1

        existing_secret = core_v1.read_namespaced_secret(secret_name, namespace)
        logger.info(f"Join token secret {secret_name} already exists, reusing it")
        return secret_name
    except ApiException as e:
        if e.status == 404:
            # Secret doesn't exist, create it
            await create_secret(
                secret_name,
                namespace,
                {
                    "token": token_content,
                },
            )
            logger.info(f"Created join token secret: {secret_name}")
            return secret_name
        else:
            # Other error, re-raise
            raise


async def create_nixos_configuration_for_machine(
    cluster_name: str,
    cluster_uid: str,
    machine_name: str,
    role: str,
    cluster_spec: dict,
    namespace: str,
    join_token_secret: str,
    control_plane_nodes: List[str],
    worker_nodes: List[str],
    machines_info: Dict[str, Dict],
) -> str:
    """Create NixosConfiguration for a cluster machine with ownerReference"""

    # Get machine to check SSH key and determine if fullInstall is needed
    machine = get_machine(machine_name, namespace)

    # Check if machine has the full installation annotation
    annotations = machine.get("metadata", {}).get("annotations", {})
    has_full_install = annotations.get("nico.homystack.com/fullInstallationApplied")

    # Determine SSH key secret name from machine spec
    ssh_key_secret = None
    if machine["spec"].get("sshKeySecretRef"):
        ssh_key_secret = machine["spec"]["sshKeySecretRef"]["name"]

    # Build additional files - according to PRD section 3.1
    additional_files = [
        {
            "path": "cluster.nix",
            "valueType": "Inline",
            "inline": generate_cluster_config(cluster_name, control_plane_nodes, worker_nodes, machines_info),
        },
        {
            "path": "join-token",
            "valueType": "SecretRef",
            "secretRef": {"name": join_token_secret},
        },
    ]

    # Add SSH key if available (PRD requirement)
    if ssh_key_secret:
        additional_files.append({
            "path": "machine-ssh-key",
            "valueType": "SecretRef",
            "secretRef": {"name": ssh_key_secret},
        })

    # Create NixosConfiguration
    config_name = f"{cluster_name}-{machine_name}"

    # According to PRD section 3.1: flake: "#<machine-name>"
    nixos_config_spec = {
        "gitRepo": cluster_spec["gitRepo"],
        "flake": f"#{machine_name}",  # Use machine name as flake output
        "onRemoveFlake": "#minimal",  # PRD requirement: revert to minimal config
        "configurationSubdir": cluster_spec.get("configurationSubdir", ""),
        "machineRef": {"name": machine_name},
        "fullInstall": not has_full_install,  # Full install only if not already done
        "additionalFiles": additional_files,
    }

    # Add ref if specified
    if cluster_spec.get("ref"):
        nixos_config_spec["ref"] = cluster_spec["ref"]

    # Add credentials if specified
    if cluster_spec.get("credentialsRef"):
        nixos_config_spec["credentialsRef"] = cluster_spec["credentialsRef"]

    # Create with ownerReference for cascade deletion (PRD section 3.3)
    await create_nixos_configuration_with_owner(
        config_name, namespace, nixos_config_spec,
        cluster_name, cluster_uid, role
    )

    return config_name


async def reconcile_kubernetes_cluster(body, spec, name, namespace, **kwargs):
    """Main reconciliation point for KubernetesCluster"""
    logger.info(f"Reconciling KubernetesCluster: {name}")

    start_time = time.time()

    try:
        deletion_timestamp = body.get("metadata", {}).get("deletionTimestamp")

        if deletion_timestamp:
            # Handle cluster deletion
            await handle_cluster_deletion(name, namespace, body)
            return

        # Get cluster UID for ownerReference
        cluster_uid = body.get("metadata", {}).get("uid")
        if not cluster_uid:
            raise kopf.PermanentError("Cluster UID not found in metadata")

        # Get current status to preserve previously selected machines
        current_status = body.get("status", {})

        # Select machines for cluster roles (passing status to preserve selection)
        control_plane_nodes = await select_machines_for_cluster(
            spec, namespace, "controlPlane", name, current_status
        )
        worker_nodes = await select_machines_for_cluster(
            spec, namespace, "dataPlane", name, current_status
        )

        if not control_plane_nodes:
            raise kopf.TemporaryError(
                "No available control plane machines found", delay=60
            )

        # Create join token secret
        join_token_secret = await create_join_token_secret(name, namespace)

        # Collect machine information for cluster.nix
        machines_info = {}
        all_machine_names = control_plane_nodes + worker_nodes
        for machine_name in all_machine_names:
            machine = get_machine(machine_name, namespace)
            machines_info[machine_name] = {
                "hostname": machine["spec"].get("hostname", ""),
                "ipAddress": machine["spec"].get("ipAddress", ""),
            }

        # Track created/existing configurations
        applied_configs = {}

        # Create configurations for control plane nodes (idempotent)
        for machine_name in control_plane_nodes:
            config_name = f"{name}-{machine_name}"

            # Check if configuration already exists
            try:
                existing_config = get_nixos_configuration(config_name, namespace)
                logger.info(f"NixosConfiguration {config_name} already exists, checking for updates")

                # Check if gitRepo, ref, configurationSubdir, or credentialsRef changed
                existing_spec = existing_config.get("spec", {})
                spec_updates = {}

                # Check gitRepo (required field)
                if existing_spec.get("gitRepo") != spec.get("gitRepo"):
                    spec_updates["gitRepo"] = spec["gitRepo"]
                    logger.info(f"Detected gitRepo change for {config_name}: {existing_spec.get('gitRepo')} -> {spec['gitRepo']}")

                # Check ref (optional field, support removal)
                cluster_ref = spec.get("ref")
                existing_ref = existing_spec.get("ref")
                if cluster_ref != existing_ref:
                    # Set to new value or None to remove the field
                    spec_updates["ref"] = cluster_ref
                    logger.info(f"Detected ref change for {config_name}: {existing_ref} -> {cluster_ref}")

                # Check configurationSubdir (optional field)
                cluster_subdir = spec.get("configurationSubdir", "")
                existing_subdir = existing_spec.get("configurationSubdir", "")
                if cluster_subdir != existing_subdir:
                    spec_updates["configurationSubdir"] = cluster_subdir
                    logger.info(f"Detected configurationSubdir change for {config_name}: {existing_subdir} -> {cluster_subdir}")

                # Check credentialsRef (optional field, support removal)
                cluster_creds = spec.get("credentialsRef")
                existing_creds = existing_spec.get("credentialsRef")
                if cluster_creds != existing_creds:
                    # Set to new value or None to remove the field
                    spec_updates["credentialsRef"] = cluster_creds
                    logger.info(f"Detected credentialsRef change for {config_name}: {existing_creds} -> {cluster_creds}")

                # Apply updates if any changes detected
                if spec_updates:
                    await patch_nixos_configuration_spec(config_name, namespace, spec_updates)
                    logger.info(f"Updated NixosConfiguration {config_name} with spec changes")

                applied_configs[machine_name] = config_name
            except Exception as e:
                # Config doesn't exist, create it
                if "404" in str(e) or "not found" in str(e).lower():
                    config_name = await create_nixos_configuration_for_machine(
                        name, cluster_uid, machine_name, "control-plane", spec, namespace,
                        join_token_secret, control_plane_nodes, worker_nodes, machines_info
                    )
                    applied_configs[machine_name] = config_name
                    record_nixos_config_created(namespace, name, "control-plane")
                else:
                    # Some other error, re-raise
                    raise

        # Create configurations for worker nodes (idempotent)
        for machine_name in worker_nodes:
            config_name = f"{name}-{machine_name}"

            # Check if configuration already exists
            try:
                existing_config = get_nixos_configuration(config_name, namespace)
                logger.info(f"NixosConfiguration {config_name} already exists, checking for updates")

                # Check if gitRepo, ref, configurationSubdir, or credentialsRef changed
                existing_spec = existing_config.get("spec", {})
                spec_updates = {}

                # Check gitRepo (required field)
                if existing_spec.get("gitRepo") != spec.get("gitRepo"):
                    spec_updates["gitRepo"] = spec["gitRepo"]
                    logger.info(f"Detected gitRepo change for {config_name}: {existing_spec.get('gitRepo')} -> {spec['gitRepo']}")

                # Check ref (optional field, support removal)
                cluster_ref = spec.get("ref")
                existing_ref = existing_spec.get("ref")
                if cluster_ref != existing_ref:
                    # Set to new value or None to remove the field
                    spec_updates["ref"] = cluster_ref
                    logger.info(f"Detected ref change for {config_name}: {existing_ref} -> {cluster_ref}")

                # Check configurationSubdir (optional field)
                cluster_subdir = spec.get("configurationSubdir", "")
                existing_subdir = existing_spec.get("configurationSubdir", "")
                if cluster_subdir != existing_subdir:
                    spec_updates["configurationSubdir"] = cluster_subdir
                    logger.info(f"Detected configurationSubdir change for {config_name}: {existing_subdir} -> {cluster_subdir}")

                # Check credentialsRef (optional field, support removal)
                cluster_creds = spec.get("credentialsRef")
                existing_creds = existing_spec.get("credentialsRef")
                if cluster_creds != existing_creds:
                    # Set to new value or None to remove the field
                    spec_updates["credentialsRef"] = cluster_creds
                    logger.info(f"Detected credentialsRef change for {config_name}: {existing_creds} -> {cluster_creds}")

                # Apply updates if any changes detected
                if spec_updates:
                    await patch_nixos_configuration_spec(config_name, namespace, spec_updates)
                    logger.info(f"Updated NixosConfiguration {config_name} with spec changes")

                applied_configs[machine_name] = config_name
            except Exception as e:
                # Config doesn't exist, create it
                if "404" in str(e) or "not found" in str(e).lower():
                    config_name = await create_nixos_configuration_for_machine(
                        name, cluster_uid, machine_name, "worker", spec, namespace,
                        join_token_secret, control_plane_nodes, worker_nodes, machines_info
                    )
                    applied_configs[machine_name] = config_name
                    record_nixos_config_created(namespace, name, "worker")
                else:
                    # Some other error, re-raise
                    raise
        
        # Update cluster status (including persisted machine selection)
        await update_cluster_status(
            name,
            namespace,
            {
                "phase": "Provisioning",
                "controlPlaneReady": f"0/{len(control_plane_nodes)}",
                "dataPlaneReady": f"0/{len(worker_nodes)}",
                "kubeconfigSecret": f"{name}-kubeconfig",  # Will be created later
                "appliedMachines": applied_configs,
                # Persist selected machines to ensure stable first control plane node
                "selectedControlPlaneMachines": control_plane_nodes,
                "selectedDataPlaneMachines": worker_nodes,
                "conditions": [
                    {
                        "type": "Provisioning",
                        "status": "True",
                        "lastTransitionTime": datetime.utcnow().isoformat() + "Z",
                        "reason": "ConfigurationsCreated",
                        "message": f"Created configurations for {len(applied_configs)} machines",
                    }
                ],
            },
        )
        
        logger.info(f"Successfully started provisioning cluster {name}")

        # Record successful reconciliation
        duration = time.time() - start_time
        cluster_reconcile_duration.labels(
            namespace=namespace, cluster=name
        ).observe(duration)
        record_reconcile_success(namespace, name)

    except kopf.TemporaryError:
        # Record temporary error
        record_reconcile_error(namespace, name, "temporary")
        raise
    except kopf.PermanentError:
        # Record permanent error
        record_reconcile_error(namespace, name, "permanent")
        raise
    except Exception as e:
        logger.error(f"Failed to reconcile KubernetesCluster {name}: {e}")
        record_reconcile_error(namespace, name, "unknown")
        raise kopf.TemporaryError(f"Cluster reconciliation failed: {e}", delay=60)


async def handle_cluster_deletion(cluster_name: str, namespace: str, body: dict):
    """Handle deletion of KubernetesCluster"""
    logger.info(f"Handling deletion of cluster: {cluster_name}")
    
    # Get applied configurations from status
    status = body.get("status", {})
    applied_configs = status.get("appliedMachines", {})
    
    # Delete all NixosConfigurations
    for machine_name, config_name in applied_configs.items():
        try:
            await delete_nixos_configuration(config_name, namespace)
            logger.info(f"Deleted NixosConfiguration: {config_name}")
            record_nixos_config_deleted(namespace, cluster_name)
        except Exception as e:
            logger.warning(f"Failed to delete NixosConfiguration {config_name}: {e}")
    
    # Delete join token secret
    try:
        join_token_secret = f"{cluster_name}-join-token"
        await delete_secret(join_token_secret, namespace)
        logger.info(f"Deleted join token secret: {join_token_secret}")
    except Exception as e:
        logger.warning(f"Failed to delete join token secret: {e}")
    
    # Delete kubeconfig secret (if exists)
    try:
        kubeconfig_secret = f"{cluster_name}-kubeconfig"
        await delete_secret(kubeconfig_secret, namespace)
        logger.info(f"Deleted kubeconfig secret: {kubeconfig_secret}")
    except Exception as e:
        logger.warning(f"Failed to delete kubeconfig secret: {e}")
    
    logger.info(f"Cluster {cluster_name} deletion completed")


async def extract_kubeconfig_from_control_plane(
    control_plane_nodes: List[str], namespace: str
) -> Optional[str]:
    """
    Extract kubeconfig from control plane nodes in a distribution-agnostic way

    Tries multiple standard locations and methods to retrieve kubeconfig:
    1. Standard paths for different k8s distributions
    2. kubectl config view if available
    3. Falls back to placeholder if unable to retrieve
    """
    if not control_plane_nodes:
        return None

    # Standard kubeconfig locations for different distributions
    kubeconfig_paths = [
        "/etc/rancher/k3s/k3s.yaml",           # k3s
        "/var/lib/k0s/pki/admin.conf",         # k0s
        "/etc/kubernetes/admin.conf",          # kubeadm
        "/root/.kube/config",                  # generic
        "/etc/kubernetes/kubeconfig",          # generic
    ]

    # Get machine info to establish SSH connection
    try:
        from clients import get_machine

        # Try first control plane node
        first_cp = control_plane_nodes[0]
        machine = get_machine(first_cp, namespace)

        # Extract connection details
        hostname = machine["spec"].get("hostname") or machine["spec"].get("ipAddress")
        ssh_user = machine["spec"].get("sshUser", "root")
        ssh_key_ref = machine["spec"].get("sshKeySecretRef")

        if not hostname:
            logger.warning(f"No hostname/IP found for machine {first_cp}")
            return None

        # Get SSH key if specified
        ssh_key_path = None
        if ssh_key_ref:
            from clients import get_secret_data
            secret_data = await get_secret_data(ssh_key_ref["name"], namespace)

            if "ssh-privatekey" in secret_data:
                # Write SSH key to temporary file
                import tempfile
                fd, ssh_key_path = tempfile.mkstemp(prefix="nico-ssh-")
                with os.fdopen(fd, 'w') as f:
                    f.write(secret_data["ssh-privatekey"])
                os.chmod(ssh_key_path, 0o600)

        # Try to extract kubeconfig via SSH
        import subprocess

        # Build SSH command base
        ssh_base = ["ssh", "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null"]
        if ssh_key_path:
            ssh_base.extend(["-i", ssh_key_path])
        ssh_base.append(f"{ssh_user}@{hostname}")

        kubeconfig_content = None

        # Try each known kubeconfig path
        for path in kubeconfig_paths:
            try:
                cmd = ssh_base + [f"cat {path}"]
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=10
                )

                if result.returncode == 0 and result.stdout.strip():
                    kubeconfig_content = result.stdout
                    logger.info(f"Found kubeconfig at {path} on {first_cp}")
                    break

            except subprocess.TimeoutExpired:
                logger.warning(f"SSH timeout while checking {path}")
                continue
            except Exception as e:
                logger.debug(f"Failed to read {path}: {e}")
                continue

        # If no file found, try kubectl command
        if not kubeconfig_content:
            try:
                cmd = ssh_base + ["kubectl config view --raw"]
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=10
                )

                if result.returncode == 0 and result.stdout.strip():
                    kubeconfig_content = result.stdout
                    logger.info(f"Retrieved kubeconfig via kubectl on {first_cp}")

            except Exception as e:
                logger.debug(f"Failed to run kubectl: {e}")

        # Cleanup temporary SSH key
        if ssh_key_path:
            try:
                os.unlink(ssh_key_path)
            except:
                pass

        # If we got kubeconfig, process it
        if kubeconfig_content:
            # Try to replace server URL with VIP if available
            # This makes kubeconfig work even if control plane node goes down
            try:
                import yaml
                kubeconfig_data = yaml.safe_load(kubeconfig_content)

                # Get VIP from cluster.nix if available
                # We can infer it from the cluster status or configuration
                # For now, keep original server URL

                return yaml.dump(kubeconfig_data)

            except Exception as e:
                logger.warning(f"Failed to parse kubeconfig: {e}")
                # Return raw content anyway
                return kubeconfig_content

        logger.warning(f"Could not extract kubeconfig from {first_cp}")
        return None

    except Exception as e:
        logger.error(f"Failed to extract kubeconfig: {e}")
        return None


@kopf.timer("nico.homystack.com", "v1alpha1", "kubernetesclusters", interval=30.0)
async def monitor_cluster_status(body, spec, name, namespace, **kwargs):
    """Monitor and update cluster status based on machine states"""
    logger.debug(f"Monitoring cluster status: {name}")

    try:
        status = body.get("status", {})
        applied_configs = status.get("appliedMachines", {})

        if not applied_configs:
            return

        # Count ready machines per role using NixosConfiguration labels
        control_plane_ready = 0
        data_plane_ready = 0
        total_control_plane = 0
        total_data_plane = 0
        ready_control_plane_nodes = []

        for machine_name, config_name in applied_configs.items():
            try:
                # Get configuration to determine role from labels
                config = get_nixos_configuration(config_name, namespace)
                config_labels = config.get("metadata", {}).get("labels", {})
                config_status = config.get("status", {})

                # Determine role from NixosConfiguration labels
                role = config_labels.get("nico.homystack.com/role", "worker")
                is_control_plane = role == "control-plane"

                # Get machine status
                machine = get_machine(machine_name, namespace)

                # Check if configuration is applied and machine is ready
                is_ready = (
                    config_status.get("appliedCommit")
                    and machine.get("status", {}).get("hasConfiguration")
                )

                if is_ready:
                    if is_control_plane:
                        control_plane_ready += 1
                        ready_control_plane_nodes.append(machine_name)
                    else:
                        data_plane_ready += 1

                # Count totals
                if is_control_plane:
                    total_control_plane += 1
                else:
                    total_data_plane += 1

            except Exception as e:
                logger.warning(f"Failed to check status for {machine_name}: {e}")
                continue

        # Determine cluster phase
        phase = "Provisioning"
        all_control_plane_ready = (
            control_plane_ready == total_control_plane and control_plane_ready > 0
        )
        all_workers_ready = (
            data_plane_ready == total_data_plane and total_data_plane > 0
        ) or total_data_plane == 0

        if all_control_plane_ready and all_workers_ready:
            phase = "Ready"
        elif all_control_plane_ready:
            phase = "ControlPlaneReady"

        # Generate kubeconfig if control plane is ready and kubeconfig doesn't exist
        kubeconfig_secret_name = f"{name}-kubeconfig"
        if all_control_plane_ready:
            try:
                # Check if secret already exists
                from kubernetes.client.rest import ApiException

                try:
                    from clients import core_v1

                    core_v1.read_namespaced_secret(kubeconfig_secret_name, namespace)
                except ApiException as e:
                    if e.status == 404:
                        # Secret doesn't exist, create it
                        kubeconfig = await extract_kubeconfig_from_control_plane(
                            ready_control_plane_nodes, namespace
                        )
                        if kubeconfig:
                            await create_secret(
                                kubeconfig_secret_name,
                                namespace,
                                {"kubeconfig": kubeconfig},
                            )
                            logger.info(
                                f"Created kubeconfig secret: {kubeconfig_secret_name}"
                            )
                            record_kubeconfig_generated(namespace, name, True)
                    else:
                        raise
            except Exception as e:
                logger.warning(f"Failed to create kubeconfig secret: {e}")
                record_kubeconfig_generated(namespace, name, False)

        # Update cluster status
        status_update = {
            "phase": phase,
            "controlPlaneReady": f"{control_plane_ready}/{total_control_plane}",
            "dataPlaneReady": f"{data_plane_ready}/{total_data_plane}",
            "kubeconfigSecret": kubeconfig_secret_name,
            "conditions": [
                {
                    "type": "Ready",
                    "status": "True" if phase == "Ready" else "False",
                    "lastTransitionTime": datetime.utcnow().isoformat() + "Z",
                    "reason": "AllNodesReady" if phase == "Ready" else phase,
                    "message": f"Control plane: {control_plane_ready}/{total_control_plane}, Workers: {data_plane_ready}/{total_data_plane}",
                }
            ],
        }

        await update_cluster_status(name, namespace, status_update)

        # Update Prometheus metrics
        update_cluster_metrics(namespace, name, status_update)

    except Exception as e:
        logger.error(f"Failed to monitor cluster {name} status: {e}")
