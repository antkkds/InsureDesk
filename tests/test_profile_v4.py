"""Tests: Multi Portal Profile Management (Sprint 5.4).

Tests for version management, rollback, activate/deactivate,
migration history, and health monitoring.
"""
from __future__ import annotations

import os
import sys
import json
import tempfile
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ══════════════════════════════════════════════════════════════════
# 1. Version Manager (8 tests)
# ══════════════════════════════════════════════════════════════════

class TestVersionManager:
    """Tests for VersionManager."""

    @pytest.fixture
    def vm(self):
        from src.portal.profile.versioning import VersionManager
        with tempfile.TemporaryDirectory() as tmp:
            yield VersionManager(versions_dir=tmp)

    @pytest.fixture
    def sample_profile(self):
        from src.portal.profile.models import PortalProfile
        return PortalProfile(
            id="great_eastern",
            name="Great Eastern",
            portal="great_eastern",
            version="2.0",
            workflows={
                "login": {"steps": ["navigate", "fill", "submit"]},
                "search": {"steps": ["navigate", "fill", "extract"]},
            },
            mappings={
                "login.username": "input[name='user']",
                "login.password": "#password",
            },
        )

    def test_create_version(self, vm, sample_profile):
        version = vm.create_version(sample_profile, "Initial version")
        assert version["version_id"].startswith("v")
        assert version["profile_id"] == "great_eastern"
        assert version["description"] == "Initial version"
        assert "profile_snapshot" in version

    def test_list_versions(self, vm, sample_profile):
        vm.create_version(sample_profile, "v1")
        vm.create_version(sample_profile, "v2")
        versions = vm.list_versions("great_eastern")
        assert len(versions) == 2
        assert versions[0]["description"] in ("v1", "v2")

    def test_list_versions_empty(self, vm):
        versions = vm.list_versions("nonexistent")
        assert versions == []

    def test_load_version(self, vm, sample_profile):
        v = vm.create_version(sample_profile, "test load")
        loaded = vm.load_version("great_eastern", v["version_id"])
        assert loaded is not None
        assert loaded["description"] == "test load"

    def test_delete_version(self, vm, sample_profile):
        v = vm.create_version(sample_profile, "to delete")
        assert vm.delete_version("great_eastern", v["version_id"]) is True
        assert vm.load_version("great_eastern", v["version_id"]) is None

    def test_rollback(self, vm, sample_profile):
        v = vm.create_version(sample_profile, "original")
        # Change the profile
        sample_profile.version = "3.0"
        vm.create_version(sample_profile, "updated")
        # Rollback to original
        restored = vm.rollback("great_eastern", v["version_id"])
        assert restored.id == "great_eastern"
        assert restored.version == "2.0"  # Original version

    def test_rollback_nonexistent_raises(self, vm):
        from src.portal.profile.exceptions import ProfileNotFoundError
        with pytest.raises(ProfileNotFoundError):
            vm.rollback("nonexistent", "v_bad")

    def test_compare_versions(self, vm, sample_profile):
        v1 = vm.create_version(sample_profile, "v1")
        # Add a workflow
        sample_profile.workflows["new_wf"] = {"steps": []}
        v2 = vm.create_version(sample_profile, "v2")
        diff = vm.compare_versions("great_eastern", v1["version_id"], v2["version_id"])
        assert diff["change_count"] >= 1
        assert any(c["type"] == "workflow_added" for c in diff["changes"])


# ══════════════════════════════════════════════════════════════════
# 2. Activate / Deactivate (4 tests)
# ══════════════════════════════════════════════════════════════════

class TestActivateDeactivate:
    """Tests for profile activate/deactivate."""

    @pytest.fixture
    def vm(self):
        from src.portal.profile.versioning import VersionManager
        with tempfile.TemporaryDirectory() as tmp:
            yield VersionManager(versions_dir=tmp)

    def test_activate_profile(self, vm):
        vm.activate("great_eastern")
        assert vm.is_active("great_eastern") is True

    def test_activate_with_version(self, vm):
        vm.activate("great_eastern", "v_abc123")
        assert vm.is_active("great_eastern") is True
        assert vm.get_active_version("great_eastern") == "v_abc123"

    def test_deactivate_profile(self, vm):
        vm.activate("great_eastern")
        vm.deactivate("great_eastern")
        assert vm.is_active("great_eastern") is False

    def test_not_active_by_default(self, vm):
        assert vm.is_active("new_portal") is False
        assert vm.get_active_version("new_portal") is None


# ══════════════════════════════════════════════════════════════════
# 3. Migration History (3 tests)
# ══════════════════════════════════════════════════════════════════

