"""PA-8.1/8.2 tests — IdentityData contract + IdentityRequirements.

ChatGPT (2026-08-16):
- IdentityData is the canonical Domain Layer model (NOT PA-specific), minimal
  fields only, no product concerns (occupation/plan/vehicle/premium/...).
- IdentityRequirements are profile-driven: PA ≠ Motor field requirements.
"""

from __future__ import annotations

from datetime import date

import pytest

from src.identity.errors import IdentityRequirementError
from src.identity.models import ID_TYPES, IdentityData
from src.identity.requirements import (
    IdentityRequirements,
    motor_requirements,
    pa_requirements,
)


# ══════════════════════════════════════════════════════════════════════
# IdentityData canonical model
# ══════════════════════════════════════════════════════════════════════


class TestIdentityDataModel:
    def test_minimal_canonical_fields(self):
        d = IdentityData(id_number="900101-14-1232", full_name="ALI BIN AHMAD")
        assert d.id_type == "NRIC"
        assert d.id_number == "900101-14-1232"
        assert d.full_name == "ALI BIN AHMAD"
        assert d.dob is None
        assert d.gender == ""
        assert d.nationality is None

    def test_forbidden_product_fields_do_not_exist(self):
        """The canonical model carries NO product concerns."""
        d = IdentityData(id_number="x")
        for field in ("occupation", "plan", "vehicle", "premium", "insurer", "portal"):
            assert not hasattr(d, field), f"IdentityData must not have {field}"

    def test_serialization_roundtrip(self):
        d = IdentityData(
            id_type="NRIC", id_number="900101-14-1232",
            full_name="ALI BIN AHMAD", dob=date(1990, 1, 1), gender="F",
            nationality="MALAYSIAN",
        )
        d2 = IdentityData.from_dict(d.to_dict())
        assert d2 == d

    def test_from_dict_tolerates_missing(self):
        d = IdentityData.from_dict({"id_number": "900101141232"})
        assert d.id_type == "NRIC"
        assert d.id_number == "900101141232"
        assert d.dob is None

    def test_from_dict_parses_dob_formats(self):
        for raw in ("1990-01-01", "01 Jan 1990", "01/01/1990"):
            d = IdentityData.from_dict({"id_number": "x", "dob": raw})
            assert d.dob == date(1990, 1, 1), f"format {raw}"

    def test_bool_is_id_number_presence(self):
        assert bool(IdentityData(id_number="900101-14-1232")) is True
        assert bool(IdentityData(id_number="")) is False

    def test_id_types(self):
        assert "NRIC" in ID_TYPES
        assert "PASSPORT" in ID_TYPES


# ══════════════════════════════════════════════════════════════════════
# IdentityRequirements — profile-driven, product-specific
# ══════════════════════════════════════════════════════════════════════


class TestIdentityRequirements:
    def test_pa_profile_requires_id_dob_gender(self):
        req = pa_requirements()
        assert req.product == "pa"
        # G4 (Review #3): full_name added — PA completeness now profile-driven
        assert req.required == ["id_number", "dob", "gender", "full_name"]

    def test_motor_profile_requires_id_name(self):
        req = motor_requirements()
        assert req.product == "motor"
        assert req.required == ["id_number", "full_name"]

    def test_pa_and_motor_requirements_differ(self):
        """The whole point: shared IdentityData, per-product requirements."""
        assert pa_requirements().required != motor_requirements().required

    def test_check_passes_when_satisfied(self):
        req = pa_requirements()
        identity = IdentityData(
            id_number="900101-14-1232", dob=date(1990, 1, 1), gender="F",
            full_name="TEST APPLICANT",
        )
        assert req.check_optional(identity) == []

    def test_check_raises_on_missing(self):
        req = pa_requirements()
        identity = IdentityData(id_number="900101-14-1232")  # no dob/gender
        missing = req.check_optional(identity)
        assert "dob" in missing
        assert "gender" in missing
        with pytest.raises(IdentityRequirementError) as ei:
            req.check(identity)
        assert "dob" in ei.value.message

    def test_motor_requirement_missing_name(self):
        req = motor_requirements()
        identity = IdentityData(id_number="881212145678")  # no full_name
        assert "full_name" in req.check_optional(identity)

    def test_none_requirements(self):
        req = IdentityRequirements.none("fire")
        assert req.required == []
        assert req.check_optional(IdentityData(id_number="x")) == []

    def test_loaded_from_disk_profiles(self):
        """Requirements come from the binding YAMLs, not hardcoded."""
        import os

        for profile in ("src/portal/forms/pa_easi_protector.yaml",
                        "src/portal/forms/motor_private_car.yaml"):
            assert os.path.exists(profile)
            req = IdentityRequirements.from_profile(profile)
            assert req.required, f"no identity_requirements in {profile}"


# ══════════════════════════════════════════════════════════════════════
# PA-8.2 — Capability wiring (ChatGPT's 6 acceptance tests)
# ══════════════════════════════════════════════════════════════════════

from src.contracts.gears import MotorProductCapability, PaProductCapability


