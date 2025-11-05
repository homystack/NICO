#!/usr/bin/env python3
"""
Unit tests for Prometheus metrics
"""

import pytest
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from metrics import (
    record_reconcile_success,
    record_reconcile_error,
    record_nixos_config_created,
    update_cluster_metrics,
)


class TestMetrics:
    """Tests for metrics recording"""

    def test_record_reconcile_success(self):
        """Test recording successful reconciliation"""
        # Should not raise exception
        record_reconcile_success("default", "test-cluster")

    def test_record_reconcile_error(self):
        """Test recording reconciliation error"""
        # Should not raise exception
        record_reconcile_error("default", "test-cluster", "temporary")
        record_reconcile_error("default", "test-cluster", "permanent")

    def test_record_nixos_config_created(self):
        """Test recording NixosConfiguration creation"""
        # Should not raise exception
        record_nixos_config_created("default", "test-cluster", "control-plane")
        record_nixos_config_created("default", "test-cluster", "worker")

    def test_update_cluster_metrics(self):
        """Test updating cluster metrics"""
        status = {
            "phase": "Ready",
            "controlPlaneReady": "3/3",
            "dataPlaneReady": "5/5",
        }

        # Should not raise exception
        update_cluster_metrics("default", "test-cluster", status)

    def test_update_cluster_metrics_invalid_format(self):
        """Test updating cluster metrics with invalid format"""
        status = {
            "phase": "Provisioning",
            "controlPlaneReady": "invalid",
            "dataPlaneReady": "also-invalid",
        }

        # Should handle invalid format gracefully
        update_cluster_metrics("default", "test-cluster", status)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
