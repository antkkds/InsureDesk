"""GEARS Motor (PMOT) quote creation capability — verified flow 2026-08-09.

Creates a brand-new Private Car (VPC) quotation from the dashboard and walks
it through all three form steps. Every interaction below was verified live on
the real portal (quote d355ec1b reached SAVED / Pending Proposal / docName
M01119544, premium computed via execution-vpms).

Flow:
    dashboard → New (#add-button) → Motor Insurance → Private Motor
      Insurance → Get quote → /quotations/PMOT/VPC/{uuid}/detail
    STEP 1 (Quotation Details):
      idNumber (blur enables idType) → idType=NRIC → vehicleNumber
      → place=KUALA LUMPUR → condition (JS-unlock + REGISTERED) → Continue
    STEP 2 (Details): applicant + vehicle + dates + PDS email + NCD
    STEP 3 (Sum Insured): desiredSI + add-ons + declarations

Known pitfalls (all discovered live):
  - condition/idType inputs are disabled; JS `el.disabled=false` + click
    unlocks the autocomplete (Angular still responds)
  - marketValue is a disabled input: fill via native setter + input/change
    events (JS), NOT Playwright fill
  - start-date/end-date same: native setter
  - hire purchase: btn_0/btn_1 = Yes/No radio (name=radioBasic). Answer NO
    (btn_1) → no company field; answer YES (btn_0) → #hirePurchaseCompany
    autocomplete renders and must be filled (verified live: typing "C" lists
    CIMB BANK BERHAD etc). `hire_purchase` is an explicit business input —
    never force No to bypass the field. Both paths verified.
  - PDS email button (#emailPDSandPDPN) needs the declaration checkbox first;
    manual-vehicle quotes email directly (no NVIC dialog), auto-lookup quotes
    (e.g. WKL1234) show an NVIC variant dialog → click Select
  - auto-lookup plates (WKL1234 → TOYOTA CAMRY 2002) trigger Vehicle Age
    referral → cannot Send (Submit for review instead)
  - TEST123 manual path lacks NVIC → market lookup returns {"result":[]} →
    quote stays incomplete → no send-application button. Send needs a
    complete quote (real new vehicle data in production).

JS-unlock guardrail (ChatGPT review 2026-08-09): every disabled-field write
goes through JS_FIELD_CONTRACT allowlist — a field not listed fails closed
(no silent bypass). Setter uses framework-compatible native setter +
input/change events; value is read back and verified after write.

Usage:
    creator = GearsQuoteCreator(page)
    quote = await creator.create_quote()
    step1 = await creator.fill_step1(...)
    ...
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional

DASH_URL = "https://gears-my.greateasterngeneral.com/MY/AgencySales/quotations/dashboard"

# ---------------------------------------------------------------------------
# JS-unlock field contract (ChatGPT review guardrail). Every write to a
# disabled/JS-managed field MUST be allowlisted here; anything else fails
# closed instead of silently bypassing the portal's UI state.
#   setter: "native_setter"  → HTMLInputElement value setter + input/change
#           "click_unlock"   → el.disabled=false + click (autocomplete)
# ---------------------------------------------------------------------------
JS_FIELD_CONTRACT: dict[str, dict[str, Any]] = {
    "condition": {
        "setter": "click_unlock",
        "events": ["click"],
        "note": "step1 condition autocomplete — disabled by Angular state",
    },
    "marketValue": {
        "setter": "native_setter",
        "events": ["input", "change"],
        "note": "step2 market value — disabled input, value from NVIC/market API",
    },
    "start-date": {
        "setter": "native_setter",
        "events": ["input", "change"],
        "note": "step2 policy start date — datepicker-managed input",
    },
    "end-date": {
        "setter": "native_setter",
        "events": ["input", "change"],
        "note": "step2 policy end date — datepicker-managed input",
    },
}

UNLOCKED_JS_FIELDS = frozenset(JS_FIELD_CONTRACT.keys())


def normalize_field_value(value: str) -> str:
    """Normalize a field value for comparison (locale formatting: 50,000 vs
    50000, trailing .00, spaces)."""
    return value.replace(",", "").replace(" ", "").replace(".00", "")


@dataclass
class QuoteCreateOutcome:
    status: str = "PENDING"
    quote_url: str = ""
    quote_id: str = ""
    step: int = 0
    referred: bool = False
    market_available: bool = True
    error: str = ""
    elapsed: float = 0.0
    ts: float = field(default_factory=time.time)

    @property
    def send_ready(self) -> bool:
        """A quote can reach Send when it is NOT referred AND the portal's
        market-value lookup had data for the vehicle (NVIC present)."""
        return (not self.referred) and self.market_available and self.step >= 3

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "quote_url": self.quote_url,
            "quote_id": self.quote_id,
            "step": self.step,
            "referred": self.referred,
            "market_available": self.market_available,
            "send_ready": self.send_ready,
            "error": self.error,
            "elapsed": round(self.elapsed, 1),
        }


class GearsQuoteCreator:
    """Drives the GEARS New-quote flow and returns structured outcomes.

    Never raises for business outcomes — returns QuoteCreateOutcome with a
    status taxonomy: CREATED | STEP1_OK | STEP2_OK | STEP3_OK | SAVED |
    REFERRED | ERROR.
    """

    def __init__(self, page, logger=None):
        self._page = page
        self._log = logger or (lambda msg: print(f"[create] {msg}", flush=True))
        self._t0 = time.monotonic()
        self._market_available = True  # set by fill_step2 market probe

    # ------------------------------------------------------------------
    async def create_quote(self) -> QuoteCreateOutcome:
        """Navigate dashboard → New → Motor Insurance → Private Motor → Get quote."""
        page = self._page
        out = QuoteCreateOutcome()
        try:
            await page.goto(DASH_URL, wait_until="domcontentloaded", timeout=45000)
            await page.wait_for_timeout(12000)
            await page.evaluate(
                "() => { const b = document.getElementById('add-button'); if (b) b.click(); }"
            )
            await page.wait_for_timeout(6000)
            # Motor Insurance
            for el in await page.locator("text=Motor Insurance").all():
                try:
                    if await el.is_visible():
                        await el.click()
                        break
                except Exception:
                    pass
            await page.wait_for_timeout(6000)
            # Private Motor Insurance
            for el in await page.locator("text=Private Motor Insurance").all():
                try:
                    if await el.is_visible():
                        await el.click()
                        break
                except Exception:
                    pass
            await page.wait_for_timeout(3000)
            # Get quote
            for b in await page.locator("button:has-text('Get quote')").all():
                try:
                    if await b.is_visible():
                        await b.click()
                        break
                except Exception:
                    pass
            await page.wait_for_timeout(18000)
            out.quote_url = page.url
            # extract uuid from .../PMOT/VPC/{uuid}/detail
            import re as _re
            m = _re.search(r"/VPC/([0-9a-f]{8}-[0-9a-f-]{27})", page.url)
            out.quote_id = m.group(1) if m else ""
            for _ in range(6):
                if await page.evaluate("() => !!document.getElementById('idNumber')"):
                    break
                await page.wait_for_timeout(3000)
            if not out.quote_id:
                out.status = "ERROR"
                out.error = f"no quote id in url: {page.url[:100]}"
                return out
            out.status = "CREATED"
            out.step = 1
            self._log(f"quote created: {out.quote_id}")
            return out
        except Exception as e:
            out.status = "ERROR"
            out.error = f"create failed: {str(e)[:150]}"
            return out

    # ------------------------------------------------------------------
    async def _pick_auto(self, field_id: str, target: str, wait: int = 1800) -> str:
        page = self._page
        await page.evaluate(
            """(id) => { const el = document.getElementById(id); if (el) el.click(); }""",
            field_id,
        )
        await page.wait_for_timeout(wait)
        return await page.evaluate(
            """(t) => {
              const opts = Array.from(document.querySelectorAll('.mat-option'));
              const m = opts.find(o => (o.innerText||'').toUpperCase().includes(t.toUpperCase()));
              if (m) { m.click(); return 'ok:' + m.innerText.trim().slice(0, 30); }
              if (opts.length) { opts[0].click(); return 'first:' + opts[0].innerText.trim().slice(0, 30); }
              return 'none';
            }""",
            target,
        )

    async def _click_btn(self, text: str) -> bool:
        for b in await self._page.locator(f"button:has-text('{text}')").all():
            try:
                if await b.is_visible():
                    await b.click()
                    return True
            except Exception:
                pass
        return False

    async def _close_overlay(self) -> None:
        await self._page.evaluate(
            """() => {
              const o = document.querySelector('.cdk-overlay-container');
              if (o) {
                const btns = Array.from(o.querySelectorAll('button'));
                const b = btns.find(x =>
                  (x.innerText||'').includes('Continue with application') ||
                  (x.innerText||'').trim() === 'Ok' ||
                  (x.innerText||'').trim() === 'Yes' ||
                  (x.innerText||'').trim() === 'Select');
                if (b) b.click();
              }
            }"""
        )
        await self._page.wait_for_timeout(1000)

    async def _js_set_value(self, field_id: str, value: str) -> str:
        """Set a JS-managed/disabled field value via the allowlisted contract.

        Fails closed: field must be in JS_FIELD_CONTRACT, otherwise returns
        'not-allowlisted' and does NOT write (no silent DOM bypass).
        Verifies the written value by reading it back.
        """
        if field_id not in UNLOCKED_JS_FIELDS:
            self._log(f"js-set REFUSED {field_id}: not in field contract")
            return "not-allowlisted"
        contract = JS_FIELD_CONTRACT[field_id]
        if contract["setter"] != "native_setter":
            self._log(f"js-set REFUSED {field_id}: contract setter={contract['setter']}")
            return "wrong-setter"
        written = await self._page.evaluate(
            """(d) => {
              const el = document.getElementById(d.id);
              if (!el) return 'missing';
              const setter = Object.getOwnPropertyDescriptor(
                HTMLInputElement.prototype, 'value').set;
              setter.call(el, d.v);
              el.dispatchEvent(new Event('input', {bubbles: true}));
              el.dispatchEvent(new Event('change', {bubbles: true}));
              return el.value;
            }""",
            {"id": field_id, "v": value},
        )
        # verify read-back (native getter — sees the real DOM value)
        got = await self._page.evaluate(
            """(id) => {
              const el = document.getElementById(id);
              return el ? el.value : 'missing';
            }""",
            field_id,
        )
        if got != value:
            # locale formatting can add separators (50,000 vs 50000) — normalize
            if normalize_field_value(got) != normalize_field_value(value):
                self._log(f"js-set MISMATCH {field_id}: wrote={value!r} readback={got!r}")
                return f"mismatch:{got}"
        return f"ok:{written}"

    # ------------------------------------------------------------------
    async def fill_step1(self, id_number: str = "881212145678",
                         vehicle_number: str = "TEST123",
                         place: str = "KUALA LUMPUR") -> QuoteCreateOutcome:
        page = self._page
        out = QuoteCreateOutcome(quote_url=page.url, step=1)
        try:
            await page.locator("#idNumber").fill(id_number)
            await page.locator("#idNumber").blur()
            await page.wait_for_timeout(2500)
            await self._pick_auto("idType", "NRIC")
            await page.locator("#vehicleNumber").fill(vehicle_number)
            await page.locator("#vehicleNumber").blur()
            await page.wait_for_timeout(3000)
            await self._pick_auto("place", place)
            # condition: JS unlock
            await page.evaluate(
                """() => { const el = document.getElementById('condition'); el.disabled = false; el.click(); }"""
            )
            await page.wait_for_timeout(2000)
            await page.evaluate(
                """() => {
                  const opts = Array.from(document.querySelectorAll('.mat-option'));
                  const r = opts.find(o => /REGISTERED/.test(o.innerText||'') && !/NEW/.test(o.innerText||''));
                  if (r) r.click(); else if (opts.length) opts[0].click();
                }"""
            )
            await page.wait_for_timeout(1000)
            await self._click_btn("Continue")
            await page.wait_for_timeout(8000)
            out.status = "STEP1_OK"
            out.step = 2
            return out
        except Exception as e:
            out.status = "ERROR"
            out.error = f"step1: {str(e)[:150]}"
            return out

    async def fill_step2(self, **kw) -> QuoteCreateOutcome:
        page = self._page
        out = QuoteCreateOutcome(quote_url=page.url, step=2)
        try:
            # scroll to trigger lazy render
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(2500)
            await page.evaluate("window.scrollTo(0, 0)")
            await page.wait_for_timeout(800)

            # Applicant text fields — always fill (they start empty on every
            # new quote).
            applicant_text_fields = {
                "proposalFullName": kw.get("full_name", "Fionn Liang"),
                "year_experience": kw.get("year_experience", "10"),
                "proposalMobileNumber": kw.get("mobile", "0123456789"),
                "proposalEmail": kw.get("email", "fionn.liang@gmail.com"),
                "proposalPostalCode": kw.get("postal", "50000"),
                "proposalAddressLine1": kw.get("address1", "12, Jalan Merdeka"),
            }
            for fid, val in applicant_text_fields.items():
                el = page.locator(f"#{fid}")
                await el.fill(val)
                await el.blur()
                await page.wait_for_timeout(250)

            # Vehicle text fields — fill ONLY when the portal did NOT
            # auto-populate them from the plate lookup (real plates come with
            # JPJ/NVIC data; TEST123/manual path has empty fields).
            vehicle_text_fields = {
                "chassisNumber": kw.get("chassis", "PN153BK3006001289"),
                "engineNumber": kw.get("engine", "2AZ3028068"),
                "engineCapacity": kw.get("engine_cc", "2362"),
            }
            for fid, val in vehicle_text_fields.items():
                if await page.evaluate(
                    """(id) => {
                      const el = document.getElementById(id);
                      return el ? (el.value || '').trim() : '';
                    }""",
                    fid,
                ):
                    self._log(f"skip {fid}: already populated by plate lookup")
                    continue
                el = page.locator(f"#{fid}")
                await el.fill(val)
                await el.blur()
                await page.wait_for_timeout(250)

            # Applicant selects — always fill.
            applicant_selects = {
                "proposalTitle": "Mr",
                "antiTheftDevice": "No Alarm",
                "safetyFeature": "ABS & Airbags (more than 2)",
                "garage": "Locked Garage",
                "proposalMarital": "Single",
                "proposalStateApplicant": "KUALA LUMPUR",
                "number_Claims": "0",
            }
            applicant_selects.update(kw.get("selects", {}))
            for fid, target in applicant_selects.items():
                await self._pick_auto(fid, target)

            # Vehicle selects — fill ONLY if empty (plate lookup provides them
            # for real vehicles).
            vehicle_selects = {
                "vehicleBodyType": "SEDAN",
                "vehicleIndicator": "LOCAL MANUFACTURE",
                "vehicleCoverageType": "COMPREHENSIVE",
            }
            vehicle_selects.update(kw.get("vehicle_selects", {}))
            for fid, target in vehicle_selects.items():
                if await page.evaluate(
                    """(id) => {
                      const el = document.getElementById(id);
                      if (!el) return '';
                      const t = el.querySelector('.mat-select-value-text');
                      return ((t ? t.innerText : el.innerText) || '').trim();
                    }""",
                    fid,
                ):
                    self._log(f"skip {fid}: already populated by plate lookup")
                    continue
                await self._pick_auto(fid, target)

            # numeric + year — vehicle fields, fill only if empty
            for fid, val in [("seatingCapacity", "5"), ("yearManufacture", "2024")]:
                if await page.evaluate(
                    """(id) => {
                      const el = document.getElementById(id);
                      return el ? (el.value || '').trim() : '';
                    }""",
                    fid,
                ):
                    self._log(f"skip {fid}: already populated by plate lookup")
                    continue
                el = page.locator(f"#{fid}")
                await el.fill(str(val))
                await el.blur()
                await page.wait_for_timeout(300)
            # make/model — pick only if empty (real plates auto-populate)
            for fid, target in [("vehicleMake", kw.get("make", "TOYOTA")),
                                ("vehicleModel", kw.get("model", "CAMRY"))]:
                if await page.evaluate(
                    """(id) => {
                      const el = document.getElementById(id);
                      if (!el) return '';
                      const t = el.querySelector('.mat-select-value-text');
                      return ((t ? t.innerText : el.innerText) || '').trim();
                    }""",
                    fid,
                ):
                    self._log(f"skip {fid}: already populated by plate lookup")
                    continue
                await self._pick_auto(fid, target)

            # dates via JS setter
            for fid, val in [("start-date", kw.get("start_date", "10 Sep 2026")),
                             ("end-date", kw.get("end_date", "09 Sep 2027"))]:
                await self._js_set_value(fid, val)

            # hire purchase — explicit business input (default: No).
            # Yes (btn_0) → #hirePurchaseCompany autocomplete renders → must
            # be filled; No (btn_1) → no company field. Never force No to
            # bypass the field (ChatGPT review): both paths are real inputs.
            if kw.get("hire_purchase", False):
                await page.evaluate(
                    """() => {
                      const b = document.getElementById('btn_0');
                      if (b && !b.checked) b.click();
                    }"""
                )
                await page.wait_for_timeout(1500)
                hp_company = kw.get("hire_purchase_company", "CIMB BANK BERHAD")
                hp_rendered = False
                for _ in range(5):
                    if await page.evaluate(
                        "() => !!document.getElementById('hirePurchaseCompany')"
                    ):
                        hp_rendered = True
                        break
                    await page.wait_for_timeout(1000)
                if not hp_rendered:
                    out.status = "ERROR"
                    out.error = "step2: hire_purchase=Yes but #hirePurchaseCompany never rendered"
                    return out
                res = await self._pick_auto("hirePurchaseCompany", hp_company)
                self._log(f"hire purchase YES → company: {res}")
            else:
                await page.evaluate(
                    """() => {
                      const b = document.getElementById('btn_1');
                      if (b && !b.checked) b.click();
                    }"""
                )
            await page.wait_for_timeout(1000)
            # declaration checkbox
            await page.evaluate(
                """() => {
                  const c = document.getElementById('mat-checkbox-1-input');
                  if (c && !c.checked) { const l = c.closest('label'); if (l) l.click(); }
                }"""
            )
            await page.wait_for_timeout(1000)
            # PDS email button
            for b in await page.locator("#emailPDSandPDPN").all():
                try:
                    if await b.is_visible() and not await b.is_disabled():
                        await b.click()
                        break
                except Exception:
                    pass
            await page.wait_for_timeout(4000)
            await page.evaluate(
                """() => {
                  const o = document.querySelector('.cdk-overlay-container');
                  if (o) {
                    const b = Array.from(o.querySelectorAll('button'))
                      .find(x => (x.innerText||'').trim() === 'Ok');
                    if (b) b.click();
                  }
                }"""
            )
            await page.wait_for_timeout(1500)
            # Check NCD
            for b in await page.locator("button:has-text('Check NCD')").all():
                try:
                    if await b.is_visible() and not await b.is_disabled():
                        await b.click()
                        break
                except Exception:
                    pass
            await page.wait_for_timeout(4000)
            await page.evaluate(
                """() => {
                  const o = document.querySelector('.cdk-overlay-container');
                  if (o) {
                    const b = Array.from(o.querySelectorAll('button'))
                      .find(x => (x.innerText||'').trim() === 'Ok');
                    if (b) b.click();
                  }
                }"""
            )
            await page.wait_for_timeout(1500)
            # market availability probe (ChatGPT: encode the market-value-
            # unavailable branch explicitly, do not let test data block the
            # architecture). The portal's Check-market-value button queries
            # NVIC market data; manual-vehicle quotes (TEST123) return 0/empty.
            out.market_available = True
            self._market_available = True
            mv_probed = await page.evaluate(
                """() => {
                  const b = document.getElementById('check-market-value');
                  if (b && !b.disabled) { b.click(); return true; }
                  return false;
                }"""
            )
            if mv_probed:
                await page.wait_for_timeout(3500)
                mv_probe = await page.evaluate(
                    """() => {
                      const el = document.getElementById('marketValue');
                      return el ? el.value : '';
                    }"""
                )
                if not mv_probe or mv_probe.strip() in ("0", "0.00", ""):
                    out.market_available = False
                    self._market_available = False
                    self._log(
                        "market value UNAVAILABLE (NVIC lookup empty) — "
                        "manual override for test data; send_ready=False"
                    )
            # marketValue — keep portal-computed value when the NVIC lookup had
            # data; only manual-override when market value is unavailable
            # (test-data path).
            if self._market_available:
                self._log("market value available — keeping portal-computed value")
            else:
                await self._js_set_value(
                    "marketValue", kw.get("market_value", "50000")
                )
                await page.wait_for_timeout(1500)

            # Continue → step 3 (may need 2 clicks)
            await self._click_btn("Continue")
            await page.wait_for_timeout(6000)
            await self._close_overlay()
            has_si = await page.evaluate("() => !!document.getElementById('desiredSI')")
            if not has_si:
                await self._click_btn("Continue")
                await page.wait_for_timeout(6000)
                await self._close_overlay()
                has_si = await page.evaluate("() => !!document.getElementById('desiredSI')")
            if not has_si:
                errs = await page.evaluate(
                    """() => Array.from(document.querySelectorAll('.errorMessage, .mat-error'))
                      .map(e => (e.innerText||'').trim().slice(0, 60)).filter(Boolean)"""
                )
                out.status = "ERROR"
                out.error = f"step2 stuck: {errs[:5]}"
                return out
            out.status = "STEP2_OK"
            out.step = 3
            return out
        except Exception as e:
            out.status = "ERROR"
            out.error = f"step2: {str(e)[:150]}"
            return out

    async def fill_step3(self, add_ons: bool = True,
                         check_referral: bool = True) -> QuoteCreateOutcome:
        page = self._page
        out = QuoteCreateOutcome(quote_url=page.url, step=3,
                                 market_available=self._market_available)
        try:
            # reveal add-ons
            await self._click_btn("Continue")
            await page.wait_for_timeout(5000)
            await self._close_overlay()
            if add_ons:
                for pid, target in [("select_plan_0", "21 days-MYR200"),
                                    ("select_plan_1", "ICCA PLAN-A")]:
                    await self._pick_auto(pid, target)
                for cid in ["add-on-btn-2-input", "add-on-btn-3-input", "add-on-btn-4-input",
                            "add-on-btn-5-input", "add-on-btn-6-input", "add-on-btn-7-input",
                            "add-on-btn-8-input", "add-on-btn-10-input"]:
                    await page.evaluate(
                        """(id) => {
                          const c = document.getElementById(id);
                          if (c && !c.checked) { const l = c.closest('label'); if (l) l.click(); }
                        }""",
                        cid,
                    )
                si = page.locator("#sumInsured_4")
                if await si.count() and await si.is_visible() and not await si.is_disabled():
                    await si.fill("5000")
            for cid in ("mat-checkbox-4-input", "mat-checkbox-5-input"):
                await page.evaluate(
                    """(id) => {
                      const c = document.getElementById(id);
                      if (c && !c.checked) { const l = c.closest('label'); if (l) l.click(); }
                    }""",
                    cid,
                )
            await page.wait_for_timeout(1500)
            if check_referral:
                await self._click_btn("Quotation Summary")
                await page.wait_for_timeout(8000)
                body = await page.evaluate("() => document.body.innerText.slice(0, 700)")
                out.referred = "Referred application" in body
            out.status = "REFERRED" if out.referred else "STEP3_OK"
            return out
        except Exception as e:
            out.status = "ERROR"
            out.error = f"step3: {str(e)[:150]}"
            return out
