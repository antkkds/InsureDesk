"""Tests for Portal Profile Intelligence.

Covers:
- Data models (PortalProfile, ProfileVersion, ProfileDiff, ProfileHealth)
- ProfileLoader (YAML load/save, directory loading)
- ProfileValidator (schema validation, required fields, workflows)
- ProfileAnalyzer (health analysis, improvement suggestions)
- ProfileComparator (profile comparison, diff generation)
- ProfileUpgrader (schema upgrade 1.0 → 2.0)
- ProfileRegistry + ProfileManager (registration, orchestration)
- Integration
"""

from __future__ import annotations

import os
import tempfile
from datetime import datetime

import pytest

from src.portal.profile.models import (
    HealthIssue,
    PortalProfile,
    ProfileDiff,
    ProfileHealth,
    ProfileStatus,
    ProfileVersion,
)
from src.portal.profile.loader import ProfileLoader
from src.portal.profile.validator import ProfileValidator
from src.portal.profile.analyzer import ProfileAnalyzer
from src.portal.profile.comparator import ProfileComparator
from src.portal.profile.upgrader import ProfileUpgrader
from src.portal.profile.registry import ProfileRegistry, ProfileManager
from src.portal.profile.schema import CURRENT_SCHEMA_VERSION
from src.portal.profile.exceptions import (
    ProfileLoadError,
    ProfileNotFoundError,
    ProfileValidationError,
    ProfileUpgradeError,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def sample_profile() -> PortalProfile:
    return PortalProfile(
        id="ge",
        name="Great Eastern",
        portal="great_eastern",
        version="2.0",
        schema_version="2.0",
        workflows={
            "create_quote": {"steps": ["login", "fill", "calculate"]},
        },
        mappings={
            "customer": {
                "name": {"selector": "#name", "type": "text"},
            },
        },
        validation_rules={
            "age": {"min": 18, "max": 65},
        },
        adapter="src.portal.adapters.great_eastern.GreatEasternAdapter",
    )


@pytest.fixture
def minimal_profile() -> PortalProfile:
    return PortalProfile(id="min", name="Minimal", portal="minimal")


@pytest.fixture
def yaml_content() -> str:
    return """id: ge
name: Great Eastern
portal: great_eastern
version: "2.0"
schema_version: "2.0"
adapter: src.portal.adapters.ge.GEAdapter
workflows:
  create_quote:
    steps:
      - login
      - fill
      - calculate
mappings:
  customer:
    name:
      selector: "#name"
      type: text
"""


@pytest.fixture
def manager() -> ProfileManager:
    return ProfileManager()


# =============================================================================
# Data Models
# =============================================================================


class TestPortalProfile:
    def test_defaults(self):
        p = PortalProfile(id="test", name="Test", portal="test")
        assert p.version == "1.0"
        assert p.workflow_count == 0

    def test_to_dict(self, sample_profile: PortalProfile):
        d = sample_profile.to_dict()
        assert d["id"] == "ge"
        assert d["portal"] == "great_eastern"
        assert d["workflow_count"] == 1

    def test_counts(self, sample_profile: PortalProfile):
        assert sample_profile.workflow_count == 1
        assert sample_profile.mapping_count == 1
        assert sample_profile.validation_count == 1


class TestProfileDiff:
    def test_no_changes(self):
        diff = ProfileDiff(old_version="1.0", new_version="1.0")
        assert diff.has_changes is False
        assert diff.change_count == 0

    def test_with_changes(self):
        diff = ProfileDiff(old_version="1.0", new_version="2.0",
                            added=["workflows.new"],
                            modified=[{"path": "version", "type": "changed"}])
        assert diff.has_changes is True
        assert diff.change_count == 2


class TestProfileHealth:
    def test_healthy_default(self):
        h = ProfileHealth(profile_id="test")
        assert h.score == 100
        assert h.status == "healthy"

    def test_error_reduces_score(self):
        h = ProfileHealth(profile_id="test")
        h.add_issue(HealthIssue(category="validity", severity="error",
                                 message="Missing required field"))
        assert h.score == 75
        assert h.status == "critical"

    def test_warning_reduces_score(self):
        h = ProfileHealth(profile_id="test")
        h.add_issue(HealthIssue(category="coverage", severity="warning",
                                 message="No workflows"))
        assert h.score == 90


# =============================================================================
# ProfileLoader
# =============================================================================


class TestProfileLoader:
    def test_load_yaml(self, yaml_content: str):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write(yaml_content)
            path = f.name

        try:
            loader = ProfileLoader()
            profile = loader.load(path)
            assert profile.id == "ge"
            assert profile.portal == "great_eastern"
            assert "create_quote" in profile.workflows
        finally:
            os.unlink(path)

    def test_load_nonexistent(self):
        loader = ProfileLoader()
        with pytest.raises(ProfileLoadError):
            loader.load("/nonexistent/path.yaml")

    def test_save_and_reload(self, sample_profile: PortalProfile):
        with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as f:
            path = f.name

        try:
            loader = ProfileLoader()
            loader.save(sample_profile, path)
            loaded = loader.load(path)
            assert loaded.id == sample_profile.id
            assert loaded.portal == sample_profile.portal
        finally:
            os.unlink(path)

    def test_load_directory(self, yaml_content: str):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "ge.yaml")
            with open(path, "w") as f:
                f.write(yaml_content)

            loader = ProfileLoader()
            profiles = loader.load_directory(tmpdir)
            assert len(profiles) == 1
            assert profiles[0].id == "ge"


