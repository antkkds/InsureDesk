"""GEARS Driver quote flow — the SINGLE production path (ChatGPT decision B).

This module replaces gears_create.py as the one implementation of the GEARS
portal behavior. Business layer (gears_cli.py, InsureDesk GUI) calls ONLY this:

    run_driver_flow(page, payload, log) -> dict   (full create→save flow)
    send_quote(quote_url, log) -> dict            (send existing quote)

Everything portal-specific lives in GearsDriver (state machine) + FillEngine
(form fills). This module only ORCHESTRATES: it maps a CLI payload onto the
verified step sequence, and returns a stable result dict (build_result shape
compatible with the old CLI contract).

Evidence: VDL1987 E2E 2026-08-10 (premium 1,908.53, SAVE SAVED + SEND SENT).
Contracts discovered on real portal runs are pinned in tests/test_gears_driver.py
and tests/test_vehicle_resolver.py.
"""
from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path
from typing import Any, Callable, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from playwright.async_api import async_playwright  # noqa: E402

from src.quote.gears_driver import GearsDriver  # noqa: E402
from src.quote.gears_save import GearsQuoteSaver  # noqa: E402
from src.quote.gears_send import GearsQuoteSender  # noqa: E402
from src.quote.vehicle_resolver import parse_dialog_rows  # noqa: E402
from src.fill.engine import FillEngine  # noqa: E402
from src.portal.formspec import MotorPrivateCarSpec  # noqa: E402

CDP = "http://127.0.0.1:9333"
DASH_URL = "https://gears-my.greateasterngeneral.com/MY/AgencySales/quotations/dashboard"
FORM_YAML = str(Path(__file__).resolve().parent.parent / "src/portal/forms/motor_private_car.yaml")

DEFAULT_PAYLOAD: dict[str, Any] = {
    "id_number": "881212145678",
    "vehicle_number": "TEST123",
    "place": "KUALA LUMPUR",
    # Commercial (VCV) prerequisites — RESERVED, not yet wired into the VCV
    # flow. GEARS requires a REAL client company TIN/BRN (search-tin must
    # return a company before the embedded vehicle VIX lookup fires).
    # VCV stays disabled in the GUI until verified with a real TIN.
    "tin": "",
    "brn": "",
    "full_name": "Fionn Liang",
    "mobile": "0123456789",
    "email": "fionn.liang@gmail.com",
    "postal": "",           # empty → auto-matched to place (see STATE_POSTCODE)
    "address1": "12, Jalan Merdeka",
    "chassis": "PN153BK3006001289",
    "engine": "2AZ3028068",
    "engine_cc": "2362",
    "make": "TOYOTA",
    "model": "CAMRY",
    "year_manufacture": 2024,
    "seating_capacity": 5,
    "hire_purchase": False,
    "hire_purchase_company": "CIMB BANK BERHAD",
    "market_value": "50000",
    "start_date": "10 Sep 2026",
    "end_date": "09 Sep 2027",
    "add_ons": True,
    "check_referral": True,
    "save": True,
}


def build_result(**kw: Any) -> dict[str, Any]:
    """Stable result dict (same shape as the old gears_cli contract)."""
    r: dict[str, Any] = {
        "ok": False,
        "status": "ERROR",
        "quote_id": "",
        "quote_url": "",
        "step": 0,
        "referred": False,
        "market_available": True,
        "send_ready": False,
        "saved": False,
        "save_status": "",
        "doc_name": "",
        "version": -1,
        "send_status": "",
        "send_email": "",
        "send_http": None,
        "error": "",
        "elapsed": 0.0,
    }
    r.update(kw)
    return r


def parse_payload(raw: str) -> tuple[Optional[dict], Optional[str]]:
    """Parse + validate the run payload (same contract as old CLI)."""
    import json

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        return None, f"payload is not valid JSON: {e}"
    if not isinstance(data, dict):
        return None, "payload must be a JSON object"
    payload = dict(DEFAULT_PAYLOAD)
    payload.update({k: v for k, v in data.items() if v is not None})
    for key in ("hire_purchase", "add_ons", "check_referral", "save"):
        if key in payload:
            v = payload[key]
            if isinstance(v, str):
                payload[key] = v.strip().lower() in ("1", "true", "yes", "on")
            payload[key] = bool(payload[key])
    for key in ("year_manufacture", "seating_capacity"):
        if key in payload:
            try:
                payload[key] = int(payload[key])
            except (TypeError, ValueError):
                payload[key] = DEFAULT_PAYLOAD[key]
    if not str(payload["vehicle_number"]).strip():
        return None, "vehicle_number is required"
    return payload, None


