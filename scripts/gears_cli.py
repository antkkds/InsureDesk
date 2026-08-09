"""GEARS Motor quote CLI bridge — the single automation entry point for the
InsureDesk Windows GUI.

The GUI (Windows) invokes this via::

    wsl.exe -e bash -lc "cd /home/antkk/InsureDesk && \\
        venv/bin/python -X utf8 scripts/gears_cli.py run '<json payload>'"

Contract:
- Progress lines are printed to STDERR (human-readable, streamed to the GUI log).
- The final structured result is ONE JSON line on STDOUT prefixed ``RESULT:``
  (the GUI parses only the last RESULT: line; everything else is progress).

Actions:
    status              — cheap CDP health check (is the GEARS Chrome alive?)
    run                 — full flow: create → step1 → step2 → step3 → save
    send <quote_url>    — send-application on an existing complete quote

`run` payload fields (all optional, defaults match the live-verified flow):
    id_number, vehicle_number, place
    full_name, mobile, email, postal, address1
    chassis, engine, engine_cc, make, model
    year_manufacture, seating_capacity
    hire_purchase (bool), hire_purchase_company
    market_value, start_date, end_date
    add_ons (bool), check_referral (bool), save (bool)
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any, Callable, Optional

# make `src` importable regardless of how the CLI is invoked (script dir is
# scripts/, not the project root — sys.path[0] alone is NOT enough)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

CDP = "http://127.0.0.1:9333"
DASH_URL = "https://gears-my.greateasterngeneral.com/MY/AgencySales/quotations/dashboard"

DEFAULT_PAYLOAD: dict[str, Any] = {
    "id_number": "881212145678",
    "vehicle_number": "TEST123",
    "place": "KUALA LUMPUR",
    "full_name": "Fionn Liang",
    "mobile": "0123456789",
    "email": "fionn.liang@gmail.com",
    "postal": "50000",
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


# ---------------------------------------------------------------------------
# Pure helpers (unit-testable without a browser)
# ---------------------------------------------------------------------------

def parse_payload(raw: str) -> tuple[Optional[dict], Optional[str]]:
    """Parse + validate the run payload. Returns (payload, error)."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        return None, f"payload is not valid JSON: {e}"
    if not isinstance(data, dict):
        return None, "payload must be a JSON object"
    payload = dict(DEFAULT_PAYLOAD)
    payload.update({k: v for k, v in data.items() if v is not None})
    # type coercion for the boolean/int fields that the GUI sends as strings
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


def build_result(**kw: Any) -> dict[str, Any]:
    """Normalize the CLI result dict (stable keys for the GUI)."""
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


# ---------------------------------------------------------------------------
# Live flow
# ---------------------------------------------------------------------------

