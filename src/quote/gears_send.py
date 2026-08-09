"""GEARS Motor (PMOT) Send application capability — verified flow 2026-08-09.

Real Send-application flow on the GEARS Angular app (agent emails the saved
quotation to the customer):

    (quote detail page, fully rendered)
    click hidden #send-application button   →  confirmation dialog appears
        "Please verify the details before sending ... Customer's email address
         / year of birth / last 4 of NRIC"  (fields pre-filled from quote)
    click dialog "Send"                     →  PUT (save) ×2
                                            →  POST .../quotations/PMOT/VPC/application
                                               body: {title: last4, email, message: YOB,
                                                      validDays: 30, quotationURL, password}
                                            →  200 {"result": true}
    success dialog: "The quote has been emailed to {email}."  → click Ok

The #send-application button only exists in the mobile summary section
(.as-summary-section--mobile, hidden on desktop via CSS) — a DOM click
(element.click()) still fires the Angular handler, so no viewport resize
is needed.

Usage:
    sender = GearsQuoteSender(page)
    outcome = await sender.send_application()
    if outcome.status == "SENT":
        print(outcome.email, outcome.http_status)

Failure taxonomy (structured, not "generic error"):
    SENT              application POST 200 + result:true + success dialog
    DIALOG_TIMEOUT    confirmation dialog never appeared after click
    SEND_FAILED       POST missing / non-200 / result != true
    SESSION_EXPIRED   page ended on a login/forcelogout trap
    NETWORK_ERROR     listener/parse failure
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Optional

SEND_BTN_ID = "send-application"
DIALOG_PROBE_MS = 10000      # wait for confirmation dialog after click
POST_WAIT_MS = 30000         # wait for the application POST
SUCCESS_PROBE_MS = 10000     # wait for the success dialog

# POST URL: https://store-my.greateasterngeneral.com/my/v1/ife/general/quotations/PMOT/VPC/application
POST_MARKER = "/quotations/PMOT/VPC/application"


@dataclass
class SendOutcome:
    """Structured result of one send-application attempt."""

    status: str = "PENDING"          # SENT | DIALOG_TIMEOUT | SEND_FAILED | SESSION_EXPIRED | NETWORK_ERROR
    email: str = ""
    quote_id: str = ""
    http_status: Optional[int] = None
    result: Optional[bool] = None
    post_payload_keys: list[str] = field(default_factory=list)
    dialog_fields: dict[str, str] = field(default_factory=dict)
    error: str = ""
    attempt: int = 0
    ts: float = field(default_factory=time.time)

    @property
    def ok(self) -> bool:
        return self.status == "SENT"

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "email": self.email,
            "quote_id": self.quote_id,
            "http_status": self.http_status,
            "result": self.result,
            "post_payload_keys": self.post_payload_keys,
            "dialog_fields": self.dialog_fields,
            "error": self.error,
            "attempt": self.attempt,
        }


class GearsQuoteSender:
    """Drives the GEARS Send-application flow and returns a structured outcome."""

    def __init__(self, page, logger=None):
        self._page = page
        self._log = logger or (lambda msg: print(f"[send] {msg}", flush=True))

    # ------------------------------------------------------------------
    async def send_application(self, expect_email: Optional[str] = None,
                               quote_url: Optional[str] = None,
                               attempt: int = 1) -> SendOutcome:
        """Run the full Send flow with network capture. Never raises for
        business outcomes — returns a SendOutcome with a status taxonomy.

        If `quote_url` is given and the current page is not the quote detail
        page (e.g. after a Save the app navigates to the dashboard), the
        sender navigates there itself first — the capability is
        self-contained, callers don't need to manage navigation.
        """
        page = self._page
        out = SendOutcome(attempt=attempt)
        started = time.monotonic()

        # ---- 0. self-navigate to the quote detail page if needed ----
        if quote_url:
            try:
                has_btn = await page.evaluate(
                    "() => !!document.getElementById('send-application')"
                )
            except Exception:
                has_btn = False
            if not has_btn:
                self._log(f"not on quote page — navigating to {quote_url[:70]}")
                try:
                    await page.goto(quote_url, wait_until="domcontentloaded",
                                    timeout=45000)
                except Exception as e:
                    out.status = "NETWORK_ERROR"
                    out.error = f"goto quote failed: {str(e)[:120]}"
                    return out

        # ---- 1. wait for the send button to exist (page render ~15-22s).
        # The button is CSS-hidden on desktop — we only need it in the DOM. ----
        btn_ok = False
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            try:
                btn_ok = await page.evaluate(
                    "() => !!document.getElementById('send-application')"
                )
            except Exception:
                btn_ok = False
            if btn_ok:
                break
            await page.wait_for_timeout(1500)
        if not btn_ok:
            out.status = "NETWORK_ERROR"
            out.error = "#send-application button not found within 30s"
            return out
        self._log("send-application button present in DOM")

        # ---- 2. DOM-click it (hidden on desktop; element.click() still
        # fires the Angular handler). ----
        try:
            await page.evaluate(
                """() => {
                    const b = document.getElementById('send-application');
                    if (b) b.click();
                }"""
            )
        except Exception as e:
            out.status = "NETWORK_ERROR"
            out.error = f"send button click failed: {str(e)[:120]}"
            return out
        self._log("clicked send-application")

        # ---- 3. wait for confirmation dialog, read its fields ----
        dlg = await self._wait_for_dialog()
        if dlg is None:
            out.status = "DIALOG_TIMEOUT"
            out.error = "send confirmation dialog did not appear"
            return out
        out.dialog_fields = dlg
        if expect_email and dlg.get("email"):
            out.email = dlg["email"]

        # ---- 4. click dialog Send while capturing the application POST ----
        post_seen = {"req": None, "resp": None, "body": ""}

        async def _do_send():
            await page.evaluate(
                """() => {
                    const btns = Array.from(document.querySelectorAll(
                        '.cdk-overlay-container button'));
                    const s = btns.find(b => b.innerText.trim() === 'Send');
                    if (s) s.click();
                }"""
            )

        try:
            async with page.expect_response(
                lambda r: POST_MARKER in r.url, timeout=POST_WAIT_MS
            ) as resp_info:
                async with page.expect_request(
                    lambda r: r.method == "POST" and POST_MARKER in r.url,
                    timeout=POST_WAIT_MS,
                ) as req_info:
                    await _do_send()
                post_seen["req"] = await req_info.value
            post_seen["resp"] = await resp_info.value
        except Exception:
            # expect_* timed out — classify below
            pass
        self._log("clicked dialog Send")

        # ---- 5. late-arrival grace + session trap check ----
        if post_seen["resp"] is None:
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline and post_seen["resp"] is None:
                await page.wait_for_timeout(500)

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
        req = post_seen["req"]
        resp = post_seen["resp"]
        if resp is not None:
            try:
                body = (await resp.body()).decode("utf-8", "replace")
            except Exception:
                body = ""
        else:
            body = ""

        if req and req.post_data:
            out.post_payload_keys = list(json.loads(req.post_data).keys()) \
                if req.post_data.startswith("{") else []
        if resp is None:
            out.status = "SEND_FAILED"
            out.error = "no application POST captured within timeout"
            return out

        out.http_status = resp.status
        if resp.status == 200 and body:
            try:
                obj = json.loads(body)
                out.result = bool(obj.get("result"))
            except Exception:
                out.result = None
            if out.result:
                # confirm via success dialog
                ok_dialog = await self._wait_for_success_dialog()
                if ok_dialog is not None:
                    out.email = out.email or ok_dialog.get("email", "")
                    out.status = "SENT"
                else:
                    out.status = "SEND_FAILED"
                    out.error = "POST ok but no success dialog within 10s"
            else:
                out.status = "SEND_FAILED"
                out.error = f"application POST result=false body={body[:200]}"
        else:
            out.status = "SEND_FAILED"
            out.error = (f"application POST status={resp.status} body={body[:200]}"
                         if body else f"application POST status={resp.status} empty body")

        out.ts = time.time()
        self._log(f"outcome={out.status} email={out.email} http={out.http_status} "
                  f"result={out.result} elapsed={time.monotonic()-started:.1f}s")
        return out

    # ------------------------------------------------------------------
    async def _wait_for_dialog(self) -> Optional[dict[str, str]]:
        """Wait for the send confirmation dialog; return its field values."""
        page = self._page
        deadline = time.monotonic() + DIALOG_PROBE_MS / 1000
        while time.monotonic() < deadline:
            try:
                info = await page.evaluate(
                    """() => {
                        const o = document.querySelector('.cdk-overlay-container');
                        if (!o) return null;
                        const txt = o.innerText || '';
                        if (!/Send application/.test(txt)) return null;
                        // fields are plain-text divs (.value-text), not inputs:
                        // [email, year of birth, last 4 of NRIC]
                        const vals = Array.from(
                            o.querySelectorAll('.value-text')
                        ).map(e => (e.textContent || '').trim());
                        return {
                            email: vals[0] || '',
                            yob: vals[1] || '',
                            last4: vals[2] || '',
                        };
                    }"""
                )
                if info is not None and (info["email"] or info["yob"] or info["last4"]):
                    return info
            except Exception:
                pass
            await page.wait_for_timeout(500)
        return None

    async def _wait_for_success_dialog(self) -> Optional[dict[str, str]]:
        """Wait for 'The quote has been emailed to ...' dialog, click Ok."""
        page = self._page
        deadline = time.monotonic() + SUCCESS_PROBE_MS / 1000
        while time.monotonic() < deadline:
            try:
                info = await page.evaluate(
                    """() => {
                        const o = document.querySelector('.cdk-overlay-container');
                        if (!o) return null;
                        const txt = o.innerText || '';
                        if (!/emailed to/.test(txt)) return null;
                        const m = txt.match(/emailed to\\s*\\n?\\s*([^\\n]+)/);
                        return { email: m ? m[1].trim() : '' };
                    }"""
                )
                if info is not None:
                    # click Ok to close
                    await page.evaluate(
                        """() => {
                            const btns = Array.from(document.querySelectorAll(
                                '.cdk-overlay-container button'));
                            const ok = btns.find(b => b.innerText.trim() === 'Ok');
                            if (ok) ok.click();
                        }"""
                    )
                    return info
            except Exception:
                pass
            await page.wait_for_timeout(500)
        return None