async def js_click(page, text: str, tag: str = "button") -> bool:
    """Click first visible element with the given text (KNOWN_STATE)."""
    for el in await page.locator(f"{tag}:has-text('{text}')").all():
        try:
            if await el.is_visible():
                await el.click()
                return True
        except Exception:
            continue
    return False


def _step1_data(p: dict[str, Any]) -> dict[str, Any]:
    return {
        "applicant_type": "individual",
        "condition": "REGISTERED",
        "id_type": "NRIC",
        "id_number": p["id_number"],
        "sst_number": "",
        "vehicle_number": p["vehicle_number"],
        "place": p["place"],
    }


# Postcode auto-match: the Details section validates postcode↔state. A KL
# postcode (50000) with a SABAH place fails validation ("Please provide valid
# postcode") and blocks Step 2 — verified live 2026-08-12. Agents type the
# place; the postcode follows the state unless the payload explicitly sets one.
STATE_POSTCODE: dict[str, str] = {
    "PERLIS": "01000", "KEDAH": "05000", "PULAU PINANG": "10000",
    "PERAK": "30000", "SELANGOR": "40000", "KUALA LUMPUR": "50000",
    "PUTRAJAYA": "62000", "NEGERI SEMBILAN": "70000", "MELAKA": "75000",
    "JOHOR": "80000", "PAHANG": "25000", "TERENGGANU": "20000",
    "KELANTAN": "15000", "SABAH": "88000", "SARAWAK": "93000",
    "LABUAN": "87000", "LANGKAWI": "07000",
}


def _postcode_for(p: dict[str, Any]) -> str:
    """Explicit payload postcode wins; otherwise match the state."""
    postal = str(p.get("postal", "")).strip()
    if postal:
        return postal
    return STATE_POSTCODE.get(str(p.get("place", "")).upper(), "50000")


def _details_data(p: dict[str, Any]) -> dict[str, Any]:
    """Details-section data. POL-1: customer attributes come from the payload
    (validated request data), NEVER hardcoded. Gender/salutation are derived
    from the NRIC when the request does not carry them (legit derivation, not
    fabrication); body_type is AUTO from the vehicle lookup (omit → portal
    keeps its looked-up value)."""
    hp = "Y" if p["hire_purchase"] else "N"

    # Gender: request value wins, else derived from NRIC parity (legal).
    gender = str(p.get("gender", "")).strip() or _gender_from_nric(str(p.get("id_number", "")))
    # Salutation follows gender (legal derivation — never a hardcoded Mr).
    salutation = {"M": "Mr", "F": "Ms"}.get(gender.upper(), "")

    data = {
        "salutation": salutation,
        "fullname": p["full_name"],
        "gender": gender,
        "marital_status": p["marital_status"],
        "years_driving_exp": str(p["years_driving_exp"]),
        "mobile": p["mobile"],
        "email": p["email"],
        "pds_consent": True,
        "postcode": _postcode_for(p),
        "state": p["place"],
        "address1": p["address1"],
        "seating_capacity": str(p.get("seating_capacity", "")),
        "safety_feature": "ABS & Airbags (more than 2)",
        "hire_purchase": hp,
        # portal REQUIRES these despite spec required:false (live evidence 2026-08-10)
        "anti_theft_device": "W/O Mech - No Alarm",
        "garage": "Locked Garage",
    }
    # body_type: only when the request supplied it; otherwise the portal's
    # AUTO value from the vehicle lookup is kept (omit from data).
    if str(p.get("body_type", "")).strip():
        data["body_type"] = p["body_type"]
    return data


def _gender_from_nric(id_number: str) -> str:
    """NRIC 12th digit parity: odd → M, even → F (IdentityDataValidator rule)."""
    digits = "".join(ch for ch in str(id_number) if ch.isdigit())
    if len(digits) == 12:
        return "M" if int(digits[-1]) % 2 == 1 else "F"
    return ""


