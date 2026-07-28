"""InsureDesk Portal — Quote Executor.

Executes insurance quote calculations on real insurance portals.
Uses FormEngine + YAML-driven field definitions from PortalMapping.

Architecture:
    CalculateQuoteTool
        ↓
    QuoteExecutor
        ↓
    FormEngine → BrowserEngine → GEGLink
        ↓
    QuoteResult (dict-based)

Field definitions come from YAML (e.g. portals/great_eastern.yaml):
    quotation.fields.<name> = {selector, type, required, ...}
    quotation.actions.calculate = {selector, wait_after_ms}
    quotation.outputs.premium = {selector, type}

READ_ONLY: Never submits or issues policies.

NOTE: QuoteExecutor uses plain dicts for input/output to avoid
circular imports (tools → portal → tools).
"""

from __future__ import annotations

import asyncio
import logging
import random
import re
from typing import Any, Dict, Optional, Tuple

from src.portal.form_engine import FormEngine
from src.portal.mapping import (
    load_portal_mapping,
    get_selector,
    PortalMapping,
)

logger = logging.getLogger("insuredesk.portal.quote_executor")

# Mapping from incoming request key → YAML quotation field name
REQUEST_TO_YAML_FIELD: Dict[str, str] = {
    "sum_insured": "sum_insured_building",
    "sum_insured_building": "sum_insured_building",
    "sum_insured_contents": "sum_insured_contents",
    "property_address": "property_address",
    "property_postcode": "property_postcode",
    "property_city": "property_city",
    "property_state": "property_state",
    "occupancy": "occupancy",
    "occupancy_class": "occupancy_class",
    "occupation": "occupancy",
    "construction_type": "construction_type",
    "year_built": "year_built",
    "number_of_floors": "number_of_floors",
    "building_area": "building_area",
    "building_type": "building_type",
    "roof_type": "roof_type",
    "security_features": "security_features",
    "coverage_start": "coverage_start",
    "coverage_end": "coverage_end",
    "name": "customer_name",
    "ic_number": "customer_ic",
    "ic": "customer_ic",
    "email": "customer_email",
    "phone": "customer_phone",
    "dob": "customer_dob",
}


