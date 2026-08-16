"""MotorProductFlow — GEARS Private Motor read-only quote flow entry.

Motor-1 (ChatGPT 2026-08-16): the second product must pass through the SAME
architecture shape as PA. pa_adapter.run_pa_quote_via_cdp is the PA entry;
this module is the motor twin:

    MotorProductCapability.execute
        ↓
    run_motor_quote_via_cdp(payload, log)     ← this module
        ↓
    run_driver_flow(page, payload, log)       ← SINGLE production path (scripts/)
        ↓
    GearsDriver state machine + FillEngine + motor_private_car.yaml

Read-only guarantee: the flow NEVER clicks Send/Submit/Issue. ``save`` is
defaulted to False at the CONTRACT layer (the manifest safety scope is
readonly); an explicit ``save: true`` is required to store a draft, exactly
like the GUI's own gears_cli path.

Execution trace ends with::

    ok=true
    status=STEP3_OK|SAVED
    quote_id=...  nvic=...  market_value=...  ncd=...  premium=...
    submission_attempted=false
    send_attempted=false
    issue_attempted=false
    execution_mode=real
"""

from __future__ import annotations

import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Optional

# The single production orchestration lives in scripts/ (gears_driver_flow).
# Import it lazily with the scripts dir on sys.path — same pattern the CLI
# uses to import src. Production logic stays in ONE place.
SCRIPTS_DIR = str(Path(__file__).resolve().parent.parent.parent / "scripts")

CDP_URL = "http://127.0.0.1:9333"


def _load_driver_flow():
    if SCRIPTS_DIR not in sys.path:
        sys.path.insert(0, SCRIPTS_DIR)
    from gears_driver_flow import DEFAULT_PAYLOAD, parse_payload, run_driver_flow

    return DEFAULT_PAYLOAD, parse_payload, run_driver_flow


def parse_motor_payload(raw: str) -> tuple[Optional[dict], Optional[str]]:
    """Parse + validate the motor run payload (same contract as gears_cli)."""
    _, parse_payload, _ = _load_driver_flow()
    return parse_payload(raw)


def build_motor_payload(arguments: dict[str, Any]) -> dict[str, Any]:
    """Build the motor run payload from REQUEST data only (POL-1).

    POL-1 (2026-08-16): customer data is NEVER fabricated from test
    fixtures. The old implementation merged DEFAULT_PAYLOAD (which carries
    a synthetic IC/name/mobile/email/address) and silently filled whatever
    the request omitted — wrong identity/contact on a real quote.

    Now: the flow defaults are only used for NON-customer runtime values
    (policy dates are computed fresh; business toggles like hire_purchase
    default false). All customer fields must come from the request —
    validate() guarantees the required set, so any still-empty customer
    field here means a caller bypassed the gate: fail loudly.
    """
    _, parse_payload, _ = _load_driver_flow()

    # Runtime defaults that are NOT customer data:
    today = datetime.now()
    payload: dict[str, Any] = {
        "hire_purchase": False,
        "add_ons": True,
        "check_referral": True,
        "save": False,  # contract-layer default: read-only (manifest scope)
    }
    payload.update({k: v for k, v in arguments.items() if v is not None})

    # Policy dates: default to start today+7d / end today+7d+1y (fresh, never
    # a stale fixture date). Explicit request dates win.
    if not str(payload.get("start_date", "")).strip():
        start = (today + timedelta(days=7)).strftime("%d %b %Y")
        payload["start_date"] = start
    if not str(payload.get("end_date", "")).strip():
        end = (today + timedelta(days=7 + 365)).strftime("%d %b %Y")
        payload["end_date"] = end

    # POL-1: customer fields MUST come from the request. validate() already
    # enforced required; this is a defense-in-depth for direct callers.
    customer_fields = ("id_number", "vehicle_number", "place", "full_name",
                       "mobile", "email", "address1", "marital_status",
                       "years_driving_exp")
    missing = [f for f in customer_fields if not str(payload.get(f, "")).strip()]
    if missing:
        raise ValueError(
            f"customer field(s) missing (never defaulted): {', '.join(missing)}")

    return payload


def build_motor_result(**kw: Any) -> dict[str, Any]:
    """Stable motor result dict (execution flags always present)."""
    r: dict[str, Any] = {
        "ok": False,
        "status": "ERROR",
        "quote_id": "",
        "quote_url": "",
        "step": 0,
        "premium": "",
        "nvic": "",
        "market_value": "",
        "ncd": "",
        "send_ready": False,
        "saved": False,
        "save_status": "SKIPPED",
        "submission_attempted": False,
        "send_attempted": False,
        "issue_attempted": False,
        "execution_mode": "real",
        "error": "",
        "elapsed": 0.0,
    }
    r.update(kw)
    return r


async def run_motor_quote_via_cdp(
    payload: dict[str, Any],
    log: Callable[[str], None],
    cdp_url: str = CDP_URL,
) -> dict[str, Any]:
    """Connect CDP 9333, reuse the resident GEARS tab, run the Driver flow.

    Memory rule: ONE resident tab, NEVER open-close-open, NEVER relogin —
    the flow reuses the existing gears-my tab; session handling belongs to
    the session guard, not here.
    """
    from playwright.async_api import async_playwright

    t0 = time.monotonic()
    try:
        async with async_playwright() as p:
            log("connecting to Chrome CDP 9333 …")
            browser = await p.chromium.connect_over_cdp(cdp_url)
            ctx = browser.contexts[0]
            page = None
            for pg in ctx.pages:
                if "gears-my" in pg.url:
                    page = pg
                    break
            if page is None:
                # No existing GEARS tab — session guard will handle SSO.
                page = await ctx.new_page()
                log("no resident GEARS tab — opened fresh (guard handles SSO)")
            else:
                log(f"reusing resident tab: {page.url[:70]}")

            _, _, run_driver_flow = _load_driver_flow()
            result = await run_driver_flow(page, payload, log)

            # Contract normalization: execution flags (never send/submit/issue)
            flags = {
                "submission_attempted": False,
                "send_attempted": False,
                "issue_attempted": False,
                "execution_mode": "real",
                "elapsed": round(time.monotonic() - t0, 1),
            }
            flags.update({k: v for k, v in result.items() if k in flags})
            result.update(flags)
            return result
    except Exception as e:  # noqa: BLE001 — structured failure
        log(f"motor flow error: {e}")
        return build_motor_result(error=str(e), elapsed=round(time.monotonic() - t0, 1))