async def _fill_section(engine, adapter, spec, sec: str, data: dict[str, Any]) -> tuple[bool, str]:
    schema = spec.live_schema(sec)
    if schema is None:
        return False, f"live_schema({sec}) is None"
    r = await engine.fill_section(adapter, schema, data)
    ok = sum(1 for f in r.fields if f.success)
    bad = [f.field for f in r.fields if not f.success and "Skipped" not in (f.message or "")]
    if bad:
        return False, f"{ok}/{len(r.fields)} ok bad={bad}"
    return True, f"{ok}/{len(r.fields)} ok"


async def run_driver_flow(page, payload: dict[str, Any], log: Callable[[str], None]) -> dict[str, Any]:
    """Full Driver flow: create → step1 → step2 → step3 → save (single path)."""
    from gears_live_adapter import GearsPageAdapter  # local import (adapter dep)

    t0 = time.monotonic()
    driver = GearsDriver(page, step_timeout=40.0)

    # ---- 0. session health (reuse existing tab, NEVER new GEGLink tab) ----
    sess = await driver.check_session()
    if not sess.ok:
        # caller already connected to a healthy tab; if trapped, fail structured
        return build_result(status="SESSION_EXPIRED",
                            error=sess.detail, elapsed=time.monotonic() - t0)
    log(f"session healthy at {page.url[:60]}")

    # ---- 1. CREATE (dashboard → New → PMOT → Get quote) ----
    await page.goto(DASH_URL, wait_until="domcontentloaded", timeout=45000)
    await page.wait_for_timeout(4000)
    await js_click(page, "New")
    await page.wait_for_timeout(4000)
    out = await driver.select_product("PMOT")
    if not out.ok:
        return build_result(status="CREATE_FAILED", error=out.detail,
                            elapsed=time.monotonic() - t0)
    await page.wait_for_timeout(6000)
    await js_click(page, "Ok")
    await page.wait_for_timeout(3000)

    # early #vehicle-NVIC-dialog (known state: exact-match auto-select)
    early = await page.evaluate("document.getElementById('vehicle-NVIC-dialog') ? true : false")
    if early:
        dlg_text = await page.evaluate("document.getElementById('vehicle-NVIC-dialog').innerText")
        rows = parse_dialog_rows(dlg_text)
        log(f"early NVIC dialog: {len(rows)} rows {[r.nvic for r in rows][:6]}")
        if len(rows) == 1:
            await page.evaluate("""(() => {
                const btns = Array.from(document.querySelectorAll('#vehicle-NVIC-dialog button'));
                const hit = btns.find(e => (e.textContent||'').includes('Select'));
                if (hit) hit.click();
            })()""")
            await page.wait_for_timeout(2500)
        elif len(rows) > 1:
            return build_result(status="NVIC_CONFLICT",
                                error=f"early dialog {[r.nvic for r in rows]}",
                                elapsed=time.monotonic() - t0)

    out = await driver.wait_quote_ready("#condition", max_wait=45.0)
    if not out.ok:
        return build_result(status="CREATE_FAILED", error=out.detail,
                            elapsed=time.monotonic() - t0)
    quote_url = page.url
    if "/VPC/" in quote_url:
        quote_id = quote_url.split("/VPC/")[-1].split("/")[0]
    else:
        quote_id = ""
    log(f"quote created: {quote_id[:36]}  step1 reached")

    # ---- 2. STEP1 fill (existing FillEngine, verified selectors) ----
    spec = MotorPrivateCarSpec.from_yaml_file(FORM_YAML)
    engine = FillEngine()
    adapter = GearsPageAdapter(page)
    ok, msg = await _fill_section(engine, adapter, spec, "quotation_details", _step1_data(payload))
    if not ok:
        return build_result(status="STEP1_FAILED", quote_url=quote_url, quote_id=quote_id,
                            error=msg, step=1, elapsed=time.monotonic() - t0)
    log(f"step 1 OK ({msg})")

    # ---- 3. Continue → NVIC identity (driver handles dialog OR auto-resolve) ----
    await js_click(page, "Continue")
    await page.wait_for_timeout(6000)
    out = await driver.resolve_nvic_variant()
    src = driver._outcome.vehicle.get("nvic_source", "dialog")
    if not out.ok:
        return build_result(status=out.failure.name, quote_url=quote_url, quote_id=quote_id,
                            error=out.detail, step=1, elapsed=time.monotonic() - t0)
    nvic = driver._outcome.vehicle.get("nvic", "")
    log(f"NVIC resolved: {nvic} (source={src})")
    await page.wait_for_timeout(4000)

    # ---- 4. BUSINESS GATES (driver contract) ----
    out = await driver.check_market_value()
    if not out.ok:
        return build_result(status=out.failure.name, quote_url=quote_url, quote_id=quote_id,
                            error=out.detail, step=2, elapsed=time.monotonic() - t0)
    mv = driver._outcome.vehicle.get("market_value", "")
    log(f"market value: {mv}")

    out = await driver.check_ncd()
    if not out.ok:
        return build_result(status=out.failure.name, quote_url=quote_url, quote_id=quote_id,
                            error=out.detail, step=2, elapsed=time.monotonic() - t0)
    ncd = driver._outcome.vehicle.get("ncd", "")
    if "ncd_warning" in driver._outcome.vehicle:
        log(f"NCD={ncd} (warning: {driver._outcome.vehicle['ncd_warning'][:80]})")
    else:
        log(f"NCD={ncd}")

    # ---- 5. STEP2: owner/address/vehicle + PDS + dates ----
    for sec in ("owner", "address", "vehicle"):
        ok, msg = await _fill_section(engine, adapter, spec, sec, _details_data(payload))
        if not ok:
            return build_result(status="STEP2_FAILED", quote_url=quote_url, quote_id=quote_id,
                                error=f"{sec}: {msg}", step=2, elapsed=time.monotonic() - t0)
        log(f"step 2 {sec} OK ({msg})")

    out = await driver.complete_pds_gate()
    if not out.ok:
        return build_result(status=out.failure.name, quote_url=quote_url, quote_id=quote_id,
                            error=out.detail, step=2, elapsed=time.monotonic() - t0)
    log("PDS gate OK")

    await page.evaluate("(() => { const el = document.getElementById('number_Claims'); if (el) el.removeAttribute('disabled'); })()")
    await page.wait_for_timeout(1000)
    out = await driver.set_dates(payload["start_date"], payload["end_date"])
    if not out.ok:
        return build_result(status="STEP2_FAILED", quote_url=quote_url, quote_id=quote_id,
                            error=out.detail, step=2, elapsed=time.monotonic() - t0)
    await page.wait_for_timeout(1000)
    log("dates set")

    # ---- 6. Continue → STEP3 (verify we actually arrived) ----
    # ENQ008 (NCD reset) warning can surface asynchronously AFTER check_ncd
    # and block Continue — dismiss any known dialog first (VDL1987 evidence).
    blocker = await driver.dismiss_dialog()
    if blocker:
        return build_result(status="RENEWAL_BLOCKED", quote_url=quote_url, quote_id=quote_id,
                            error=f"blocker before step3: {blocker}", step=2,
                            elapsed=time.monotonic() - t0)
    await js_click(page, "Continue")
    arrived = False
    errs: list[str] = []
    for _ in range(10):
        await page.wait_for_timeout(2000)
        has_si = await page.evaluate("document.getElementById('desiredSI') ? true : false")
        if has_si:
            arrived = True
            break
    if not arrived:
        errs = await page.evaluate(
            "Array.from(document.querySelectorAll('.mat-error, [class*=error]'))"
            ".map(e => (e.innerText||'').trim()).filter(Boolean).slice(0,5)")
        return build_result(status="STEP3_ARRIVE_FAILED", quote_url=quote_url, quote_id=quote_id,
                            error=f"stayed on Details; errors={errs}", step=2,
                            elapsed=time.monotonic() - t0)
    log("step 3 arrived")

    out = await driver.set_desired_si(str(payload["market_value"]))
    if not out.ok:
        return build_result(status="STEP3_FAILED", quote_url=quote_url, quote_id=quote_id,
                            error=out.detail, step=3, elapsed=time.monotonic() - t0)
    await page.wait_for_timeout(2000)

    out = await driver.check_declarations()
    if not out.ok:
        return build_result(status="STEP3_FAILED", quote_url=quote_url, quote_id=quote_id,
                            error=out.detail, step=3, elapsed=time.monotonic() - t0)

    # step-3 Continue (Sum Insured section) → computes premium, enables Send
    out = await driver.continue_step3(max_wait=40.0)
    if not out.ok:
        return build_result(status="STEP3_FAILED", quote_url=quote_url, quote_id=quote_id,
                            error=out.detail, step=3, elapsed=time.monotonic() - t0)
    premium = driver._outcome.premium
    log(f"step 3 continue: premium-so-far={premium}")

    out = await driver.verify_ready()
    if not out.ok:
        return build_result(status="STEP3_FAILED", quote_url=quote_url, quote_id=quote_id,
                            error=out.detail, step=3, elapsed=time.monotonic() - t0)
    # re-read premium AFTER verify_ready — that's where the regex captures it
    # (continue_step3 only enables the buttons; the premium text lands during
    # verify_ready's body scan). ChatGPT rank-1: business result must be real.
    premium = driver._outcome.premium
    log(f"step 3 done: premium={premium}")
    result = build_result(
        status="STEP3_OK", quote_url=quote_url, quote_id=quote_id,
        send_ready=True, step=3, premium=premium,
        market_available=bool(mv), elapsed=time.monotonic() - t0,
    )
    result["nvic"] = nvic
    result["market_value"] = mv
    result["ncd"] = ncd
    result["premium"] = premium

    # ---- 7. SAVE (existing structured module) ----
    if payload["save"]:
        log("[save] saving as draft")
        saver = GearsQuoteSaver(page)
        so = await saver.save_as_draft()
        result["saved"] = so.ok
        result["save_status"] = so.status
        result["doc_name"] = so.doc_name
        result["version"] = so.version
        log(f"save: {so.status} doc={so.doc_name or '-'} ver={so.version}")
        if not so.ok:
            result["error"] = so.error or f"save {so.status}"
        else:
            result["status"] = "SAVED"
    else:
        log("save skipped (save=false)")
        result["save_status"] = "SKIPPED"

    result["ok"] = result["status"] in ("STEP3_OK", "SAVED") and \
        (not result["saved"] or result["save_status"] == "SAVED")
    result["elapsed"] = round(time.monotonic() - t0, 1)
    return result