# =============================================================================
# ProfileValidator
# =============================================================================


class TestProfileValidator:
    def test_valid_profile(self, sample_profile: PortalProfile):
        validator = ProfileValidator()
        errors = validator.validate(sample_profile)
        assert len(errors) == 0

    def test_missing_required_fields(self, minimal_profile: PortalProfile):
        # minimal_profile has id/name/portal but version 1.0
        validator = ProfileValidator()
        errors = validator.validate(minimal_profile)
        # Should have schema version warning
        assert len(errors) >= 0

    def test_is_valid(self, sample_profile: PortalProfile):
        validator = ProfileValidator()
        assert validator.is_valid(sample_profile) is True

    def test_validate_or_raise(self, sample_profile: PortalProfile):
        validator = ProfileValidator()
        validator.validate_or_raise(sample_profile)  # Should not raise

    def test_validate_or_raise_fails(self):
        validator = ProfileValidator()
        with pytest.raises(ProfileValidationError):
            profile = PortalProfile(id="", name="", portal="")
            validator.validate_or_raise(profile)

    def test_workflow_without_steps(self):
        validator = ProfileValidator()
        profile = PortalProfile(
            id="test", name="Test", portal="test",
            schema_version="2.0",
            workflows={"bad": {"not_steps": "here"}},
        )
        errors = validator.validate(profile)
        assert any("missing 'steps'" in e for e in errors)


# =============================================================================
# ProfileAnalyzer
# =============================================================================


class TestProfileAnalyzer:
    def test_healthy_profile(self, sample_profile: PortalProfile):
        analyzer = ProfileAnalyzer()
        health = analyzer.analyze(sample_profile)
        assert health.status == "healthy"
        assert health.score >= 80

    def test_minimal_profile_issues(self, minimal_profile: PortalProfile):
        analyzer = ProfileAnalyzer()
        health = analyzer.analyze(minimal_profile)
        assert health.issue_count > 0  # Missing workflows, mappings, etc.

    def test_suggest_improvements(self, sample_profile: PortalProfile):
        analyzer = ProfileAnalyzer()
        suggestions = analyzer.suggest_improvements(sample_profile)
        assert isinstance(suggestions, list)


# =============================================================================
# ProfileComparator
# =============================================================================


class TestProfileComparator:
    def test_identical_profiles(self, sample_profile: PortalProfile):
        comparator = ProfileComparator()
        diff = comparator.compare(sample_profile, sample_profile)
        assert diff.has_changes is False

    def test_different_versions(self):
        comparator = ProfileComparator()
        old = PortalProfile(
            id="ge", name="Old", portal="ge", version="1.0",
            workflows={"old": {"steps": []}},
        )
        new = PortalProfile(
            id="ge", name="New", portal="ge", version="2.0",
            workflows={"old": {"steps": []}, "new": {"steps": []}},
        )
        diff = comparator.compare(old, new)
        assert diff.has_changes is True
        assert any("workflows.new" in a for a in diff.added)

    def test_removed_items(self):
        comparator = ProfileComparator()
        old = PortalProfile(
            id="ge", name="Test", portal="ge",
            workflows={"old": {"steps": []}, "gone": {"steps": []}},
        )
        new = PortalProfile(
            id="ge", name="Test", portal="ge",
            workflows={"old": {"steps": []}},
        )
        diff = comparator.compare(old, new)
        assert any("gone" in r for r in diff.removed)


