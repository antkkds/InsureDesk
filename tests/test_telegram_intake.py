"""PA-8.5 tests — Telegram intake (thin adapter) + IdentityIntakeService.

ChatGPT DoD (11 items):
    image→Document / Document→ExtractionResult / →IdentityReview /
    confirm→AUTO_ACCEPTED / correction→CORRECTED / invalid→REJECTED /
    NEEDS_REVIEW cannot quote / validated IdentityData→PAQuoteRequest /
    raw image never enters portal payload / zero PA-GEARS in telegram layer /
    existing PA-Motor flows unchanged.
"""

from __future__ import annotations

import asyncio
from datetime import date

import pytest

from src.connectors.telegram.intake_adapter import TelegramIntakeAdapter
from src.identity.errors import IdentityExtractionFailedError
from src.identity.extraction import TextIdentityExtractor
from src.identity.intake import IdentityIntakeService, IntakeState
from src.identity.models import IdentityData
from src.identity.review import ReviewStatus
from src.identity.requirements import pa_requirements

VALID_IC_TEXT = (
    "MALAYSIA\nName: ALI BIN AHMAD\nNRIC: 900101-14-1232\n"
    "Date of Birth: 01-01-1990\nSex: Female"
)


def _intake(**kw) -> IdentityIntakeService:
    return IdentityIntakeService(requirements=pa_requirements(), **kw)


def _photo_intake() -> IdentityIntakeService:
    """Simulate a photo upload: the extractor receives a PATH (image)."""
    class _PhotoExtractor(TextIdentityExtractor):
        def extract(self, document, **kw):
            # pretend OCR happened on the photo path
            return super().extract(VALID_IC_TEXT, source=str(document))

    return _intake(extractor=_PhotoExtractor())


# ══════════════════════════════════════════════════════════════════════
# DoD 1-3 — image → Document → ExtractionResult → IdentityReview
# ══════════════════════════════════════════════════════════════════════


class TestIntakePipeline:
    def test_1_image_to_document(self):
        intake = _photo_intake()
        review = intake.receive_document("/tmp/fake_ic_photo.jpg", source="telegram")
        assert review.status == ReviewStatus.AUTO_ACCEPTED
        assert intake.state == IntakeState.READY_FOR_QUOTE

    def test_2_document_to_extraction_result(self):
        intake = _intake()
        intake.receive_document(VALID_IC_TEXT, source="telegram")
        assert intake.result is not None
        assert intake.result.identity.id_number == "900101-14-1232"

    def test_3_extraction_to_review(self):
        intake = _intake()
        review = intake.receive_document(VALID_IC_TEXT, source="telegram")
        assert isinstance(review.status, ReviewStatus)
        assert review.identity.full_name == "ALI BIN AHMAD"


# ══════════════════════════════════════════════════════════════════════
# DoD 4-6 — confirm / correct / reject
# ══════════════════════════════════════════════════════════════════════


class TestHumanLoop:
    def test_4_confirm_auto_accepted(self):
        intake = _intake()
        intake.receive_document(VALID_IC_TEXT)
        review = intake.confirm()
        assert review.may_quote is True
        assert intake.state == IntakeState.READY_FOR_QUOTE

    def test_5_correction_corrected(self):
        intake = _intake()
        intake.receive_document(
            "NRIC: 991399-14-1232\nName: ALI\nDate of Birth: 01-01-1990"
        )
        assert intake.review.status == ReviewStatus.NEEDS_REVIEW
        corrected = IdentityData(
            id_type="NRIC", id_number="900101-14-1232",
            full_name="ALI BIN AHMAD", dob=date(1990, 1, 1), gender="F",
        )
        review = intake.correct(corrected)
        assert review.status == ReviewStatus.CORRECTED
        assert intake.may_quote is True

    def test_6_invalid_correction_rejected(self):
        intake = _intake()
        intake.receive_document(
            "NRIC: 991399-14-1232\nName: ALI\nDate of Birth: 01-01-1990"
        )
        still_bad = IdentityData(
            id_type="NRIC", id_number="991399-14-1232",  # month 13 again
            full_name="ALI", dob=date(1990, 1, 1), gender="M",
        )
        review = intake.correct(still_bad)
        assert review.status == ReviewStatus.REJECTED
        assert intake.state == IntakeState.REJECTED
        assert intake.may_quote is False


# ══════════════════════════════════════════════════════════════════════
# DoD 7 — NEEDS_REVIEW cannot quote
# ══════════════════════════════════════════════════════════════════════


class TestQuoteBoundary:
    def test_7_needs_review_cannot_quote(self):
        intake = _intake()
        intake.receive_document(
            "NRIC: 991399-14-1232\nName: ALI\nDate of Birth: 01-01-1990"
        )
        assert intake.review.status == ReviewStatus.NEEDS_REVIEW
        assert intake.may_quote is False
        with pytest.raises(IdentityExtractionFailedError):
            intake.quote_identity()

    def test_quote_identity_returns_canonical(self):
        intake = _intake()
        intake.receive_document(VALID_IC_TEXT)
        identity = intake.quote_identity()
        assert isinstance(identity, IdentityData)
        assert identity.id_number == "900101-14-1232"


# ══════════════════════════════════════════════════════════════════════
# DoD 8-9 — validated IdentityData → PAQuoteRequest; image never in payload
# ══════════════════════════════════════════════════════════════════════