async def send_existing(quote_url: str, log: Callable[[str], None]) -> dict[str, Any]:
    """Send-application on an existing quote (must be complete/non-referred).

    TAB DISCIPLINE (IRON RULE, learned 2026-08-10): keep ONE persistent GEARS
    tab and reuse it for every operation. NEVER open-close-open in a loop —
    frequent login cycles look like credential abuse to the portal's risk
    engine and lock the account. If no GEARS tab exists, open one and LEAVE
    it open as the resident tab. Session expiry is handled by the guard
    (re-login only when truly EXPIRED), never by tab churn.
    """
    t0 = time.monotonic()
    try:
        async with async_playwright() as p:
            browser = await p.chromium.connect_over_cdp(CDP)
            ctx = browser.contexts[0]
            page = None
            for pg in ctx.pages:
                if "gears-my" in pg.url:
                    page = pg
                    break
            if not page:
                # no resident GEARS tab — create ONE and keep it (do NOT close)
                page = await ctx.new_page()
                log("no resident GEARS tab — opened one (kept as resident)")
            log(f"sending application for: {quote_url[:90]}")
            sender = GearsQuoteSender(page)
            so = await sender.send_application(quote_url=quote_url)
            log(f"send: {so.status} email={so.email} http={so.http_status}")
            result = build_result(
                status=so.status,
                quote_url=quote_url,
                ok=so.ok,
                error=so.error or "",
                elapsed=round(time.monotonic() - t0, 1),
            )
            if so.quote_id:
                result["quote_id"] = so.quote_id
            result["send_status"] = so.status
            result["send_email"] = so.email
            result["send_http"] = so.http_status
            return result
    except Exception as e:  # noqa: BLE001 — bridge must never crash silently
        return build_result(error=f"{type(e).__name__}: {str(e)[:200]}",
                            elapsed=time.monotonic() - t0)


async def check_status(log: Callable[[str], None]) -> dict[str, Any]:
    """Cheap CDP health check — no quote flow."""
    try:
        async with async_playwright() as p:
            browser = await p.chromium.connect_over_cdp(CDP)
            ctx = browser.contexts[0]
            pages = ctx.pages
            gears = [pg for pg in pages if "greateasterngeneral.com" in pg.url]
            return {
                "ok": True,
                "cdp_alive": True,
                "tabs": len(pages),
                "gears_tabs": len(gears),
                "detail": f"CDP 9333 alive — {len(gears)} GEARS tab(s), {len(pages)} total",
            }
    except Exception as e:  # noqa: BLE001
        return {
            "ok": False,
            "cdp_alive": False,
            "tabs": 0,
            "gears_tabs": 0,
            "detail": f"CDP 9333 unreachable: {str(e)[:120]}",
        }