def _pa_args(**overrides) -> dict:
    args = {
        "execution_mode": "real",
        "coverage_type": "individual",
        "occupation": "MANAGER",
        "applicant": {
            "id_type": "NRIC",
            "id_number": "900101-14-1232",
            "full_name": "TEST APPLICANT",
            "dob": "1990-01-01",
            "gender": "F",
            "mobile": "0123456789",
            "email": "test.applicant@gmail.com",
            "address1": "12, JALAN MERDEKA",
            "state": "KUALA LUMPUR",
        },
        "plan": "EP1",
    }
    args.update(overrides)
    return args


def _motor_args(**overrides) -> dict:
    args = {
        "execution_mode": "real",
        "vehicle_number": "VDL 1987",
        "place": "KUALA LUMPUR",
        "id_number": "881212145678",
        "full_name": "Fionn Liang",
        "mobile": "0123456789",
        "email": "fionn.liang@gmail.com",
        "address1": "12, Jalan Merdeka",
        "marital_status": "Single",
        "years_driving_exp": "5",
    }
    args.update(overrides)
    return args


class TestCapabilityWiring:
    """ChatGPT PA-8.2 acceptance: PA + Motor share the same identity
    validation mechanism; required fields declared per binding."""

    def test_1_pa_requirements_from_pa_yaml(self):
        cap = PaProductCapability()
        req = IdentityRequirements.from_binding(cap.binding)
        # G4 (Review #3): full_name added — PA completeness now profile-driven
        assert req.required == ["id_number", "dob", "gender", "full_name"]

    def test_2_motor_requirements_from_motor_yaml(self):
        cap = MotorProductCapability()
        req = IdentityRequirements.from_binding(cap.binding)
        assert req.required == ["id_number", "full_name"]

    def test_3_missing_pa_gender_fails(self):
        cap = PaProductCapability()
        vr = cap.validate(_pa_args(applicant={
            "id_type": "NRIC", "id_number": "900101-14-1232",
            "full_name": "TEST", "dob": "1990-01-01",  # gender missing
        }))
        assert not vr.valid
        assert vr.code == "IDENTITY_REQUIREMENT_MISSING"
        assert "gender" in vr.message

    def test_4_missing_motor_full_name_fails(self):
        cap = MotorProductCapability()
        vr = cap.validate(_motor_args(full_name=""))
        assert not vr.valid
        # full_name is required by BOTH ProfileGate (request_schema) and the
        # identity gate; ProfileGate wins when it fires first. Either way the
        # request is rejected before the portal is touched.
        assert vr.code in ("MISSING_REQUIRED_FIELD", "IDENTITY_REQUIREMENT_MISSING")
        assert "full_name" in vr.message

    def test_5_invalid_identity_portal_never_touched(self, monkeypatch):
        """Invalid identity → structured failure, runner never invoked."""
        pa = PaProductCapability()
        called = []

        async def runner(payload, log, cdp_url="http://127.0.0.1:9333"):
            called.append(True)
            return {"ok": True}

        monkeypatch.setattr("src.quote.pa_adapter.run_pa_quote_via_cdp", runner)
        vr = pa.validate(_pa_args(applicant={
            "id_type": "NRIC", "id_number": "123",  # invalid format
            "full_name": "TEST", "dob": "1990-01-01", "gender": "M",
        }))
        assert not vr.valid
        assert called == []

        motor = MotorProductCapability()
        vr = motor.validate(_motor_args(id_number="12345"))  # bad format
        assert not vr.valid
        assert called == []

    def test_6_yaml_change_changes_validation_without_python(self, tmp_path):
        """Declarative proof: editing the YAML requirement changes the gate
        with ZERO Python changes."""
        import yaml as _yaml

        # Copy the PA profile to a temp location with DIFFERENT requirements
        src = "src/portal/forms/pa_easi_protector.yaml"
        with open(src, "r", encoding="utf-8") as fh:
            data = _yaml.safe_load(fh)
        data["identity_requirements"] = {"required": ["id_number", "nationality"]}

        tmp = tmp_path / "pa_modified.yaml"
        with open(tmp, "w", encoding="utf-8") as fh:
            _yaml.safe_dump(data, fh)

        req = IdentityRequirements.from_profile(str(tmp))
        assert req.required == ["id_number", "nationality"]

        # And the capability gate follows the NEW requirement via binding:
        class _FakeBinding:
            product = "pa"
            profile = str(tmp)

        req2 = IdentityRequirements.from_binding(_FakeBinding())
        assert req2.required == ["id_number", "nationality"]

    def test_pa_valid_still_passes(self):
        cap = PaProductCapability()
        assert cap.validate(_pa_args()).valid

    def test_motor_valid_still_passes(self):
        cap = MotorProductCapability()
        assert cap.validate(_motor_args()).valid

    def test_motor_invalid_nric_fails_validator(self):
        """Motor id passes format gate but fails legality (bad DOB)."""
        cap = MotorProductCapability()
        vr = cap.validate(_motor_args(id_number="991399145678"))  # month 13
        assert not vr.valid
        assert vr.code not in ("", "IDENTITY_REQUIREMENT_MISSING")