async def run_flow(payload: dict[str, Any], log: Callable[[str], None]) -> dict[str, Any]:
    """Full create → step1 → step2 → step3 → save flow on the real portal."""
    from playwright.async_api import async_playwright

    from src.quote.gears_create import GearsQuoteCreator
    from src.quote.gears_save import GearsQuoteSaver

    t0 = time.monotonic()
    try:
        async with async_playwright() as p:
            log("connecting to Chrome CDP 9333 …")
            browser = await p.chromium.connect_over_cdp(CDP)
            ctx = browser.contexts[0]
            page = await ctx.new_page()
            log("connected — starting quote flow")

            creator = GearsQuoteCreator(page, logger=log)

            log("[1/5] create quote (dashboard → New → Motor → Get quote)")
            o = await creator.create_quote()
            if o.status != "CREATED":
                return build_result(status=o.status, quote_url=o.quote_url,
                                    error=o.error or "create failed",
                                    elapsed=time.monotonic() - t0)
            log(f"quote created: {o.quote_id}  step1 reached")

            log("[2/5] step 1 — customer + vehicle")
            o = await creator.fill_step1(
                id_number=payload["id_number"],
                vehicle_number=payload["vehicle_number"],
                place=payload["place"],
            )
            if o.status != "STEP1_OK":
                return build_result(status=o.status, quote_url=o.quote_url,
                                    quote_id=creator._page.url.split("/VPC/")[-1][:36],
                                    error=o.error or "step1 failed",
                                    elapsed=time.monotonic() - t0)
            log("step 1 OK")

            log("[3/5] step 2 — applicant + vehicle details + dates")
            o = await creator.fill_step2(
                full_name=payload["full_name"],
                mobile=payload["mobile"],
                email=payload["email"],
                postal=payload["postal"],
                address1=payload["address1"],
                chassis=payload["chassis"],
                engine=payload["engine"],
                engine_cc=payload["engine_cc"],
                make=payload["make"],
                model=payload["model"],
                year_manufacture=payload["year_manufacture"],
                seating_capacity=payload["seating_capacity"],
                start_date=payload["start_date"],
                end_date=payload["end_date"],
                hire_purchase=payload["hire_purchase"],
                hire_purchase_company=payload["hire_purchase_company"],
                market_value=payload["market_value"],
            )
            if o.status != "STEP2_OK":
                return build_result(status=o.status, quote_url=o.quote_url,
                                    error=o.error or "step2 failed",
                                    elapsed=time.monotonic() - t0)
            log(f"step 2 OK (market_available={o.market_available})")

            log("[4/5] step 3 — sum insured + add-ons + declarations")
            o = await creator.fill_step3(add_ons=payload["add_ons"],
                                         check_referral=payload["check_referral"])
            if o.status == "ERROR":
                return build_result(status=o.status, quote_url=o.quote_url,
                                    error=o.error or "step3 failed",
                                    elapsed=time.monotonic() - t0)
            log(f"step 3 done: status={o.status} referred={o.referred}")

            result = build_result(
                status=o.status, quote_url=o.quote_url,
                referred=o.referred, market_available=o.market_available,
                send_ready=o.send_ready, step=o.step,
                elapsed=time.monotonic() - t0,
            )
            # quote id from URL
            url = o.quote_url or page.url
            if "/VPC/" in url:
                result["quote_id"] = url.split("/VPC/")[-1].split("/")[0]

            if o.referred:
                log("REFERRED — skipping save (Submit-for-review path)")
                result["status"] = "REFERRED"
                return result

            if payload["save"]:
                log("[5/5] save as draft")
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
                log("save skipped (save=false)")
                result["save_status"] = "SKIPPED"

            result["ok"] = (result["status"] in ("STEP3_OK", "SAVED", "CREATED")) \
                and (not result["saved"] or result["save_status"] == "SAVED") \
                and (not payload["save"] or result["save_status"] == "SAVED")
            result["elapsed"] = round(time.monotonic() - t0, 1)
            return result
    except Exception as e:  # noqa: BLE001 — bridge must never crash silently
        return build_result(error=f"{type(e).__name__}: {str(e)[:200]}",
                            elapsed=time.monotonic() - t0)


async def send_quote(quote_url: str, log: Callable[[str], None]) -> dict[str, Any]:
    """Send-application on an existing quote (must be complete/non-referred)."""
    from playwright.async_api import async_playwright

    from src.quote.gears_send import GearsQuoteSender

    t0 = time.monotonic()
    try:
        async with async_playwright() as p:
            log("connecting to Chrome CDP 9333 …")
            browser = await p.chromium.connect_over_cdp(CDP)
            ctx = browser.contexts[0]
            page = await ctx.new_page()
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
    from playwright.async_api import async_playwright

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


def main(argv: Optional[list[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print("usage: gears_cli.py <status|run|send> [payload-json|quote-url]", file=sys.stderr)
        return 2

    action = argv[0]

    def log(msg: str) -> None:
        print(f"[{time.strftime('%H:%M:%S')}] {msg}", file=sys.stderr, flush=True)

    if action == "status":
        result = asyncio.run(check_status(log))
        print("RESULT:" + json.dumps(result, ensure_ascii=False))
        return 0 if result["ok"] else 1

    if action == "run":
        payload_raw = argv[1] if len(argv) > 1 else "{}"
        if payload_raw == "-":
            # payload comes from stdin (GUI pipes JSON — avoids shell quoting)
            payload_raw = sys.stdin.read()
        payload, err = parse_payload(payload_raw)
        if err:
            print("RESULT:" + json.dumps(build_result(error=err), ensure_ascii=False))
            return 2
        assert payload is not None  # err is None ⇒ payload valid
        log(f"run payload: vehicle={payload['vehicle_number']} "
            f"hp={payload['hire_purchase']} save={payload['save']}")
        result = asyncio.run(run_flow(payload, log))
        print("RESULT:" + json.dumps(result, ensure_ascii=False))
        return 0 if result["ok"] else 1

    if action == "send":
        quote_url = argv[1] if len(argv) > 1 else ""
        if not quote_url:
            print("usage: gears_cli.py send <quote_url>", file=sys.stderr)
            return 2
        result = asyncio.run(send_quote(quote_url, log))
        print("RESULT:" + json.dumps(result, ensure_ascii=False))
        return 0 if result["ok"] else 1

    print(f"unknown action: {action}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
