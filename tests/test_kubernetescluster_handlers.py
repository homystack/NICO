#!/usr/bin/env python3
"""
Unit tests for KubernetesCluster handlers
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kubernetescluster_handlers import (
    select_machines_for_cluster,
    generate_cluster_config,
)


class TestMachineSelection:
    """Tests for machine selection logic"""

    @pytest.mark.asyncio
    async def test_select_explicit_machines(self):
        """Test selection with explicit machines list"""
        cluster_spec = {
            "controlPlane": {
                "machines": ["cp-01", "cp-02", "cp-03"],
                "machineSelector": {"matchLabels": {"role": "control-plane"}},
                "count": 5,
            }
        }

        result = await select_machines_for_cluster(
            cluster_spec, "default", "controlPlane"
        )

        assert result == ["cp-01", "cp-02", "cp-03"]
        assert len(result) == 3

    @pytest.mark.asyncio
    @patch("kubernetescluster_handlers.list_machines")
    async def test_select_machines_by_selector(self, mock_list_machines):
        """Test selection with machineSelector and count"""
        mock_list_machines.return_value = [
            {
                "metadata": {
                    "name": "worker-01",
                    "labels": {"role": "worker", "env": "prod"},
                },
                "status": {"hasConfiguration": False},
            },
            {
                "metadata": {
                    "name": "worker-02",
                    "labels": {"role": "worker", "env": "prod"},
                },
                "status": {"hasConfiguration": False},
            },
            {
                "metadata": {
                    "name": "worker-03",
                    "labels": {"role": "worker", "env": "prod"},
                },
                "status": {"hasConfiguration": True},  # Already configured
            },
            {
                "metadata": {
                    "name": "control-01",
                    "labels": {"role": "control-plane", "env": "prod"},
                },
                "status": {"hasConfiguration": False},
            },
        ]

        cluster_spec = {
            "dataPlane": {
                "machineSelector": {"matchLabels": {"role": "worker"}},
                "count": 2,
            }
        }

        result = await select_machines_for_cluster(
            cluster_spec, "default", "dataPlane"
        )

        # Should select 2 workers that don't have configuration
        assert len(result) == 2
        assert "worker-01" in result
        assert "worker-02" in result
        assert "worker-03" not in result  # Has configuration

    @pytest.mark.asyncio
    @patch("kubernetescluster_handlers.list_machines")
    async def test_select_no_available_machines(self, mock_list_machines):
        """Test selection when no machines are available"""
        mock_list_machines.return_value = [
            {
                "metadata": {"name": "worker-01", "labels": {"role": "worker"}},
                "status": {"hasConfiguration": True},  # Already configured
            }
        ]

        cluster_spec = {
            "dataPlane": {
                "machineSelector": {"matchLabels": {"role": "worker"}},
                "count": 1,
            }
        }

        result = await select_machines_for_cluster(
            cluster_spec, "default", "dataPlane"
        )

        assert len(result) == 0


class TestClusterConfig:
    """Tests for cluster configuration generation"""

    def test_generate_cluster_config(self):
        """Test cluster.nix generation"""
        control_plane_nodes = ["cp-01", "cp-02"]
        worker_nodes = ["worker-01", "worker-02", "worker-03"]
        machines_info = {
            "cp-01": {"hostname": "cp-01.local", "ipAddress": "192.168.1.10"},
            "cp-02": {"hostname": "cp-02.local", "ipAddress": "192.168.1.11"},
            "worker-01": {"hostname": "worker-01.local", "ipAddress": "192.168.1.20"},
            "worker-02": {"hostname": "worker-02.local", "ipAddress": "192.168.1.21"},
            "worker-03": {"hostname": "worker-03.local", "ipAddress": "192.168.1.22"},
        }

        result = generate_cluster_config(
            "test-cluster", control_plane_nodes, worker_nodes, machines_info
        )

        # Check that result is valid Nix code
        assert "cluster = {" in result
        assert 'name = "test-cluster"' in result
        assert "controlPlane =" in result
        assert "workers =" in result

        # Check IP addresses are included
        assert "192.168.1.10" in result
        assert "192.168.1.20" in result

        # Check node names are included
        assert "cp-01" in result
        assert "worker-01" in result

    def test_generate_cluster_config_empty_workers(self):
        """Test cluster.nix generation with no workers"""
        control_plane_nodes = ["cp-01"]
        worker_nodes = []
        machines_info = {
            "cp-01": {"hostname": "cp-01.local", "ipAddress": "192.168.1.10"}
        }

        result = generate_cluster_config(
            "test-cluster", control_plane_nodes, worker_nodes, machines_info
        )

        assert "cluster = {" in result
        assert 'name = "test-cluster"' in result
        assert "workers = [" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