class TestMigrationHistory:
    """Tests for migration history tracking."""

    @pytest.fixture
    def vm(self):
        from src.portal.profile.versioning import VersionManager
        with tempfile.TemporaryDirectory() as tmp:
            yield VersionManager(versions_dir=tmp)

    def test_log_migration(self, vm):
        entry = vm.log_migration("great_eastern", "1.0", "2.0", "Upgraded schema")
        assert entry["migration_id"].startswith("m")
        assert entry["from_version"] == "1.0"
        assert entry["to_version"] == "2.0"

    def test_get_migration_history(self, vm):
        vm.log_migration("ge", "1.0", "1.1", "Patch")
        vm.log_migration("ge", "1.1", "2.0", "Major upgrade")
        history = vm.get_migration_history("ge")
        assert len(history) == 2

    def test_empty_history(self, vm):
        assert vm.get_migration_history("new_portal") == []


# ══════════════════════════════════════════════════════════════════
# 4. Health Monitoring (2 tests)
# ══════════════════════════════════════════════════════════════════

class TestHealthMonitoring:
    """Tests for cross-profile health monitoring."""

    @pytest.fixture
    def vm(self):
        from src.portal.profile.versioning import VersionManager
        with tempfile.TemporaryDirectory() as tmp:
            yield VersionManager(versions_dir=tmp)

    @pytest.fixture
    def profiles(self):
        from src.portal.profile.models import PortalProfile
        return [
            PortalProfile(id="ge", name="Great Eastern", portal="great_eastern", version="2.0"),
            PortalProfile(id="aia", name="AIA Malaysia", portal="aia", version="1.0"),
        ]

    def test_monitor_all(self, vm, profiles):
        vm.activate("ge")
        results = vm.monitor_all(profiles)
        assert "ge" in results
        assert "aia" in results
        assert results["ge"]["active"] is True
        assert results["aia"]["active"] is False

    def test_monitor_all_counts(self, vm, profiles):
        for p in profiles:
            vm.create_version(p)
        vm.activate("ge")
        results = vm.monitor_all(profiles)
        assert results["ge"]["version_count"] == 1
        assert results["aia"]["version_count"] == 1


# ══════════════════════════════════════════════════════════════════
# 5. ProfileManager Enhancement (6 tests)
# ══════════════════════════════════════════════════════════════════

class TestProfileManagerV4:
    """Tests for ProfileManager Sprint 5.4 enhancements."""

    @pytest.fixture
    def manager(self):
        from src.portal.profile.registry import ProfileManager
        from src.portal.profile.versioning import VersionManager
        import tempfile
        tmp = tempfile.TemporaryDirectory()

        class ManagedManager(ProfileManager):
            def __init__(self):
                vm = VersionManager(versions_dir=tmp.name)
                super().__init__(versioning=vm)
                self._tmp = tmp

        return ManagedManager()

    def test_create_version_via_manager(self, manager):
        from src.portal.profile.loader import ProfileLoader
        loader = ProfileLoader()
        path = os.path.join(os.path.dirname(__file__), "..", "portals", "great_eastern.yaml")
        profile = loader.load(path)
        manager._registry.register(profile)
        # Use the actual profile ID from the loaded YAML
        version = manager.create_version(profile.id, "test version")
        assert "version_id" in version
        assert version["profile_id"] == profile.id

    def test_list_versions_via_manager(self, manager):
        from src.portal.profile.models import PortalProfile
        p = PortalProfile(id="test", name="Test", portal="test")
        manager._registry.register(p)
        manager.create_version("test", "v1")
        manager.create_version("test", "v2")
        versions = manager.list_versions("test")
        assert len(versions) == 2

    def test_activate_via_manager(self, manager):
        manager.activate("great_eastern")
        assert manager.is_active("great_eastern") is True

    def test_deactivate_via_manager(self, manager):
        manager.activate("great_eastern")
        manager.deactivate("great_eastern")
        assert manager.is_active("great_eastern") is False

    def test_migration_history_via_manager(self, manager):
        entry = manager.log_migration("ge", "1.0", "2.0", "test")
        assert entry["from_version"] == "1.0"
        history = manager.get_migration_history("ge")
        assert len(history) == 1

    def test_monitor_all_via_manager(self, manager):
        from src.portal.profile.models import PortalProfile
        manager._registry.register(PortalProfile(id="ge", name="GE", portal="ge"))
        manager._registry.register(PortalProfile(id="aia", name="AIA", portal="aia"))
        manager.activate("ge")
        results = manager.monitor_all()
        assert "ge" in results
        assert "aia" in results