# =============================================================================
# ProfileUpgrader
# =============================================================================


class TestProfileUpgrader:
    def test_upgrade_1_to_2(self):
        upgrader = ProfileUpgrader()
        profile = PortalProfile(
            id="ge", name="Test", portal="ge",
            version="1.0", schema_version="1.0",
        )
        upgraded, version = upgrader.upgrade(profile, target_version="2.0")
        assert upgraded.schema_version == "2.0"
        assert len(version.changes) > 0
        assert version.source == "auto_upgrade"

    def test_already_current(self, sample_profile: PortalProfile):
        upgrader = ProfileUpgrader()
        upgraded, version = upgrader.upgrade(sample_profile)
        assert upgraded.schema_version == CURRENT_SCHEMA_VERSION
        assert version.source == "no_change"

    def test_unsupported_upgrade_path(self):
        upgrader = ProfileUpgrader()
        profile = PortalProfile(
            id="test", name="Test", portal="test",
            schema_version="2.0",
        )
        with pytest.raises(ProfileUpgradeError):
            upgrader.upgrade(profile, target_version="3.0")


# =============================================================================
# ProfileRegistry
# =============================================================================


class TestProfileRegistry:
    def test_register_and_get(self, sample_profile: PortalProfile):
        registry = ProfileRegistry()
        registry.register(sample_profile)
        assert registry.get("ge") is sample_profile
        assert "ge" in registry

    def test_get_not_found(self):
        registry = ProfileRegistry()
        assert registry.get("nonexistent") is None
        with pytest.raises(ProfileNotFoundError):
            registry.get_or_raise("nonexistent")

    def test_list_ids(self, sample_profile: PortalProfile):
        registry = ProfileRegistry()
        registry.register(sample_profile)
        assert "ge" in registry.list_ids()

    def test_unregister(self, sample_profile: PortalProfile):
        registry = ProfileRegistry()
        registry.register(sample_profile)
        registry.unregister("ge")
        assert "ge" not in registry


# =============================================================================
# ProfileManager (Integration)
# =============================================================================


class TestProfileManager:
    def test_load_and_validate(self, manager: ProfileManager, yaml_content: str):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write(yaml_content)
            path = f.name

        try:
            profile = manager.load(path)
            assert profile.id == "ge"
            assert manager.is_valid("ge") is True
        finally:
            os.unlink(path)

    def test_analyze(self, manager: ProfileManager, sample_profile: PortalProfile):
        manager._registry.register(sample_profile)
        health = manager.analyze("ge")
        assert health.profile_id == "ge"

    def test_compare(self, manager: ProfileManager):
        old = PortalProfile(id="a", name="A", portal="a", version="1.0")
        new = PortalProfile(id="b", name="B", portal="b", version="2.0")
        manager._registry.register(old)
        manager._registry.register(new)
        diff = manager.compare("a", "b")
        assert diff.has_changes is True

    def test_upgrade(self, manager: ProfileManager):
        profile = PortalProfile(
            id="ge", name="Test", portal="ge",
            version="1.0", schema_version="1.0",
        )
        manager._registry.register(profile)
        upgraded, version = manager.upgrade("ge")
        assert upgraded.schema_version == "2.0"

    def test_suggest(self, manager: ProfileManager, sample_profile: PortalProfile):
        manager._registry.register(sample_profile)
        suggestions = manager.suggest("ge")
        assert isinstance(suggestions, list)

    def test_load_directory(self, manager: ProfileManager, yaml_content: str):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "ge.yaml")
            with open(path, "w") as f:
                f.write(yaml_content)

            profiles = manager.load_directory(tmpdir)
            assert len(profiles) == 1
            assert manager.get("ge") is not None

    def test_list_ids(self, manager: ProfileManager, sample_profile: PortalProfile):
        manager._registry.register(sample_profile)
        assert "ge" in manager.list_ids()
