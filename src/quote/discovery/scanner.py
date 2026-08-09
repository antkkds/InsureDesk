"""InsureDesk — Form Scanner.

Scans web pages to discover form fields, their types,
options, validation rules, and dependencies.

Usage:
    scanner = FormScanner(engine)
    schema = await scanner.scan_page("https://...")
    print(schema.to_profile_yaml())
"""

from __future__ import annotations

import json
import time
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime

from src.browser.driver import BrowserEngine
from src.quote.discovery.models import (
    FormField, FormPage, FormSchema, FieldOption, FieldDependency,
)


# JS snippet that scans the current page for form fields
SCAN_FORM_JS = """
(() => {
    const fields = [];
    const formElements = document.querySelectorAll(
        'input, select, textarea, button, [role="button"], ' +
        'a.btn, a[class*="button"], [contenteditable="true"]'
    );

    for (const el of formElements) {
        const tag = el.tagName.toLowerCase();
        const type = (el.getAttribute('type') || 'text').toLowerCase();
        const name = el.getAttribute('name') || '';
        const id = el.getAttribute('id') || '';
        const placeholder = el.getAttribute('placeholder') || '';

        // Skip hidden, submit buttons (capture separately)
        if (type === 'hidden') continue;
        if (tag === 'button' || (tag === 'input' && type === 'submit') || (tag === 'input' && type === 'image')) {
            // Capture as action, not field
            continue;
        }

        // Find label
        let label = '';
        const labelEl = document.querySelector('label[for="' + id + '"]');
        if (labelEl) label = (labelEl.textContent || '').trim();
        if (!label) {
            const parent = el.closest('label');
            if (parent) label = (parent.textContent || '').trim();
        }
        if (!label) {
            // Try aria-label
            label = el.getAttribute('aria-label') || '';
        }
        if (!label && placeholder) label = placeholder;

        // Get options for select
        let options = [];
        if (tag === 'select') {
            for (const opt of el.querySelectorAll('option')) {
                options.push({
                    value: opt.value,
                    label: (opt.textContent || '').trim(),
                    selected: opt.selected,
                });
            }
        }

        // Required detection
        const required = el.hasAttribute('required') ||
            (el.getAttribute('aria-required') === 'true') ||
            (el.classList.contains('required')) ||
            false;

        // Validation attributes
        const minLength = el.getAttribute('minlength');
        const maxLength = el.getAttribute('maxlength');
        const min = el.getAttribute('min');
        const max = el.getAttribute('max');
        const pattern = el.getAttribute('pattern') || '';

        // Generate candidate selectors
        const candidates = {};

        // Try ID
        if (id) {
            const sel = '#' + CSS.escape(id);
            const count = document.querySelectorAll(sel).length;
            candidates[sel] = count === 1 ? 95 : 80;
        }

        // data-testid
        const testId = el.getAttribute('data-testid');
        if (testId) candidates['[data-testid="' + testId + '"]'] = 92;

        // name
        if (name) {
            const sel = '[name="' + name + '"]';
            const count = document.querySelectorAll(sel).length;
            candidates[sel] = count === 1 ? 82 : 70;
        }

        // aria-label
        if (label && !candidates['[aria-label="' + label + '"]']) {
            candidates['[aria-label="' + label + '"]'] = 80;
        }

        // placeholder
        if (placeholder) candidates['[placeholder="' + placeholder + '"]'] = 75;

        // Class-based (skip dynamic classes)
        const classes = (el.className || '').split(/\\s+/).filter(Boolean);
        const stableClasses = classes.filter(c => !/^[a-z]+-[a-f0-9]{4,}/.test(c) && c !== '');
        if (stableClasses.length > 0) {
            const sel = tag + '.' + stableClasses.join('.');
            candidates[sel] = 55;
        }

        // Pick best selector
        const bestSelector = Object.keys(candidates)
            .sort((a, b) => candidates[b] - candidates[a])[0] || tag;

        fields.push({
            key: name || id || (label ? label.toLowerCase().replace(/[^a-z0-9]+/g, '_') : '') || ('field_' + fields.length),
            tag: tag,
            type: type,
            name: name,
            id: id,
            label: label,
            placeholder: placeholder,
            selector: bestSelector,
            candidates: candidates,
            required: required,
            minLength: minLength || null,
            maxLength: maxLength || null,
            min: min || null,
            max: max || null,
            pattern: pattern || null,
            options: options,
            multiple: el.hasAttribute('multiple'),
        });
    }

    // Detect buttons/actions separately
    const actions = [];
    for (const el of document.querySelectorAll(
        'button, input[type="submit"], input[type="button"], ' +
        'a[class*="btn"], [role="button"]'
    )) {
        if (el.offsetParent === null) continue; // hidden
        const text = (el.textContent || el.value || '').trim().substring(0, 50);
        if (!text) continue;
        actions.push({
            key: text.toLowerCase().replace(/[^a-z0-9]+/g, '_'),
            text: text,
            selector: (el.id ? '#' + CSS.escape(el.id) : '') ||
                      '[value="' + (el.value || '') + '"]' ||
                      'button:has-text("' + text + '")',
            type: el.tagName.toLowerCase(),
        });
    }

    return {
        fields: fields,
        actions: actions,
        url: window.location.href,
        title: document.title,
    };
})();
"""