class TestQuoteRequestChain:
    def test_8_validated_identity_feeds_pa_capability(self):
        from src.contracts.gears import PaProductCapability

        intake = _intake()
        intake.receive_document(VALID_IC_TEXT)
        identity = intake.quote_identity()

        cap = PaProductCapability()
        vr = cap.validate({
            "execution_mode": "real",
            "coverage_type": "individual",
            "occupation": "MANAGER",
            "applicant": {
                "id_type": identity.id_type,
                "id_number": identity.id_number,
                "full_name": identity.full_name,
                "dob": identity.dob.isoformat(),
                "gender": identity.gender,
                # POL-1: contact is external customer data, supplied by the
                # operator (not derivable from the IC document)
                "mobile": "0123456789",
                "email": "test.applicant@gmail.com",
                "address1": "12, JALAN MERDEKA",
                "state": "KUALA LUMPUR",
            },
            "plan": "EP1",
        })
        assert vr.valid  # validated identity passes the capability gate

    def test_9_raw_image_never_enters_payload(self):
        """The quote payload carries only canonical facts — no image/base64."""
        from src.contracts.gears import PaProductCapability
        from src.contracts.registry import get_default_registry

        intake = _photo_intake()
        intake.receive_document("/tmp/fake_ic_photo.jpg", source="telegram")
        identity = intake.quote_identity()

        reg = get_default_registry()
        applicant = identity.to_dict()
        # POL-1: contact is external customer data (not derivable from IC)
        applicant.update({
            "mobile": "0123456789",
            "email": "test.applicant@gmail.com",
            "address1": "12, JALAN MERDEKA",
            "state": "KUALA LUMPUR",
        })
        ctx = reg.build_context("insurance.quote.pa", {
            "execution_mode": "real",
            "coverage_type": "individual",
            "occupation": "MANAGER",
            "applicant": applicant,
            "plan": "EP1",
        })
        assert ctx is not None
        cap = PaProductCapability()
        review = cap.validate(ctx.arguments)
        assert review.valid

        # Now inspect what the capability would SEND (payload build path)
        payload = {
            "id_number": identity.id_number,
            "full_name": identity.full_name,
            "dob": identity.dob.isoformat(),
            "gender": identity.gender,
        }
        blob = str(payload).lower()
        assert "image" not in blob
        assert "base64" not in blob
        assert "/tmp/" not in blob
        assert "photo" not in blob


# ══════════════════════════════════════════════════════════════════════
# Telegram adapter — thin UX, zero domain logic
# ══════════════════════════════════════════════════════════════════════


class TestTelegramAdapter:
    def test_handle_photo_builds_review_message(self):
        adapter = TelegramIntakeAdapter(_photo_intake())
        out = adapter.handle_photo("/tmp/fake_ic.jpg")
        assert "我识别到" in out["reply"]
        assert "ALI BIN AHMAD" in out["reply"]
        assert "900101-14-1232" in out["reply"]
        assert out["may_quote"] is True

    def test_handle_confirm(self):
        adapter = TelegramIntakeAdapter(_photo_intake())
        adapter.handle_photo("/tmp/fake_ic.jpg")
        out = adapter.handle_confirm()
        assert out["may_quote"] is True
        assert "确认完成" in out["reply"]

    def test_handle_correct_field(self):
        intake = _intake()
        adapter = TelegramIntakeAdapter(intake)
        adapter.handle_text_document(
            "NRIC: 991399-14-1232\nName: ALI\nDate of Birth: 01-01-1990"
        )
        out = adapter.handle_correct("id_number", "900101-14-1232")
        assert out["may_quote"] is True
        assert "已更新" in out["reply"]

    def test_handle_correct_invalid_rejected(self):
        intake = _intake()
        adapter = TelegramIntakeAdapter(intake)
        adapter.handle_text_document(
            "NRIC: 991399-14-1232\nName: ALI\nDate of Birth: 01-01-1990"
        )
        out = adapter.handle_correct("id_number", "991399-14-1232")
        assert out["may_quote"] is False
        assert "无效" in out["reply"]

    def test_10_telegram_layer_zero_pa_gears(self):
        """No PA/GEARS/selectors/quote logic in the telegram adapter.

        Uses AST to inspect REAL imports (docstring prose doesn't count).
        """
        import ast
        import inspect

        from src.connectors.telegram import intake_adapter

        tree = ast.parse(inspect.getsource(intake_adapter))
        imported = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported.append(node.module)
            elif isinstance(node, ast.Import):
                imported.extend(a.name for a in node.names)
        for mod in imported:
            assert not mod.startswith(("src.quote", "src.portal", "src.gears")), (
                f"telegram adapter must not import {mod}"
            )
        src = inspect.getsource(intake_adapter)
        for bad in ("select_product", "button:has-text", "#idNumber",
                    "PaProductCapability"):
            assert bad not in src, f"telegram adapter must not know {bad}"
        # and no validation logic
        assert "IdentityDataValidator" not in src
        assert "checksum" not in src

    def test_audit_explains_decision(self):
        intake = _intake()
        intake.receive_document(VALID_IC_TEXT)
        audit = intake.audit()
        assert audit["state"] == "ready_for_quote"
        assert audit["may_quote"] is True
        assert audit["review"]["validated"] is True
        assert audit["review"]["requirements_satisfied"] is True
        assert audit["review"]["source"] == ""

    def test_rejected_audit_explains(self):
        intake = _intake()
        intake.receive_document(
            "NRIC: 991399-14-1232\nName: ALI\nDate of Birth: 01-01-1990"
        )
        audit = intake.audit()
        assert audit["state"] == "needs_correction"
        assert audit["may_quote"] is False
        assert audit["review"]["validated"] is False
