"""Contract Freeze — GEARS bindings (GEARS × PA, GEARS × Motor).

This module implements the frozen interfaces for the only portal that exists
today (GEARS). The implementations are THIN: they delegate to the existing,
battle-tested modules (pa_adapter, tools registry, session guard,
diagnostics). The freeze locks the contract; it does not rewrite portal
automation.

Matrix (frozen):
    GEARS × PA    → insurance.quote.pa      (profile: pa_easi_protector.yaml)
    GEARS × Motor → insurance.quote.motor (profile: motor_private_car.yaml)
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from src.contracts.capability import ProductCapability
from src.contracts.models import (
    ExecutionContext,
    ExecutionStage,
    ProductBinding,
    ValidationResult,
)
from src.contracts.portal import PortalAdapter, PortalRuntime
from src.contracts.registry import ContractRegistry

logger = logging.getLogger(__name__)

PA_PROFILE = "src/portal/forms/pa_easi_protector.yaml"
MOTOR_PROFILE = "src/portal/forms/motor_private_car.yaml"
TRAVEL_PROFILE = "profiles/geglink_travel.yaml"

# ══════════════════════════════════════════════════════════════════════
# GEARS Portal Runtime — service bag over existing implementations
# ══════════════════════════════════════════════════════════════════════


class GearsPortalRuntime(PortalRuntime):
    """GEARS runtime services (session guard + diagnostics + fill engine)."""

    @property
    def portal(self) -> str:
        return "gears"

    @property
    def session(self) -> Any:
        """GearsSessionGuard — session health/recovery (execution-time)."""
        from src.gears.session.guard import GearsSessionGuard

        return GearsSessionGuard()

    @property
    def diagnostics(self) -> Any:
        """Startup diagnostics + frozen browser contract."""
        from src.gears.session import diagnostics as diag

        return diag

    @property
    def navigation(self) -> Any:
        """FormEngine (YAML profile driven navigation/fill)."""
        try:
            from src.portal.form_engine import FormEngine
            from src.browser import create_browser_engine

            return FormEngine(create_browser_engine())
        except Exception as e:  # noqa: BLE001 — runtime service is lazy
            logger.debug("gears runtime navigation unavailable: %s", e)
            return None

    @property
    def fill(self) -> Any:
        try:
            from src.fill.engine import FillEngine

            return FillEngine()
        except Exception as e:  # noqa: BLE001
            logger.debug("gears runtime fill unavailable: %s", e)
            return None

    async def health(self) -> Dict[str, Any]:
        """Observe-only portal health (startup diagnostics, never recovers)."""
        diag = self.diagnostics
        try:
            report = await diag.run_startup_diagnostics()
            d = report.to_dict()
            d["portal"] = self.portal
            return d
        except Exception as e:  # noqa: BLE001
            return {
                "portal": self.portal,
                "overall": "failed",
                "error": str(e),
            }


# ══════════════════════════════════════════════════════════════════════
# GEARS Portal Adapter
# ══════════════════════════════════════════════════════════════════════


class GearsPortalAdapter(PortalAdapter):
    """GEARS (Great Eastern) portal adapter — product-agnostic."""

    SUPPORTED_PRODUCTS = {"pa", "motor", "fire", "travel"}

    @property
    def portal(self) -> str:
        return "gears"

    @property
    def insurer(self) -> str:
        return "great_eastern"

    def supports_product(self, product: str) -> bool:
        return product in self.SUPPORTED_PRODUCTS

    def runtime(self) -> PortalRuntime:
        return GearsPortalRuntime()

    async def run(self, ctx: ExecutionContext) -> Dict[str, Any]:
        """Execute the product flow against GEARS.

        Current contract: delegate to the resolved product capability (which
        owns the existing portal automation). A future Company B adapter
        would serve the same capability with portal-specific glue.
        """
        from src.contracts.registry import get_default_registry

        registry = get_default_registry()
        resolved = registry.resolve(ctx.capability)
        if resolved is None or resolved.capability is None:
            return {"ok": False, "error": f"no capability for {ctx.capability}"}
        ctx.mark(ExecutionStage.EXECUTING)
        return await resolved.capability.execute(ctx)


# ══════════════════════════════════════════════════════════════════════
# PA Product Capability — Easi Protector (PEP)
# ══════════════════════════════════════════════════════════════════════


def _parse_dob(dob_raw: str):
    """Parse DOB in the formats the PA flow accepts (same as handler)."""
    from datetime import datetime

    for fmt in ("%Y-%m-%d", "%d %b %Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(dob_raw, fmt).date()
        except ValueError:
            continue
    return None


class PaProductCapability(ProductCapability):
    """PA (Personal Accident) product contract.

    validate(): identity gate (IdentityDataValidator — PA-3) + plan check.
        Invalid identity NEVER reaches the portal (second safety gate).
    execute(): build adapter payload + run the READ-ONLY PEP flow via the
        resident GEARS CDP tab (existing pa_adapter, untouched).
    """

    @property
    def product(self) -> str:
        return "pa"

    @property
    def capabilities(self) -> List[str]:
        return ["insurance.quote.pa"]

    @property
    def binding(self) -> ProductBinding:
        return ProductBinding(
            product="pa",
            insurer="great_eastern",
            portal="gears",
            capability="insurance.quote.pa",
            profile=PA_PROFILE,
            safety="readonly",
        )

    def validate(self, arguments: Dict[str, Any]) -> ValidationResult:
        """PA business validation gate (runs before any portal access).

        Review #3 / G4: profile-driven gate — required fields (coverage_type,
        occupation, plan, applicant) and the EP plan ladder (allowed_values)
        come from the binding YAML via ProfileGate. Identity completeness
        (id_number/dob/gender/full_name) via IdentityRequirements; legality
        (NRIC/DOB/parity) via IdentityDataValidator. Invalid data NEVER
        reaches the portal.
        """
        # ── profile-driven gate: required + allowed_values (G4) ──
        from src.contracts.gate import ProfileGate

        gate = ProfileGate(self.binding.profile)
        vr = gate.validate(arguments)
        if not vr.valid:
            return vr

        from src.identity.validator import IdentityDataValidator

        applicant = arguments.get("applicant") or {}
        id_number = str(applicant.get("id_number", "")).strip()
        id_type = str(applicant.get("id_type", "NRIC")).strip()
        full_name = str(applicant.get("full_name", "")).strip()
        gender = str(applicant.get("gender", "")).strip()
        dob_raw = str(applicant.get("dob", "")).strip()

        # ── PA-8.2: IdentityRequirements (from binding, profile-driven) ──
        # Which identity facts does THIS product require? (PA: id+dob+gender
        # +full_name). Completeness gate BEFORE legality (validator) — a
        # missing fact is clearer than a format error.
        from src.identity.requirements import IdentityRequirements

        req = IdentityRequirements.from_binding(self.binding)
        identity_facts = {
            "id_number": id_number,
            "dob": dob_raw,
            "gender": gender,
            "full_name": full_name,
        }
        missing = [f for f in req.required if not str(identity_facts.get(f, "")).strip()]
        if missing:
            return ValidationResult.fail(
                f"identity requirement(s) missing: {', '.join(missing)}",
                code="IDENTITY_REQUIREMENT_MISSING",
                errors=[{"field": f, "code": "IDENTITY_REQUIREMENT_MISSING"} for f in missing],
            )

        dob = None
        if dob_raw:
            dob = _parse_dob(dob_raw)

        v = IdentityDataValidator()
        vresult = v.validate_identity(
            id_type, id_number, dob=dob, gender=gender or None,
        )
        if not vresult.is_valid:
            codes = sorted({e.code for e in vresult.errors})
            msgs = "; ".join(e.message for e in vresult.errors[:3])
            return ValidationResult.fail(
                f"identity validation failed: {msgs}",
                code=codes[0] if codes else "IDENTITY_INVALID",
                errors=vresult.errors,
            )

        # plan membership is enforced by ProfileGate allowed_values (G4)

        # ── POL-1: contact completeness — NEVER fabricate contact data ──
        # mobile/email/address1/state are customer data the request must
        # supply; a missing contact field fails validation (operator asks
        # the customer) instead of defaulting from test fixtures.
        from src.identity.requirements import ContactRequirements

        creq = ContactRequirements.from_binding(self.binding)
        cmissing = creq.missing_fields(applicant)
        if cmissing:
            return ValidationResult.fail(
                f"contact requirement(s) missing: {', '.join(cmissing)}",
                code="CONTACT_REQUIREMENT_MISSING",
                errors=[{"field": f, "code": "CONTACT_REQUIREMENT_MISSING"} for f in cmissing],
            )

        return ValidationResult.ok()

    async def execute(self, ctx: ExecutionContext) -> Dict[str, Any]:
        """Build PA payload + run READ-ONLY PEP flow (existing pa_adapter).

        Payload construction is an exact replica of the original handler
        contract (identity → payload → runner), so tests asserting payload
        fields keep passing unchanged.
        """
        from src.quote.pa_adapter import run_pa_quote_via_cdp

        arguments = ctx.arguments
        applicant = arguments.get("applicant") or {}
        id_number = str(applicant.get("id_number", "")).strip()
        full_name = str(applicant.get("full_name", "")).strip()
        gender = str(applicant.get("gender", "")).strip()
        dob_raw = str(applicant.get("dob", "")).strip()
        dob = _parse_dob(dob_raw) if dob_raw else None
        plan = str(arguments.get("plan", "EP1")).strip() or "EP1"

        payload = {
            "coverage_type": arguments.get("coverage_type") or "individual",
            "occupation": arguments.get("occupation") or "MANAGER",
            "occupation_class": arguments.get("occupation_class") or "",
            "dob": dob.strftime("%d %b %Y") if dob else "",
            "vehicle_indicator": "N",
            "plan": plan,
            "id_number": id_number,
            "title": arguments.get("title") or "",
            "full_name": full_name,
            "gender": gender,
            "nationality": applicant.get("nationality") or "",
            "race": applicant.get("race") or "",
            "state": applicant.get("state") or "",
            "address1": applicant.get("address1") or "",
            "mobile": applicant.get("mobile") or "",
            "email": applicant.get("email") or "",
            "health_declare_no": True,
            "send_pds_email": False,
        }

        # POL-1: contact/identity are guaranteed by validate(); if a customer
        # field is somehow still empty, fail loudly rather than fabricate.
        empty = [k for k, v in payload.items() if isinstance(v, str) and not v.strip() and k not in ("occupation_class", "title", "nationality", "race")]
        if empty:
            ctx.mark(ExecutionStage.EXECUTION_FAILED)
            return {"ok": False, "status": "VALIDATION_FAILED",
                    "error": f"missing customer field(s) for portal: {', '.join(empty)}",
                    "execution_mode": "real"}

        ctx.payload = payload
        ctx.mark(ExecutionStage.EXECUTING)

        def log(msg: str) -> None:
            logger.info("[pa] %s", msg)

        result = await run_pa_quote_via_cdp(payload, log)
        ctx.result = result
        if result.get("ok"):
            ctx.mark(ExecutionStage.CALCULATED)
        else:
            ctx.mark(ExecutionStage.EXECUTION_FAILED)
        return result


# ══════════════════════════════════════════════════════════════════════
# Motor Product Capability — Motor private car (GEARS)
# ══════════════════════════════════════════════════════════════════════


class MotorProductCapability(ProductCapability):
    """Motor (private car) product contract.

    validate(): profile-driven gate (Motor-1) — required fields come from
        the binding YAML request_schema via ProfileGate; identity checked by
        IdentityRequirements + IdentityDataValidator. Portal selectors stay
        in the profile YAML.
    execute(): REAL-only production path (Motor-2 converged) — delegates to
        motor_flow (run_driver_flow, the SINGLE production path). The legacy
        tool-registry simulation path was removed to align with PA/Fire.
    """

    @property
    def product(self) -> str:
        return "motor"

    @property
    def capabilities(self) -> List[str]:
        return ["insurance.quote.motor"]

    @property
    def binding(self) -> ProductBinding:
        return ProductBinding(
            product="motor",
            insurer="great_eastern",
            portal="gears",
            capability="insurance.quote.motor",
            profile=MOTOR_PROFILE,
            safety="readonly",
        )

    def validate(self, arguments: Dict[str, Any]) -> ValidationResult:
        """Profile-driven validation gate (Motor-1).

        Reads ``request_schema`` from the binding YAML (motor_private_car.yaml):
        registration/plate (vehicle_number), usage state (place), and owner
        identity (id_number) are required — invalid data never reaches the
        portal. The rules live in the PROFILE, not in Python.

        REAL mode only (Motor-2): no simulation bypass — every execution
        passes this gate before touching the portal.
        """
        from src.contracts.gate import ProfileGate

        gate = ProfileGate(self.binding.profile)
        vr = gate.validate(arguments)
        if not vr.valid:
            return vr

        # Motor identity format contract (portal-level, from the profile):
        # idNumber is maxlength=12 + digitonly — 12 digits WITHOUT dashes.
        id_number = str(arguments.get("id_number", "")).strip()
        if id_number and (len(id_number) != 12 or not id_number.isdigit()):
            return ValidationResult.fail(
                "id_number must be 12 digits without dashes (portal contract)",
                code="ID_NUMBER_FORMAT_INVALID",
            )

        # ── PA-8.2: IdentityRequirements (from binding, profile-driven) ──
        # Motor requires id_number + full_name (declared in the Motor YAML).
        from src.identity.requirements import IdentityRequirements

        req = IdentityRequirements.from_binding(self.binding)
        missing = [f for f in req.required if not str(arguments.get(f, "")).strip()]
        if missing:
            return ValidationResult.fail(
                f"identity requirement(s) missing: {', '.join(missing)}",
                code="IDENTITY_REQUIREMENT_MISSING",
                errors=[{"field": f, "code": "IDENTITY_REQUIREMENT_MISSING"} for f in missing],
            )

        # ── IdentityDataValidator — is the identity LEGAL? (format/DOB) ──
        # Motor supplies id_number (12-digit NRIC or passport); dob/gender
        # are AUTO-populated by the portal from the NRIC, so only the
        # document number is validated here.
        from src.identity.validator import IdentityDataValidator

        id_type = str(arguments.get("id_type", "NRIC")).strip()
        v = IdentityDataValidator()
        vresult = v.validate_identity(id_type, id_number)
        if not vresult.is_valid:
            codes = sorted({e.code for e in vresult.errors})
            msgs = "; ".join(e.message for e in vresult.errors[:3])
            return ValidationResult.fail(
                f"identity validation failed: {msgs}",
                code=codes[0] if codes else "IDENTITY_INVALID",
                errors=vresult.errors,
            )
        return ValidationResult.ok()

    async def execute(self, ctx: ExecutionContext) -> Dict[str, Any]:
        """Run the motor quote through the product flow (REAL only, Motor-2).

        Production path: GearsDriver + FillEngine + motor_private_car.yaml
        via motor_flow (run_driver_flow — the SINGLE production path).
        The legacy tool-registry simulation path was removed (Motor-2) —
        every execution is real, gated, read-only.
        """
        arguments = dict(ctx.arguments)

        # ── REAL — production path (GearsDriver + FillEngine + YAML) ──
        from src.quote.motor_flow import build_motor_payload, run_motor_quote_via_cdp

        payload = build_motor_payload(arguments)
        ctx.payload = payload
        ctx.mark(ExecutionStage.EXECUTING)

        def log(msg: str) -> None:
            logger.info("[motor] %s", msg)

        result = await run_motor_quote_via_cdp(payload, log)
        ctx.result = result
        if result.get("ok"):
            ctx.mark(ExecutionStage.CALCULATED)
        else:
            ctx.mark(ExecutionStage.EXECUTION_FAILED)
        return result

FIRE_PROFILE = "profiles/geglink_fire.yaml"

# Deterministic expected premium for the pinned fixture (recon 2026-08-16):
# Building and Content / 1A / Detached / 500k + 100k / no add-ons → MYR 861.04.
EXPECTED_FIRE_PREMIUM = "861.04"


class FireProductCapability(ProductCapability):
    """Fire (GREAT SHIELD HOME / FSH) product contract.

    validate(): profile-driven gate (Fire-2) — required fields, conditional
        required (Building/Content visibility) and content_value ladder all
        come from the binding YAML via ProfileGate; identity validated by
        IdentityDataValidator. Invalid data NEVER reaches the portal.
    execute(): Fire-2 scope is the eligibility dialog declarative action
        experiment (portal workflow state FSH introduces) — NOT the full
        quote flow. The full chain (Gate → Step 1 → eligibility → Step 2 →
        Step 3 → premium) is verified in Fire-4.
    """

    @property
    def product(self) -> str:
        return "fire"

    @property
    def capabilities(self) -> List[str]:
        return ["insurance.quote.fire"]

    @property
    def binding(self) -> ProductBinding:
        return ProductBinding(
            product="fire",
            insurer="great_eastern",
            portal="gears",
            capability="insurance.quote.fire",
            profile=FIRE_PROFILE,
            safety="readonly",
        )

    def validate(self, arguments: Dict[str, Any]) -> ValidationResult:
        """Fire business validation gate (Fire-2, profile-driven)."""
        from src.contracts.gate import ProfileGate

        # ── profile-driven gate: required + conditional + allowed ladder ──
        gate = ProfileGate(self.binding.profile)
        vr = gate.validate(arguments)
        if not vr.valid:
            return vr

        # ── identity gate (applicant on step 3, same validator as PA/Motor) ──
        applicant = arguments.get("applicant") or {}
        id_number = str(applicant.get("id_number", "")).strip()
        id_type = str(applicant.get("id_type", "NRIC")).strip()

        if id_number:
            from src.identity.validator import IdentityDataValidator

            v = IdentityDataValidator()
            vresult = v.validate_identity(id_type, id_number)
            if not vresult.is_valid:
                codes = sorted({e.code for e in vresult.errors})
                msgs = "; ".join(e.message for e in vresult.errors[:3])
                return ValidationResult.fail(
                    f"identity validation failed: {msgs}",
                    code=codes[0] if codes else "IDENTITY_INVALID",
                    errors=vresult.errors,
                )
        return ValidationResult.ok()

    async def execute(self, ctx: ExecutionContext) -> Dict[str, Any]:
        """Run the read-only FSH quote flow (Fire-3 main chain).

        The capability only builds the payload from arguments and delegates to
        src.quote.fire_flow — the same shape as PA (→ pa_adapter) and Motor
        (→ motor_flow). NO selector / browser / GEARS knowledge lives here;
        the binding profile YAML owns the form spec and the eligibility action.
        """
        from src.quote.fire_flow import run_fire_quote_via_cdp

        arguments = ctx.arguments
        payload = {
            "coverage_type": arguments.get("coverage_type") or "Building and Content",
            "construction_classification": (
                arguments.get("construction_classification")
                or "1A. Wholly brick walls/Reinforced Concrete Floors"
            ),
            "property_type": arguments.get("property_type") or "Detached - Non-Detached",
            "property_sum_insured": arguments.get("property_sum_insured") or 500000,
            "content_descriptions": (
                arguments.get("content_descriptions")
                or "Detached and Non-Detached, Flats and Apartments"
            ),
            "content_value": arguments.get("content_value") or 100000,
            "start_date": arguments.get("coverage_start_date") or "16 Aug 2026",
            "end_date": arguments.get("coverage_end_date") or "15 Aug 2027",
        }
        if "applicant" in arguments:
            payload["applicant"] = arguments["applicant"]

        ctx.payload = payload
        ctx.mark(ExecutionStage.EXECUTING)

        def log(msg: str) -> None:
            logger.info("[fire] %s", msg)

        result = await run_fire_quote_via_cdp(payload, log)
        ctx.result = result
        if result.get("ok"):
            ctx.mark(ExecutionStage.CALCULATED)
        else:
            ctx.mark(ExecutionStage.EXECUTION_FAILED)
        return result


# ══════════════════════════════════════════════════════════════════════
# Travel Product Capability — Travel For More+ Short Term (PMT)
# ══════════════════════════════════════════════════════════════════════


class TravelProductCapability(ProductCapability):
    """Travel (Travel For More+ Short Term / PMT) product contract.

    validate(): profile-driven gate (Travel-1) — required fields, trip type /
        coverage type enums and the A/B/C plan ladder all come from the
        binding YAML via ProfileGate; identity validated by
        IdentityDataValidator (step-3 proposer). Invalid data NEVER reaches
        the portal.
    execute(): read-only PMT quote flow (Step 1 Trip details → Step 2 Plans
        → Step 3 Details → premium capture). Delegates to
        src.quote.travel_adapter — the same shape as PA (→ pa_adapter).
        NO selector / browser / GEARS knowledge lives here.
    """

    @property
    def product(self) -> str:
        return "travel"

    @property
    def capabilities(self) -> List[str]:
        return ["insurance.quote.travel"]

    @property
    def binding(self) -> ProductBinding:
        return ProductBinding(
            product="travel",
            insurer="great_eastern",
            portal="gears",
            capability="insurance.quote.travel",
            profile=TRAVEL_PROFILE,
            safety="readonly",
        )

    def validate(self, arguments: Dict[str, Any]) -> ValidationResult:
        """Travel business validation gate (profile-driven)."""
        from src.contracts.gate import ProfileGate

        # ── profile-driven gate: required + enums + allowed ladder ──
        gate = ProfileGate(self.binding.profile)
        vr = gate.validate(arguments)
        if not vr.valid:
            return vr

        # ── identity gate (proposer on step 3, same as PA/Motor) ──
        applicant = arguments.get("applicant") or {}
        id_number = str(applicant.get("id_number", "")).strip()
        id_type = str(applicant.get("id_type", "NRIC")).strip()
        full_name = str(applicant.get("full_name", "")).strip()
        gender = str(applicant.get("gender", "")).strip()
        dob_raw = str(applicant.get("dob", "")).strip()

        # Completeness gate BEFORE legality — declared in the binding YAML
        # (identity_requirements.required). A missing fact is clearer than
        # a format error.
        from src.identity.requirements import IdentityRequirements

        req = IdentityRequirements.from_binding(self.binding)
        identity_facts = {
            "id_number": id_number,
            "dob": dob_raw,
            "gender": gender,
            "full_name": full_name,
        }
        missing = [f for f in req.required if not str(identity_facts.get(f, "")).strip()]
        if missing:
            return ValidationResult.fail(
                f"identity requirement(s) missing: {', '.join(missing)}",
                code="IDENTITY_REQUIREMENT_MISSING",
                errors=[{"field": f, "code": "IDENTITY_REQUIREMENT_MISSING"} for f in missing],
            )

        dob = None
        if dob_raw:
            dob = _parse_dob(dob_raw)

        from src.identity.validator import IdentityDataValidator

        v = IdentityDataValidator()
        vresult = v.validate_identity(id_type, id_number, dob=dob, gender=gender or None)
        if not vresult.is_valid:
            codes = sorted({e.code for e in vresult.errors})
            msgs = "; ".join(e.message for e in vresult.errors[:3])
            return ValidationResult.fail(
                f"identity validation failed: {msgs}",
                code=codes[0] if codes else "IDENTITY_INVALID",
                errors=vresult.errors,
            )

        # ── POL-1: contact completeness — NEVER fabricate contact data ──
        from src.identity.requirements import ContactRequirements

        creq = ContactRequirements.from_binding(self.binding)
        cmissing = creq.missing_fields(applicant)
        if cmissing:
            return ValidationResult.fail(
                f"contact requirement(s) missing: {', '.join(cmissing)}",
                code="CONTACT_REQUIREMENT_MISSING",
                errors=[{"field": f, "code": "CONTACT_REQUIREMENT_MISSING"} for f in cmissing],
            )
        return ValidationResult.ok()

    async def execute(self, ctx: ExecutionContext) -> Dict[str, Any]:
        """Run the read-only PMT quote flow (Travel-1 main chain).

        The capability only builds the payload from arguments and delegates to
        src.quote.travel_adapter — the same shape as PA (→ pa_adapter).
        NO selector / browser / GEARS knowledge lives here; the binding
        profile YAML owns the form spec.
        """
        from src.quote.travel_adapter import run_travel_quote_via_cdp

        arguments = ctx.arguments
        applicant = arguments.get("applicant") or {}
        payload = {
            "trip_type": arguments.get("trip_type") or "overseas",
            "destination": arguments.get("destination") or "THAILAND",
            "coverage_type": arguments.get("coverage_type") or "insured_only",
            "plan": arguments.get("plan") or "A",
            "adults": arguments.get("adults") or 1,
            "id_number": applicant.get("id_number") or "",
            "title": applicant.get("title") or "",
            "full_name": applicant.get("full_name") or "",
            "gender": applicant.get("gender") or "",
            "dob": applicant.get("dob") or "",
            "nationality": applicant.get("nationality") or "",
            "race": applicant.get("race") or "",
            "state": applicant.get("state") or "",
            "address1": applicant.get("address1") or "",
            "mobile": applicant.get("mobile") or "",
            "email": applicant.get("email") or "",
        }
        # POL-1: validate() guarantees contact/identity; fail loudly rather
        # than fabricate if a customer field is somehow still empty.
        empty = [k for k, v in payload.items() if isinstance(v, str) and not v.strip() and k not in ("title", "nationality", "race")]
        if empty:
            ctx.mark(ExecutionStage.EXECUTION_FAILED)
            return {"ok": False, "status": "VALIDATION_FAILED",
                    "error": f"missing customer field(s) for portal: {', '.join(empty)}",
                    "execution_mode": "real"}
        if arguments.get("start_date"):
            payload["start_date"] = arguments["start_date"]
        if arguments.get("end_date"):
            payload["end_date"] = arguments["end_date"]

        ctx.payload = payload
        ctx.mark(ExecutionStage.EXECUTING)

        def log(msg: str) -> None:
            logger.info("[travel] %s", msg)

        result = await run_travel_quote_via_cdp(payload, log)
        ctx.result = result
        if result.get("ok"):
            ctx.mark(ExecutionStage.CALCULATED)
        else:
            ctx.mark(ExecutionStage.EXECUTION_FAILED)
        return result


# ══════════════════════════════════════════════════════════════════════
# Default registration
# ══════════════════════════════════════════════════════════════════════


def register_gears_defaults(registry: ContractRegistry) -> None:
    """Register GEARS portal + PA + Motor + Fire + Travel capabilities (idempotent)."""
    if registry.get_portal("gears") is None:
        registry.register_portal(GearsPortalAdapter())
    if registry.get_product("pa") is None:
        registry.register_capability(PaProductCapability())
    if registry.get_product("motor") is None:
        registry.register_capability(MotorProductCapability())
    if registry.get_product("fire") is None:
        registry.register_capability(FireProductCapability())
    if registry.get_product("travel") is None:
        registry.register_capability(TravelProductCapability())
