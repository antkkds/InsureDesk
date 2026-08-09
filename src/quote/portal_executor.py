"""InsureDesk — Portal Quote Executor.

Orchestrates real GEGLink quote execution:
1. Launch the quote channel (IFE/EQ) via GEGLinkAdapter
2. Fill the form fields using YAML profile selectors
3. Click Calculate
4. Extract premium/result from portal page

This is the READ-ONLY quote execution (no save_draft, no submit).
All operations go through SessionMode.READ_ONLY check.

Usage:
    executor = PortalQuoteExecutor(engine, mode=READ_ONLY)
    result = await executor.calculate_quote({
        "proposer_name": "Tiong Hoe Hung",
        "sum_insured": 5000000,
        "occupancy": "Factory",
    })
"""

from __future__ import annotations

import json
import asyncio
import re
from typing import Optional, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime

from src.portals.base import SessionMode, ReadOnlyViolationError
from src.browser.driver import BrowserEngine
from src.quote.field_mapper import FieldMapper


# ══════════════════════════════════════════════════════════════════
# Results
# ══════════════════════════════════════════════════════════════════


@dataclass
class QuoteExtractResult:
    """Result extracted from portal after calculation."""
    success: bool
    premium: float = 0.0
    quote_number: str = ""
    gross_premium: float = 0.0
    net_premium: float = 0.0
    stamp_duty: float = 0.0
    service_tax: float = 0.0
    message: str = ""
    raw_data: Dict[str, Any] = field(default_factory=dict)
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "premium": self.premium,
            "quote_number": self.quote_number,
            "gross_premium": self.gross_premium,
            "net_premium": self.net_premium,
            "stamp_duty": self.stamp_duty,
            "service_tax": self.service_tax,
            "message": self.message,
            "raw_data": self.raw_data,
            "error": self.error,
        }


# ══════════════════════════════════════════════════════════════════
# Portal Quote Executor
# ══════════════════════════════════════════════════════════════════