class FormScanner:
    """Scans web pages to discover form fields and structure.

    Connects to a browser, scans the current page, and returns
    a structured FormSchema with all discovered fields.

    Usage:
        scanner = FormScanner(engine)
        schema = await scanner.scan_current_page("proposer", "IFE")
        print(schema.to_profile_yaml())
    """

    def __init__(self, engine: BrowserEngine):
        self._engine = engine
        self._scan_history: List[FormSchema] = []

    @property
    def scan_history(self) -> List[FormSchema]:
        return list(self._scan_history)

    async def scan_current_page(
        self,
        page_name: str = "form",
        portal: str = "",
        channel: str = "",
    ) -> Optional[FormSchema]:
        """Scan the current browser page for form fields.

        Args:
            page_name: Name for this page (e.g. "proposer", "risk", "coverage")
            portal: Portal name (e.g. "great_eastern")
            channel: Quote channel (e.g. "IFE", "EQ")

        Returns:
            FormSchema with discovered fields, or None if scan fails.
        """
        if not self._engine:
            return None

        try:
            result = await self._engine.evaluate(SCAN_FORM_JS)
        except Exception:
            return None

        if not result or not isinstance(result, dict):
            return None

        fields_data = result.get("fields", [])
        actions_data = result.get("actions", [])
        url = result.get("url", "")
        title = result.get("title", "")

        # Build FormFields
        fields = []
        for i, fd in enumerate(fields_data):
            candidates = fd.get("candidates", {})
            # Build options
            options = []
            for opt in fd.get("options", []):
                options.append(FieldOption(
                    value=opt.get("value", ""),
                    label=opt.get("label", ""),
                    selected=opt.get("selected", False),
                ))

            field = FormField(
                key=fd.get("key", f"field_{i}"),
                label=fd.get("label", ""),
                placeholder=fd.get("placeholder", ""),
                selector=fd.get("selector", ""),
                best_selector=fd.get("selector", ""),
                candidate_selectors=candidates,
                page_url=url,
                field_type=fd.get("type", "text"),
                tag=fd.get("tag", "input"),
                required=bool(fd.get("required", False)),
                min_length=self._safe_int(fd.get("minLength")),
                max_length=self._safe_int(fd.get("maxLength")),
                min_value=self._safe_float(fd.get("min")),
                max_value=self._safe_float(fd.get("max")),
                pattern=fd.get("pattern", "") or "",
                options=options,
                multiple=bool(fd.get("multiple", False)),
                order=i,
            )
            fields.append(field)

        # Build actions
        actions = []
        for a in actions_data:
            actions.append({
                "key": a.get("key", ""),
                "selector": a.get("selector", ""),
                "type": a.get("type", "button"),
            })

        # Build page
        page = FormPage(
            name=page_name,
            url_pattern=url,
            title_pattern=title,
            fields=fields,
            actions=actions,
        )

        # Build schema
        schema = FormSchema(
            portal=portal,
            quote_channel=channel,
            version="1.0",
            captured_at=datetime.utcnow().isoformat(),
            pages=[page],
        )

        self._scan_history.append(schema)
        return schema

    async def scan_multi_page(
        self,
        pages_config: List[Tuple[str, str]],
        portal: str = "",
        channel: str = "",
    ) -> Optional[FormSchema]:
        """Scan multiple pages sequentially (for multi-step wizards).

        Args:
            pages_config: List of (page_name, url) tuples
            portal: Portal name
            channel: Quote channel

        Returns:
            Combined FormSchema with all pages.
        """
        all_pages = []
        for page_name, url in pages_config:
            if url:
                try:
                    await self._engine.navigate(url)
                    import asyncio
                    await asyncio.sleep(2)
                except Exception:
                    pass

            schema = await self.scan_current_page(
                page_name=page_name,
                portal=portal,
                channel=channel,
            )
            if schema and schema.pages:
                all_pages.extend(schema.pages)

        if not all_pages:
            return None

        return FormSchema(
            portal=portal,
            quote_channel=channel,
            version="1.0",
            captured_at=datetime.utcnow().isoformat(),
            pages=all_pages,
        )

    async def detect_dependencies(
        self,
        trigger_selector: str,
        trigger_value: str,
        wait_seconds: float = 2.0,
    ) -> List[FieldDependency]:
        """Detect field dependencies by setting a value and watching for changes.

        Sets a field to a specific value, waits, then compares
        the visible fields before and after to detect dependencies.

        Args:
            trigger_selector: Selector for the trigger field
            trigger_value: Value to set
            wait_seconds: Time to wait for dependent fields to appear

        Returns:
            List of FieldDependency objects.
        """
        if not self._engine:
            return []

        # Scan before
        before = await self._get_visible_fields()

        # Set value
        try:
            await self._engine.fill(trigger_selector, trigger_value)
            import asyncio
            await asyncio.sleep(wait_seconds)
        except Exception:
            return []

        # Scan after
        after = await self._get_visible_fields()

        # Diff
        before_set = set(before)
        after_set = set(after)
        new_fields = after_set - before_set
        hidden_fields = before_set - after_set

        dependencies = []
        if new_fields:
            dependencies.append(FieldDependency(
                field=trigger_selector,
                equals=trigger_value,
                show_fields=list(new_fields),
                hide_fields=list(hidden_fields),
            ))

        return dependencies

    async def _get_visible_fields(self) -> List[str]:
        """Get list of visible field selectors on the current page."""
        try:
            js = """
                Array.from(document.querySelectorAll(
                    'input, select, textarea'
                )).filter(el => {
                    const rect = el.getBoundingClientRect();
                    return rect.width > 0 && rect.height > 0 &&
                           el.offsetParent !== null;
                }).map(el => {
                    return el.getAttribute('name') ||
                           el.getAttribute('id') ||
                           el.tagName.toLowerCase();
                });
            """
            result = await self._engine.evaluate(js)
            return result if isinstance(result, list) else []
        except Exception:
            return []

    def merge_schemas(self, schemas: List[FormSchema]) -> Optional[FormSchema]:
        """Merge multiple schemas (from different pages) into one."""
        if not schemas:
            return None

        all_pages = []
        for s in schemas:
            all_pages.extend(s.pages)

        return FormSchema(
            portal=schemas[0].portal,
            quote_channel=schemas[0].quote_channel,
            version="1.0",
            captured_at=datetime.utcnow().isoformat(),
            pages=all_pages,
        )

    @staticmethod
    def _safe_int(val) -> Optional[int]:
        if val is None:
            return None
        try:
            return int(val)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _safe_float(val) -> Optional[float]:
        if val is None:
            return None
        try:
            return float(val)
        except (ValueError, TypeError):
            return None
