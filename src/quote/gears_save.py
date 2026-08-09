"""GEARS Motor (PMOT) quote Save capability — verified flow 2026-08-09.

Real Save flow on the GEARS Angular app (NOT a direct API call — the store
API requires an Angular-injected per-session `Token-Request` header that
cannot be replicated externally):

    click "Save as draft"  →  confirmation dialog appears
        ("Do you want to save the quotation as draft?")
    click dialog "Save"    →  PUT https://store-my.../quotations/PMOT/VPC/{id}
    → HTTP 200 (echo of full quotation)  →  app navigates to dashboard

The PUT is an idempotent upsert (version stays 0, no duplicate drafts).

Usage:
    saver = GearsQuoteSaver(page)
    outcome = await saver.save_as_draft()
    if outcome.status == "SAVED":
        print(outcome.doc_name, outcome.quote_id, outcome.version)

Failure taxonomy (structured, not "generic error"):
    SAVED             PUT 200 + quotation echo parsed
    DIALOG_TIMEOUT    confirmation dialog never appeared
    PUT_FAILED        dialog confirmed but PUT missing/non-200
    SESSION_EXPIRED   page ended on a login/forcelogout trap
    NETWORK_ERROR     listener/parse failure
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Optional

SAVE_BTN_TEXT = "Save as draft"
DIALOG_SAVE_TEXT = "Save"
DIALOG_PROBE_MS = 8000      # wait for confirmation dialog
PUT_WAIT_MS = 30000         # wait for the PUT request/response
NAV_WAIT_MS = 15000         # wait for post-save navigation

# PUT URL shape: https://store-my.greateasterngeneral.com/my/v1/ife/general/quotations/PMOT/VPC/{id}
PUT_MARKER = "/my/v1/ife/general/quotations/PMOT/VPC/"


@dataclass
class SaveOutcome:
    """Structured result of one save attempt."""

    status: str = "PENDING"          # SAVED | DIALOG_TIMEOUT | PUT_FAILED | SESSION_EXPIRED | NETWORK_ERROR
    quote_id: str = ""
    version: int = -1
    doc_name: str = ""
    business_status: str = ""
    operation_status: str = ""
    http_status: Optional[int] = None
    payload_bytes: int = 0
    error: str = ""
    attempt: int = 0
    ts: float = field(default_factory=time.time)

    @property
    def ok(self) -> bool:
        return self.status == "SAVED"

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "quote_id": self.quote_id,
            "version": self.version,
            "doc_name": self.doc_name,
            "business_status": self.business_status,
            "operation_status": self.operation_status,
            "http_status": self.http_status,
            "payload_bytes": self.payload_bytes,
            "error": self.error,
            "attempt": self.attempt,
        }


class GearsQuoteSaver:
    """Drives the GEARS Save-as-draft flow and returns a structured outcome."""

    def __init__(self, page, logger=None):
        self._page = page
        self._log = logger or (lambda msg: print(f"[save] {msg}", flush=True))

    # ------------------------------------------------------------------
    async def save_as_draft(self, expect_quote_id: Optional[str] = None,
                            attempt: int = 1) -> SaveOutcome:
        """Run the full Save flow with network capture. Never raises for
        business outcomes — returns a SaveOutcome with a status taxonomy."""
        page = self._page
        out = SaveOutcome(attempt=attempt)
        captured: dict[str, Optional[dict[str, Any]]] = {"put_req": None, "put_resp": None}
        started = time.monotonic()

        # ---- 1. wait for + click "Save as draft" (the VISIBLE one; there is
        # also a hidden duplicate with class label-save). The Angular app may
        # still be LOADING right after navigation — poll up to 15s. ----
        clicked = False
        try:
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                for btn in await page.locator(f"button:has-text('{SAVE_BTN_TEXT}')").all():
                    if await btn.is_visible():
                        await btn.click()
                        clicked = True
                        break
                if clicked:
                    break
                await page.wait_for_timeout(1000)
        except Exception as e:
            out.status = "NETWORK_ERROR"
            out.error = f"save button click failed: {str(e)[:120]}"
            return out
        if not clicked:
            out.status = "NETWORK_ERROR"
            out.error = "no visible 'Save as draft' button"
            return out
        self._log("clicked Save as draft")

        # ---- 2. wait for confirmation dialog ----
        dialog_save = None
        deadline = time.monotonic() + DIALOG_PROBE_MS / 1000
        while time.monotonic() < deadline:
            for btn in await page.locator(".cdk-overlay-container button:has-text('Save')").all():
                try:
                    if await btn.is_visible() and (await btn.inner_text()).strip() == DIALOG_SAVE_TEXT:
                        dialog_save = btn
                        break
                except Exception:
                    pass
            if dialog_save:
                break
            await page.wait_for_timeout(500)
        if dialog_save is None:
            out.status = "DIALOG_TIMEOUT"
            out.error = "confirmation dialog did not appear within 8s"
            return out
        self._log("confirmation dialog appeared")

        # ---- 3+4. confirm dialog while capturing the PUT via expect_* ----
        # (page.on response callbacks are sync and can't await body(); use
        # expect_request/expect_response which we can await in this scope)
        put_seen = {"req": None, "resp": None}

        async def _do_confirm():
            await dialog_save.click()

        try:
            async with page.expect_response(
                lambda r: PUT_MARKER in r.url, timeout=PUT_WAIT_MS
            ) as resp_info:
                async with page.expect_request(
                    lambda r: r.method == "PUT" and PUT_MARKER in r.url,
                    timeout=PUT_WAIT_MS,
                ) as req_info:
                    await _do_confirm()
                put_seen["req"] = await req_info.value
            put_seen["resp"] = await resp_info.value
        except Exception as e:
            # expect_* timed out — check for session trap / late arrival
            pass
        self._log("clicked dialog Save")

        # ---- 5. wait a beat for late responses / navigation ----
        if put_seen["resp"] is None:
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline and put_seen["resp"] is None:
                await page.wait_for_timeout(500)

        # session-expiry trap check (forcelogout/login redirect)
        url = ""
        try:
            url = page.url
        except Exception:
            pass
        low_url = url.lower()
        if any(m in low_url for m in ("forcelogout", "userlogin", "login.html")):
            out.status = "SESSION_EXPIRED"
            out.error = f"redirected to login trap: {url[:100]}"
            return out

        # ---- 6. classify ----
        req = put_seen["req"]
        resp = put_seen["resp"]
        if resp is not None:
            try:
                body = (await resp.body()).decode("utf-8", "replace")
            except Exception:
                body = ""
        else:
            body = ""

        if resp is None:
            out.status = "PUT_FAILED"
            out.error = "no PUT request/response captured within timeout"
            return out

        out.http_status = resp.status
        out.payload_bytes = len(req.post_data) if req and req.post_data else 0
        out.quote_id = (req.url.rsplit("/", 1)[-1] if req else "") or out.quote_id

        if resp.status == 200 and body:
            try:
                obj = json.loads(body)
                out.quote_id = obj.get("id") or out.quote_id
                out.version = obj.get("version", -1)
                md = obj.get("metaData", {})
                out.doc_name = md.get("docName", "")
                bs = md.get("businessStatus") or {}
                os_ = md.get("operationStatus") or {}
                out.business_status = bs.get("code", "")
                out.operation_status = os_.get("code", "")
                out.status = "SAVED"
            except Exception as e:
                out.status = "PUT_FAILED"
                out.error = f"200 but unparseable body: {str(e)[:120]}"
        else:
            out.status = "PUT_FAILED"
            out.error = (f"PUT status={resp.status} body={body[:200]}"
                         if body else f"PUT status={resp.status} empty body")

        # ---- 7. wait for post-save navigation (best-effort, non-fatal) ----
        if out.ok:
            deadline = time.monotonic() + NAV_WAIT_MS / 1000
            while time.monotonic() < deadline and "dashboard" not in page.url:
                await page.wait_for_timeout(500)

        out.ts = time.time()
        self._log(f"outcome={out.status} doc={out.doc_name} ver={out.version} "
                  f"http={out.http_status} payload={out.payload_bytes}B "
                  f"elapsed={time.monotonic()-started:.1f}s")
        return out