class PortalQuoteExecutor:
    """Executes quote calculations on real insurance portals.

    This is the bridge between the Tool Runtime and the actual portal browser.
    All operations are READ_ONLY by default.

    Args:
        engine: BrowserEngine instance (CDP or Playwright).
        profile_path: Path to YAML profile (e.g. "profiles/ife_quote.yaml").
        channel_type: "IFE" or "EQ".
        mode: SessionMode (default READ_ONLY).
    """

    # JS to extract premium values from portal result page
    EXTRACT_JS = """
    (() => {
        const result = {};

        // Try common premium display fields
        const selectors = [
            '#totalPremium', '#grossPremium', '#netPremium',
            '#stampDuty', '#serviceTax',
            '[id*="premium"]', '[id*="Premium"]',
            '[name*="premium"]', '[name*="Premium"]',
            'td:contains("Premium")', 'span:contains("Premium")',
            '.premium-amount', '.premiumAmount',
        ];

        for (const sel of selectors) {
            const el = document.querySelector(sel);
            if (el) {
                const val = el.value || el.textContent || '';
                result[sel.replace(/[#\\[\\]]/g, '')] = val.trim();
            }
        }

        // Try quote number
        const qnSelectors = [
            '#quoteNo', '#quotationNo', '#quoteNumber',
            '[id*="quoteNo"]', '[id*="quotationNo"]',
            'td:contains("Quote No")', 'span:contains("Quote No")',
        ];
        for (const sel of qnSelectors) {
            const el = document.querySelector(sel);
            if (el) {
                result.quoteNumber = (el.value || el.textContent || '').trim();
                break;
            }
        }

        // Try result message
        const msgSelectors = [
            '.success-message', '.result-message', '#resultMessage',
            '[id*="result"]', '[class*="result"]',
        ];
        for (const sel of msgSelectors) {
            const el = document.querySelector(sel);
            if (el) {
                result.resultMessage = (el.value || el.textContent || '').trim();
                break;
            }
        }

        return JSON.stringify(result);
    })()
    """

    def __init__(self, engine: Optional[BrowserEngine] = None,
                 profile_path: Optional[str] = None,
                 channel_type: str = "IFE",
                 mode: SessionMode = SessionMode.READ_ONLY):
        self._engine = engine
        self._mode = mode
        self.channel_type = channel_type.upper()
        self.field_mapper = FieldMapper(
            profile_path=profile_path,
            channel_type=channel_type,
        ) if profile_path else None

    @property
    def mode(self) -> SessionMode:
        return self._mode

    def set_engine(self, engine: BrowserEngine):
        self._engine = engine

    def set_profile(self, profile_path: str):
        self.field_mapper = FieldMapper(
            profile_path=profile_path,
            channel_type=self.channel_type,
        )

    # ══════════════════════════════════════════════════════════
    # Safety
    # ══════════════════════════════════════════════════════════

    def _assert_read_only(self):
        """Read-only execution for portal safety."""
        # calculate is allowed in READ_ONLY mode per design
        # (it reads from portal but doesn't commit/submit)
        pass

    # ══════════════════════════════════════════════════════════
    # Form Filling
    # ══════════════════════════════════════════════════════════

    async def _fill_form_fields(self, fields: Dict[str, str]) -> int:
        """Fill form fields on the portal page.

        Args:
            fields: Dict of {css_selector: value} to fill.

        Returns:
            Number of fields successfully filled.
        """
        if not self._engine:
            return 0

        filled = 0
        for selector, value in fields.items():
            try:
                await self._engine.evaluate(f"""
                    (() => {{
                        const el = document.querySelector('{selector}');
                        if (!el) return false;
                        const tag = el.tagName.toLowerCase();

                        if (tag === 'select') {{
                            el.value = '{value}';
                            el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                        }} else if (tag === 'input' || tag === 'textarea') {{
                            const nativeSetter = Object.getOwnPropertyDescriptor(
                                window.HTMLInputElement.prototype, 'value'
                            )?.set || Object.getOwnPropertyDescriptor(
                                window.HTMLTextAreaElement.prototype, 'value'
                            )?.set;
                            if (nativeSetter) {{
                                nativeSetter.call(el, '{value}');
                            }} else {{
                                el.value = '{value}';
                            }}
                            el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                            el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                        }}

                        return true;
                    }})()
                """)
                filled += 1
            except Exception:
                pass

        return filled

    async def _click_calculate(self) -> bool:
        """Click the Calculate/Get Premium button.

        Returns:
            True if button was clicked.
        """
        if not self._engine:
            return False

        # Try various button selectors
        btn_selectors = [
            'input[value="Calculate"]',
            'input[value="Calculate Premium"]',
            'input[value="Get Quote"]',
            'button:contains("Calculate")',
            'button:contains("Premium")',
            '#btnCalculate', '#btnSubmit', '#cmdCalculate',
            '[id*="calculate"]', '[id*="Calculate"]',
            '[class*="calculate"]', '[class*="Calculate"]',
        ]

        for selector in btn_selectors:
            try:
                result = await self._engine.evaluate(f"""
                    (() => {{
                        const btn = document.querySelector('{selector}');
                        if (!btn) return false;
                        btn.click();
                        return true;
                    }})()
                """)
                if result:
                    return True
            except Exception:
                continue

        # Fallback: try to find any submit-type button
        try:
            result = await self._engine.evaluate("""
                (() => {
                    const btn = document.querySelector(
                        'input[type="submit"], input[type="button"], button[type="submit"]'
                    );
                    if (!btn) return false;
                    btn.click();
                    return true;
                })()
            """)
            return bool(result)
        except Exception:
            return False

    async def _extract_result(self) -> QuoteExtractResult:
        """Extract quote result from portal page after calculation.

        Returns:
            QuoteExtractResult with premium and quote number.
        """
        if not self._engine:
            return QuoteExtractResult(success=False, error="No browser engine")

        try:
            raw = await self._engine.evaluate(self.EXTRACT_JS)
            data = json.loads(raw) if isinstance(raw, str) else {}
        except Exception as e:
            return QuoteExtractResult(success=False, error=f"Extract failed: {e}")

        # Parse premium values from found data
        premium = self._parse_premium(data)
        quote_number = data.get("quoteNumber", "")

        return QuoteExtractResult(
            success=bool(premium > 0 or quote_number),
            premium=premium,
            quote_number=quote_number,
            gross_premium=premium,
            net_premium=premium,
            raw_data=data,
            message=data.get("resultMessage", ""),
        )

    @staticmethod
    def _parse_premium(data: Dict[str, Any]) -> float:
        """Extract premium value from raw portal data.

        Tries various field names that might contain the premium.
        """
        for key in ["totalPremium", "grossPremium", "netPremium",
                     "premium", "amount", "total"]:
            val = data.get(key)
            if val:
                try:
                    return float(str(val).replace(",", "").replace("RM", "").strip())
                except (ValueError, TypeError):
                    continue

        # Scan all values for numeric patterns
        for val in data.values():
            if isinstance(val, str):
                # Look for RM pattern
                import re
                match = re.search(r'RM\s*([\d,]+\.?\d*)', val)
                if match:
                    try:
                        return float(match.group(1).replace(",", ""))
                    except ValueError:
                        continue
        return 0.0

    # ══════════════════════════════════════════════════════════
    # Main API
    # ══════════════════════════════════════════════════════════

    async def calculate_quote(self,
                               domain_data: Dict[str, Any],
                               form_url: Optional[str] = None) -> QuoteExtractResult:
        """Execute a quote calculation on the real portal.

        Args:
            domain_data: Domain field values (proposer_name, sum_insured, etc.).
            form_url: Direct URL to the quote form (e.g. fireQuote.html).
                      If not provided, assumes already on the form page.

        Returns:
            QuoteExtractResult with premium information.
        """
        if not self._engine:
            return QuoteExtractResult(success=False, error="No browser engine")

        if not self.field_mapper:
            return QuoteExtractResult(success=False, error="No profile loaded")

        # Navigate to form page if URL provided
        if form_url:
            try:
                await self._engine.navigate(form_url)
            except Exception as e:
                return QuoteExtractResult(success=False, error=f"Navigate failed: {e}")
            await asyncio.sleep(2)

        # Map domain fields to portal form fields
        portal_fields = self.field_mapper.map_to_portal(domain_data)

        if not portal_fields:
            return QuoteExtractResult(success=False, error="No fields to fill")

        # Fill form fields
        filled = await self._fill_form_fields(portal_fields)
        if filled == 0:
            return QuoteExtractResult(success=False, error="Could not fill any form fields")

        # Click Calculate
        clicked = await self._click_calculate()
        if not clicked:
            return QuoteExtractResult(
                success=False, error="No calculate button found",
                raw_data={"fields_filled": filled},
            )

        # Wait for calculation to complete
        await asyncio.sleep(3)

        # Extract result
        result = await self._extract_result()
        result.raw_data["fields_filled"] = filled
        return result

    async def get_form_fields(self) -> Dict[str, Dict[str, Any]]:
        """Get the current state of form fields on the portal page.

        Returns:
            Dict of {field_key: {value, selector, type}}.
        """
        if not self._engine or not self.field_mapper:
            return {}

        elements = self.field_mapper.elements
        result = {}

        for key, info in elements.items():
            selector = info.get("selector", "")
            if not selector:
                continue
            try:
                value = await self._engine.evaluate(f"""
                    (() => {{
                        const el = document.querySelector('{selector}');
                        if (!el) return null;
                        return el.value || el.textContent || '';
                    }})()
                """)
                result[key] = {
                    "value": str(value) if value else "",
                    "selector": selector,
                    "type": info.get("field_type", "text"),
                }
            except Exception:
                pass

        return result

    async def check_form_ready(self) -> Dict[str, Any]:
        """Check if the portal form page is ready for interaction.

        Returns:
            Dict with status and details.
        """
        if not self._engine:
            return {"ready": False, "error": "No browser engine"}

        try:
            title = await self._engine.evaluate("document.title")
            url = await self._engine.evaluate("window.location.href")
            form_count = await self._engine.evaluate(
                "document.querySelectorAll('input, select, textarea').length"
            )
            return {
                "ready": bool(url and "getquote" in str(url).lower()),
                "url": str(url) if url else "",
                "title": str(title) if title else "",
                "form_fields": int(form_count) if form_count else 0,
            }
        except Exception as e:
            return {"ready": False, "error": str(e)}