class QuoteExecutor:
    """Executes quote calculations on insurance portals.

    Fully driven by YAML portal mappings — no hardcoded selectors.
    Add new fields by editing the YAML, not code.

    Usage:
        executor = QuoteExecutor(form_engine)
        result = await executor.calculate({
            "portal": "great_eastern",
            "product": "IFE",
            "risk": {"sum_insured": 500000},
        })
        # result = {"success": True, "premium": 1234.50, ...}
    """

    def __init__(self, form_engine: Optional[FormEngine] = None):
        self.form_engine = form_engine
        self._mapping_cache: Dict[str, PortalMapping] = {}

    # ── Main API ──

    async def calculate(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate a quote on the target portal.

        Args:
            request: Dict with keys:
                portal (str): Portal identifier.
                product (str): Product code.
                customer (dict): Customer details.
                risk (dict): Risk/property details.
                coverage (dict): Coverage options.

        Returns:
            Dict with: success, premium, currency, breakdown, details,
                       error, error_code.
        """
        # Validate prerequisites
        error = self._validate(request)
        if error:
            return _error(*error)

        portal_name = request.get("portal", "")
        product = request.get("product", "")

        # Load mapping
        mapping = self._load_mapping(portal_name)
        if mapping is None:
            return _error(
                f"No portal mapping found for: {portal_name}",
                "portal_not_found",
            )

        engine = self.form_engine.engine

        try:
            # 1. Navigate to portal
            await self._navigate_to_portal(mapping)

            # 2. Navigate to quotation page
            await self._navigate_to_quotation(mapping)

            # 3. Select product
            await self._select_product(mapping, product)

            # 4. Fill all fields from request
            await self._fill_fields(mapping, request)

            # 5. Click Calculate
            await self._click_calculate(mapping)

            # 6. Extract premium
            return await self._extract_premium(mapping)

        except Exception as e:
            logger.exception(f"Quote calculation failed: {e}")
            return _error(f"Quote execution error: {e}", "execution_error")

    # ── Validation ──

    @staticmethod
    def _validate(request: Dict[str, Any]) -> Optional[Tuple[str, str]]:
        if not request.get("portal"):
            return ("Missing portal name", "missing_portal")
        if not request.get("product"):
            return ("Missing product name", "missing_product")
        return None

    # ── Navigation ──

    async def _navigate_to_portal(self, mapping: PortalMapping) -> None:
        engine = self.form_engine.engine
        login_url = (
            get_selector(mapping, "login", "url")
            or mapping.login_url
            or mapping.base_url
        )
        if login_url:
            logger.info(f"Navigating to {login_url}")
            await engine.navigate(login_url)
            await engine.wait_for_navigation(30000)

    async def _navigate_to_quotation(self, mapping: PortalMapping) -> None:
        engine = self.form_engine.engine
        nav_link = get_selector(mapping, "quotation", "nav_link")
        if nav_link:
            logger.info("Navigating to quotation page")
            await engine.click(nav_link)
            await engine.wait_for_navigation(30000)
            await _delay(1000, 2000)

    # ── Product Selection ──

    async def _select_product(
        self, mapping: PortalMapping, product: str
    ) -> None:
        engine = self.form_engine.engine
        product_sel = get_selector(mapping, "quotation", "product_select")
        if not product_sel:
            logger.warning("No product selector found")
            return
        logger.info(f"Selecting product: {product}")
        try:
            await engine.select_option(product_sel, product.upper())
        except Exception:
            try:
                await engine.select_option(product_sel, product)
            except Exception as e:
                logger.warning(f"Product selection failed: {e}")
        await _delay(500, 1000)

    # ── Field Filling ──

    async def _fill_fields(
        self, mapping: PortalMapping, request: Dict[str, Any]
    ) -> None:
        """Fill all form fields from the request data."""
        engine = self.form_engine.engine

        # Merge customer + risk + coverage
        all_data: Dict[str, Any] = {}
        all_data.update(request.get("customer", {}))
        all_data.update(request.get("risk", {}))
        all_data.update(request.get("coverage", {}))

        if not all_data:
            logger.info("No fields to fill")
            return

        fields_yaml = mapping.selectors.get("quotation", {}).get("fields", {})
        if not fields_yaml:
            logger.warning("No quotation fields defined in YAML")
            return

        filled_count = 0
        for req_key, value in all_data.items():
            if not value:
                continue
            yaml_field = REQUEST_TO_YAML_FIELD.get(req_key, req_key)
            field_def = fields_yaml.get(yaml_field)
            if not field_def:
                continue
            selector = field_def.get("selector", "")
            field_type = field_def.get("type", "text")
            if not selector:
                continue
            logger.info(
                f"Filling '{yaml_field}' "
                f"(type={field_type}, required={field_def.get('required', False)})"
            )
            await self._fill_one(engine, selector, field_type, str(value))
            await _delay(150, 400)
            filled_count += 1
        logger.info(f"Filled {filled_count} field(s)")

    @staticmethod
    async def _fill_one(engine, selector: str, field_type: str, value: str):
        """Fill a single field based on its type."""
        try:
            if field_type in ("select", "dropdown"):
                await engine.select_option(selector, value)
            elif field_type in ("checkbox", "radio"):
                is_checked = value.lower() in ("true", "yes", "1", "on")
                await engine.set_checked(selector, is_checked)
            else:
                await engine.fill(selector, value)
        except Exception as e:
            logger.warning(f"Could not fill {selector}: {e}")

    # ── Calculate Action ──

    async def _click_calculate(self, mapping: PortalMapping) -> None:
        engine = self.form_engine.engine

        actions = mapping.selectors.get("quotation", {}).get("actions", {})
        calc_def = actions.get("calculate", {})
        calc_selector = (
            calc_def.get("selector", "") if isinstance(calc_def, dict) else ""
        )
        if not calc_selector:
            calc_selector = get_selector(mapping, "quotation", "calculate_button")
        if not calc_selector:
            raise ValueError("No calculate button in portal mapping")

        logger.info("Clicking Calculate")
        await engine.click(calc_selector)

        wait_ms = 3000
        if isinstance(calc_def, dict):
            wait_ms = calc_def.get("wait_after_ms", 3000)
        await _delay(wait_ms, wait_ms + 2000)

    # ── Premium Extraction ──

    async def _extract_premium(self, mapping: PortalMapping) -> Dict[str, Any]:
        engine = self.form_engine.engine

        outputs = mapping.selectors.get("quotation", {}).get("outputs", {})
        premium_def = outputs.get("premium", {})
        premium_selector = (
            premium_def.get("selector", "") if isinstance(premium_def, dict) else ""
        )
        if not premium_selector:
            premium_selector = get_selector(mapping, "quotation", "premium_display")
        if not premium_selector:
            return _error("No premium output selector defined",
                          "missing_premium_selector")

        try:
            await engine.wait_for_selector(premium_selector, timeout=15000)
            premium_text = await engine.get_text(premium_selector)
        except Exception as e:
            logger.warning(f"Could not extract premium: {e}")
            premium_text = ""

        premium_value = _parse_premium(premium_text)

        # Breakdown
        breakdown = {}
        bsel = outputs.get("premium_breakdown", {}).get("selector", "")
        if bsel:
            try:
                bt = await engine.get_text(bsel)
                breakdown = _parse_breakdown(bt)
            except Exception:
                pass

        return _ok(premium_value, breakdown=breakdown, details=premium_text)

    # ── Mapping Cache ──

    def _load_mapping(self, portal_name: str) -> Optional[PortalMapping]:
        if portal_name not in self._mapping_cache:
            mapping = load_portal_mapping(portal_name)
            self._mapping_cache[portal_name] = mapping
        return self._mapping_cache[portal_name]


# ══════════════════════════════════════════════════════════════════
# Module-level helpers (no class dependency)
# ══════════════════════════════════════════════════════════════════


def _ok(
    premium: float,
    currency: str = "MYR",
    breakdown: Optional[Dict[str, float]] = None,
    details: str = "",
) -> Dict[str, Any]:
    return {
        "success": True,
        "premium": premium,
        "currency": currency,
        "breakdown": breakdown or {},
        "details": details,
        "error": "",
        "error_code": "",
    }


def _error(error: str, error_code: str = "quote_error") -> Dict[str, Any]:
    return {
        "success": False,
        "premium": 0.0,
        "currency": "MYR",
        "breakdown": {},
        "details": "",
        "error": error,
        "error_code": error_code,
    }


def _parse_premium(text: str) -> float:
    """Extract premium amount from text. Handles RM/MYR/numeric formats."""
    if not text:
        return 0.0
    for pattern in [
        r"RM\s*([\d,]+\.?\d*)",
        r"MYR\s*([\d,]+\.?\d*)",
        r"([\d,]+\.\d{2})",
        r"([\d,]+)",
    ]:
        m = re.search(pattern, text)
        if m:
            try:
                return float(m.group(1).replace(",", ""))
            except ValueError:
                continue
    return 0.0


def _parse_breakdown(text: str) -> Dict[str, float]:
    """Parse 'Label: RM 1,234' style breakdown text."""
    result = {}
    if not text:
        return result
    for line in text.split("\n"):
        m = re.match(r"([\w\s/]+)\s*:\s*RM\s*([\d,]+\.?\d*)", line.strip())
        if m:
            try:
                result[m.group(1).strip()] = float(m.group(2).replace(",", ""))
            except ValueError:
                pass
    return result


async def _delay(min_ms: int = 200, max_ms: int = 600):
    await asyncio.sleep(random.randint(min_ms, max_ms) / 1000)
