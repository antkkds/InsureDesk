"""InsureDesk — Browser Inspector.

Dev tool for capturing and scoring CSS selectors on insurance portals.
Works in two modes:
1. Connected mode — attach to a running BrowserEngine, navigate, capture live
2. Offline mode — load existing page HTML/JS for selector analysis

Selector scoring (Playwright-first philosophy):
- Prefers #id, [data-testid], [name], then class, then positional
- Scores 0-100 based on specificity, uniqueness, stability, readability
"""

from __future__ import annotations

import os
import re
import json
import yaml
import asyncio
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, field, asdict


# ══════════════════════════════════════════════════════════════════
# Data Models
# ══════════════════════════════════════════════════════════════════

@dataclass
class CapturedElement:
    """An element captured during inspection.

    Stores all information needed to generate and score selectors,
    and to export as YAML mapping entries.
    """
    tag: str = ""
    text: str = ""
    attributes: Dict[str, str] = field(default_factory=dict)
    selector: str = ""
    input_type: str = ""
    page_url: str = ""
    placeholder: str = ""
    label: str = ""
    role: str = ""
    candidate_selectors: Dict[str, int] = field(default_factory=dict)

    @property
    def best_selector(self) -> str:
        """Return the highest-scored selector."""
        if not self.candidate_selectors:
            return self.selector
        return max(self.candidate_selectors, key=self.candidate_selectors.get)

    def to_dict(self) -> dict:
        """Export as portable dict for YAML serialization."""
        return {
            "field": self.text or self.label or self.placeholder or self.tag,
            "tag": self.tag,
            "selector": self.best_selector,
            "input_type": self.input_type or None,
            "label": self.label or None,
            "placeholder": self.placeholder or None,
            "role": self.role or None,
        }

    def score_summary(self) -> str:
        """Human-readable score summary."""
        lines = [f"  Tag: <{self.tag}>  Type: {self.input_type or '-'}"]
        if self.label:
            lines.append(f"  Label: {self.label}")
        if self.text:
            lines.append(f"  Text: {self.text[:60]}")
        if self.placeholder:
            lines.append(f"  Placeholder: {self.placeholder}")
        lines.append(f"  Best selector: {self.best_selector}")
        lines.append("  Candidates (scored):")
        for sel, score in sorted(
            self.candidate_selectors.items(),
            key=lambda x: -x[1],
        )[:5]:
            bar = "█" * (score // 10) + "░" * (10 - score // 10)
            lines.append(f"    {bar} {score:3d}  {sel}")
        return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════
# Selector Generator & Scorer
# ══════════════════════════════════════════════════════════════════

_SELECTOR_WEIGHTS = {
    "id": 95,
    "data-testid": 92,
    "data-test": 90,
    "data-qa": 88,
    "name": 82,
    "aria-label": 80,
    "href": 75,
    "title": 70,
    "class": 55,
    "tag": 30,
    "nth": 25,
    "text": 60,  # text-based (e.g. :text-is() in Playwright)
    "placeholder": 75,
    "role": 70,
}

_UNIQUE_BONUS = 10
_MULTI_MATCH_PENALTY = 20
_DYNAMIC_CLASS_PATTERN = re.compile(r'^[a-z]+-[a-f0-9]{4,}|^css-[a-z0-9]+|[a-z]{2,}[A-Z][a-z]+')
_TOO_GENERIC_TAGS = {"div", "span", "td", "tr", "li", "a", "p", "section", "article"}


def _is_dynamic_class(cls: str) -> bool:
    """Detect CSS module / framework-generated class names."""
    return bool(_DYNAMIC_CLASS_PATTERN.search(cls))


def _score_id_based(sel: str, element_info: dict) -> int:
    """Score an ID-based selector."""
    score = _SELECTOR_WEIGHTS["id"]
    el_id = sel.lstrip("#")
    if _is_dynamic_class(el_id):
        score -= 30
    if len(el_id) < 3:
        score -= 20  # too short, likely auto-generated
    if len(el_id) > 60:
        score -= 15  # overly long ID, likely auto-generated
    return score


def _score_attribute_based(sel: str, attr: str, element_info: dict) -> int:
    """Score an attribute-based selector."""
    base = _SELECTOR_WEIGHTS.get(attr, 70)
    score = base

    if attr == "data-testid" or attr == "data-test" or attr == "data-qa":
        score = _SELECTOR_WEIGHTS[attr]  # 88-92

    elif attr == "name":
        score = _SELECTOR_WEIGHTS["name"]
        val = re.search(r'\[name="([^"]+)"\]', sel)
        if val and _is_dynamic_class(val.group(1)):
            score -= 20

    elif attr == "class":
        score = _SELECTOR_WEIGHTS["class"]
        classes = element_info.get("classes", [])
        dynamic_count = sum(1 for c in classes if _is_dynamic_class(c))
        if dynamic_count > 0:
            # Penalize dynamic classes; prefer stable ones
            stable_ratio = (len(classes) - dynamic_count) / max(len(classes), 1)
            score = int(score * stable_ratio)

    elif attr == "href":
        score = _SELECTOR_WEIGHTS["href"]
        val = re.search(r'\[href="([^"]+)"\]', sel)
        if val and (val.group(1).startswith("javascript:") or val.group(1) == "#"):
            score -= 30

    return score


def _score_tag_based(sel: str, tag: str, element_info: dict) -> int:
    """Score a tag-based selector."""
    score = _SELECTOR_WEIGHTS["tag"]
    if tag in _TOO_GENERIC_TAGS:
        score -= 10
    if "nth" in sel or ":nth" in sel:
        score = _SELECTOR_WEIGHTS["nth"]
    return score


def _score_text_based(sel: str, element_info: dict) -> int:
    """Score a text-based selector (Playwright :text-is() etc.)."""
    score = _SELECTOR_WEIGHTS["text"]
    text = element_info.get("text", "")
    if len(text) > 100:
        score -= 10  # too long, fragile
    if not text.strip():
        score -= 30
    return score


def score_selector(sel: str, element_info: dict) -> int:
    """Score a single CSS/XPath/Playwright selector 0-100.

    Args:
        sel: The selector string (CSS, :text(), etc.)
        element_info: Dict with 'tag', 'text', 'attributes', 'classes'

    Returns:
        Score 0-100 (higher = better selector for automation)
    """
    if not sel:
        return 0

    score = 50  # default middle

    # ── Detect selector type ──
    if sel.startswith("#"):
        score = _score_id_based(sel, element_info)
    elif sel.startswith("["):
        attr_match = re.search(r'\[([\w-]+)=', sel)
        attr = attr_match.group(1) if attr_match else "attribute"
        score = _score_attribute_based(sel, attr, element_info)
    elif sel.startswith("."):
        score = _SELECTOR_WEIGHTS["class"]
        classes = element_info.get("classes", [])
        dynamic_count = sum(1 for c in classes if _is_dynamic_class(c))
        if dynamic_count > 0:
            stable_ratio = (len(classes) - dynamic_count) / max(len(classes), 1)
            score = int(_SELECTOR_WEIGHTS["class"] * stable_ratio)
    elif sel.startswith(":"):
        # Playwright pseudo-selectors
        if "text" in sel or "text-is" in sel:
            score = _score_text_based(sel, element_info)
        elif "has" in sel:
            score = 70  # :has() is powerful but slower
    elif sel.startswith("//") or sel.startswith(".//"):
        score = 35  # XPath — fragile, hard to read
    else:
        # Tag-based or combined
        score = _score_tag_based(sel, element_info.get("tag", ""), element_info)

    # ── Uniqueness bonus/penalty ──
    match_count = element_info.get("match_count", 1)
    if match_count == 1:
        score += _UNIQUE_BONUS
    elif match_count > 1:
        score -= min(_MULTI_MATCH_PENALTY, (match_count - 1) * 8)

    # ── Readability penalty ──
    if len(sel) > 120:
        score -= 10
    if re.search(r'[\\\'\"]', sel):
        score -= 5

    return max(0, min(100, score))


def generate_candidate_selectors(tag: str, attributes: Dict[str, str], text: str) -> Dict[str, int]:
    """Generate all possible selectors for an element and score them.

    Playwright-first order: id > data-testid > name > aria-label > class > tag
    """
    candidates = {}

    # ID
    el_id = attributes.get("id", "")
    if el_id:
        sel = f"#{el_id}"
        element_info = {"tag": tag, "text": text, "attributes": attributes, "classes": [], "match_count": 1}
        candidates[sel] = _score_id_based(sel, element_info)

    # data-testid and similar
    for attr in ["data-testid", "data-test", "data-qa"]:
        val = attributes.get(attr, "")
        if val:
            sel = f'[{attr}="{val}"]'
            candidates[sel] = _SELECTOR_WEIGHTS[attr]

    # name
    name_val = attributes.get("name", "")
    if name_val:
        sel = f'[name="{name_val}"]'
        candidates[sel] = _SELECTOR_WEIGHTS["name"]

    # aria-label
    aria = attributes.get("aria-label", "")
    if aria and len(aria) > 1:
        sel = f'[aria-label="{aria}"]'
        candidates[sel] = _SELECTOR_WEIGHTS["aria-label"]

    # placeholder
    placeholder = attributes.get("placeholder", "")
    if placeholder and len(placeholder) > 1:
        sel = f'[placeholder="{placeholder}"]'
        candidates[sel] = _SELECTOR_WEIGHTS["placeholder"]

    # role
    role = attributes.get("role", "")
    if role:
        sel = f'[role="{role}"]'
        candidates[sel] = _SELECTOR_WEIGHTS["role"]

    # title
    title = attributes.get("title", "")
    if title:
        sel = f'[title="{title}"]'
        candidates[sel] = _SELECTOR_WEIGHTS["title"]

    # type
    input_type = attributes.get("type", "")
    # Only use type qualifier if combined with something else
    if input_type and name_val:
        sel = f'[name="{name_val}"][type="{input_type}"]'
        candidates[sel] = _SELECTOR_WEIGHTS["name"] + 2

    # href
    href = attributes.get("href", "")
    if href and not href.startswith("javascript:") and href != "#":
        sel = f'[href="{href}"]'
        candidates[sel] = _SELECTOR_WEIGHTS["href"]

    # Class-based
    classes = [c for c in attributes.get("class", "").split() if c]
    stable_classes = [c for c in classes if not _is_dynamic_class(c)]
    if stable_classes:
        sel = "." + ".".join(stable_classes)
        element_info = {"tag": tag, "text": text, "attributes": attributes, "classes": classes, "match_count": 1}
        candidates[sel] = _score_attribute_based(sel, "class", element_info)

    # Text-based (Playwright :text-is())
    clean_text = text.strip()[:80] if text else ""
    if clean_text and len(clean_text) > 1 and len(clean_text) < 100:
        sel = f':text-is("{clean_text}")'
        candidates[sel] = _SELECTOR_WEIGHTS["text"]

    # Tag + class combo
    if stable_classes:
        sel = tag + "." + ".".join(stable_classes)
        candidates[sel] = _SELECTOR_WEIGHTS["class"] + 5

    return dict(sorted(candidates.items(), key=lambda x: -x[1]))


# ══════════════════════════════════════════════════════════════════
# Browser Inspector
# ══════════════════════════════════════════════════════════════════

class BrowserInspector:
    """Interactive browser inspector for capturing and scoring selectors.

    Can operate in two modes:
    - Connected: attach to a running BrowserEngine
    - Offline: analyze from JS-injected element info

    Usage:
        insp = BrowserInspector()
        await insp.connect(engine)  # or insp.inject_element_info(data)
        await insp.capture("#username")  # capture by selector
        insp.captured  # list of CapturedElement
        await insp.interactive()  # REPL mode
    """

    def __init__(self):
        self.captured: List[CapturedElement] = []
        self.enabled: bool = False
        self._engine = None
        self._current_url: str = ""
        self._current_title: str = ""

    async def connect(self, engine) -> bool:
        """Connect to a running BrowserEngine."""
        self._engine = engine
        try:
            info = await engine.get_page_info()
            self._current_url = info.url
            self._current_title = info.title
            self.enabled = True
            return True
        except Exception:
            self._engine = None
            self.enabled = False
            return False

    async def disconnect(self):
        """Disconnect from browser without stopping it."""
        self._engine = None
        self.enabled = False

    async def refresh_page_info(self):
        """Refresh current page URL and title."""
        if self._engine:
            try:
                info = await self._engine.get_page_info()
                self._current_url = info.url
                self._current_title = info.title
            except Exception:
                pass

    async def navigate(self, url: str) -> bool:
        """Navigate and refresh page info."""
        if not self._engine:
            return False
        ok = await self._engine.navigate(url)
        if ok:
            await self.refresh_page_info()
        return ok

    async def capture(self, selector: str) -> Optional[CapturedElement]:
        """Capture an element by selector.

        Extracts tag, text, attributes, input type, and generates
        scored candidate selectors.
        """
        if not self._engine:
            return None

        try:
            # Get element details via JS
            js = f"""
            (() => {{
                try {{
                    const el = document.querySelector({json.dumps(selector)});
                    if (!el) return null;

                    const tag = el.tagName.toLowerCase();
                    const text = (el.textContent || '').trim().substring(0, 200);
                    const attrs = {{}};
                    for (const a of el.attributes) {{
                        if (a.name !== 'style') attrs[a.name] = a.value;
                    }}
                    const cls = el.className;
                    const type = el.getAttribute('type') || '';
                    const placeholder = el.getAttribute('placeholder') || '';
                    const label_text = (() => {{
                        if (el.getAttribute('aria-label')) return el.getAttribute('aria-label');
                        const id = el.getAttribute('id');
                        if (id) {{
                            const lbl = document.querySelector('label[for="{id}"]');
                            if (lbl) return (lbl.textContent || '').trim();
                        }}
                        // Check parent label
                        const parent = el.closest('label');
                        if (parent) return (parent.textContent || '').trim();
                        return '';
                    }})();
                    const role = el.getAttribute('role') || '';

                    // Find ancestor text for context
                    const ancestor_text = (() => {{
                        const ancestors = el.closest('th,td,.form-group,.field,.row,.control-group');
                        if (ancestors) return (ancestors.textContent || '').substring(0, 100).trim();
                        return '';
                    }})();

                    // Count matches for uniqueness
                    let matchCount = 1;
                    try {{
                        const testSel = {json.dumps(selector)};
                        matchCount = document.querySelectorAll(testSel).length;
                    }} catch(e) {{}}

                    return {{
                        tag, text, attrs,
                        classes: cls ? cls.split(/\\s+/).filter(Boolean) : [],
                        inputType: type,
                        placeholder,
                        label: label_text,
                        role,
                        matchCount,
                        ancestorText: ancestor_text,
                    }};
                }} catch(e) {{ return null; }}
            }})()
            """
            result = await self._engine.evaluate(js)
            if not result:
                return None

            element_info = result

            # Generate and score candidates
            candidates = generate_candidate_selectors(
                element_info["tag"],
                element_info["attrs"],
                element_info.get("label") or element_info.get("text", ""),
            )

            # Re-score with actual match counts
            if element_info["matchCount"] > 1:
                for sel in candidates:
                    match_js = f"document.querySelectorAll({json.dumps(sel)}).length"
                    try:
                        mc = await self._engine.evaluate(match_js)
                        if isinstance(mc, (int, float)):
                            candidates[sel] = max(0, candidates[sel] - (int(mc) - 1) * 8)
                    except Exception:
                        pass

            # Build CapturedElement
            el = CapturedElement(
                tag=element_info["tag"],
                text=element_info.get("label") or element_info.get("ancestorText") or element_info.get("text", ""),
                attributes=element_info["attrs"],
                selector=selector,
                input_type=element_info.get("inputType", ""),
                page_url=self._current_url,
                placeholder=element_info.get("placeholder", ""),
                label=element_info.get("label", ""),
                role=element_info.get("role", ""),
                candidate_selectors=candidates,
            )
            self.captured.append(el)
            return el

        except Exception as e:
            return None

    async def highlight(self, selector: str) -> bool:
        """Highlight an element on the page using a colored border."""
        if not self._engine:
            return False

        # Clear previous highlights first
        await self._engine.evaluate(
            "document.querySelectorAll('.insuredesk-inspector-highlight').forEach(el => {"
            "  el.style.outline = el.dataset.insuredeskOrig || '';"
            "  el.classList.remove('insuredesk-inspector-highlight');"
            "  delete el.dataset.insuredeskOrig;"
            "})"
        )

        js = f"""
        (() => {{
            const el = document.querySelector({json.dumps(selector)});
            if (!el) return false;
            el.classList.add('insuredesk-inspector-highlight');
            el.dataset.insuredeskOrig = el.style.outline || '';
            el.style.outline = '3px solid #ff4444';
            el.style.outlineOffset = '2px';
            el.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
            return true;
        }})()
        """
        return bool(await self._engine.evaluate(js))

    async def evaluate_selector(self, selector: str) -> Dict[str, Any]:
        """Evaluate and score a single selector.

        Returns dict with match count, element info, and score.
        """
        if not self._engine:
            return {"error": "Not connected to browser"}

        js = f"""
        (() => {{
            try {{
                const els = document.querySelectorAll({json.dumps(selector)});
                if (els.length === 0) return {{ matches: 0 }};
                const el = els[0];
                const tag = el.tagName.toLowerCase();
                const text = (el.textContent || '').trim().substring(0, 200);
                const attrs = {{}};
                for (const a of el.attributes) {{
                    if (a.name !== 'style') attrs[a.name] = a.value;
                }}
                const cls = el.className;
                return {{
                    matches: els.length,
                    tag,
                    text,
                    attrs,
                    classes: cls ? cls.split(/\\s+/).filter(Boolean) : [],
                    html: el.outerHTML.substring(0, 500),
                }};
            }} catch(e) {{
                return {{ error: String(e) }};
            }}
        }})()
        """
        result = await self._engine.evaluate(js)
        if isinstance(result, dict) and result.get("matches", 0) > 0:
            # Map keys for scorer
            element_info = {
                "tag": result.get("tag", ""),
                "text": result.get("text", ""),
                "attributes": result.get("attrs", {}),
                "classes": result.get("classes", []),
                "match_count": result.get("matches", 1),
            }
            score = score_selector(selector, element_info)
            result["score"] = score
        return result

    def generate_mapping(self) -> dict:
        """Export captured elements as a YAML-ready portal mapping."""
        selectors = {}
        for el in self.captured:
            key = el.text.lower().replace(" ", "_").replace("/", "_") or f"field_{len(selectors)}"
            selectors[key] = el.to_dict()

        return {
            "portal": {
                "name": f"Inspected Portal",
                "base_url": self._current_url,
                "adapter": "inspected",
            },
            "selectors": selectors,
        }

    async def interactive(self, headless: bool = True):
        """Run interactive REPL mode.

        Commands:
          open <url>       — Navigate to URL
          cap [sel]        — Capture element by selector
          hi <sel>         — Highlight element
          eval <sel>       — Evaluate & score selector
          list              — Show captured elements
          show <n>          — Show details of captured element N
          export            — Export mapping as YAML
          url               — Show current URL
          clear             — Clear captured elements
          help              — Show this help
          quit/exit         — Exit REPL
        """
        if not self._engine:
            print("! Not connected to browser engine")
            return

        # Inject highlight style
        await self._engine.evaluate(
            "const s = document.createElement('style');"
            "s.id = 'insuredesk-inspector-styles';"
            "s.textContent = '.insuredesk-inspector-highlight { outline: 3px solid #ff4444 !important; outline-offset: 2px !important; }';"
            "document.head.appendChild(s);"
        )

        await self.refresh_page_info()
        print(f"\n  Browser Inspector  |  {self._current_title}")
        print(f"  {'=' * 50}")
        print(f"  URL: {self._current_url}")
        print(f"  Type 'help' for commands\n")

        import readline  # enable arrow key navigation

        while True:
            try:
                line = input("  insp> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break

            if not line:
                continue

            cmd, *args = line.split(maxsplit=1)
            cmd = cmd.lower()

            if cmd in ("quit", "exit", "q"):
                break

            elif cmd == "help":
                print("""  Commands:
    open <url>       — Navigate to URL
    cap [sel]        — Capture element by selector
    hi <sel>         — Highlight element on page
    eval <sel>       — Evaluate & score a selector
    list              — List captured elements (index: label)
    show <n>          — Show full details + scored candidates
    export            — Export captured mapping as YAML
    url               — Show current page URL
    clear             — Clear all captured elements
    help              — This help
    quit / exit       — Exit""")

            elif cmd == "url":
                await self.refresh_page_info()
                print(f"  Title: {self._current_title}")
                print(f"  URL:   {self._current_url}")

            elif cmd == "open" and args:
                url = args[0]
                if not url.startswith("http"):
                    url = "https://" + url
                print(f"  → Navigating to {url}...")
                ok = await self.navigate(url)
                print(f"  {'✓' if ok else '✗'} {'Done' if ok else 'Failed'}")
                if ok:
                    print(f"  Title: {self._current_title}")

            elif cmd in ("cap", "capture") and args:
                selector = args[0]
                print(f"  → Capturing {selector}...")
                el = await self.capture(selector)
                if el:
                    print(f"  ✓ Captured <{el.tag}>")
                    if el.label:
                        print(f"    Label: {el.label}")
                    if el.placeholder:
                        print(f"    Placeholder: {el.placeholder}")
                    if el.input_type:
                        print(f"    Type: {el.input_type}")
                    print(f"    Best: {el.best_selector}  ({max(el.candidate_selectors.values())}/100)")
                else:
                    print(f"  ✗ No element found for '{selector}'")

            elif cmd in ("hi", "highlight") and args:
                selector = args[0]
                ok = await self.highlight(selector)
                print(f"  {'✓ Highlighted' if ok else '✗ Not found'} — {selector}")

            elif cmd in ("eval", "evaluate") and args:
                selector = args[0]
                result = await self.evaluate_selector(selector)
                if "error" in result:
                    print(f"  ✗ Error: {result['error']}")
                elif result.get("matches", 0) == 0:
                    print(f"  ✗ 0 matches for '{selector}'")
                else:
                    print(f"  Matches: {result['matches']}")
                    print(f"  Tag: <{result.get('tag', '?')}>")
                    print(f"  Text: {result.get('text', '')[:80]}")
                    print(f"  Score: {result.get('score', '?')}/100")
                    print(f"  HTML: {result.get('html', '')[:200]}")

            elif cmd == "list":
                if not self.captured:
                    print("  (no elements captured)")
                else:
                    print(f"  {len(self.captured)} captured elements:")
                    for i, el in enumerate(self.captured):
                        label = el.label or el.text or el.placeholder or el.tag
                        sel = el.best_selector
                        sc = max(el.candidate_selectors.values()) if el.candidate_selectors else 0
                        print(f"  [{i}] {label[:50]:50s}  {sc:3d}  {sel}")

            elif cmd == "show" and args:
                try:
                    idx = int(args[0])
                    el = self.captured[idx]
                    print(el.score_summary())
                except (IndexError, ValueError):
                    print(f"  ✗ Invalid index. Range: 0-{len(self.captured) - 1}")

            elif cmd == "export":
                mapping = self.generate_mapping()
                print(yaml.dump(mapping, default_flow_style=False, allow_unicode=True))

            elif cmd == "clear":
                count = len(self.captured)
                self.captured.clear()
                print(f"  ✓ Cleared {count} captured elements")

            else:
                print(f"  ? Unknown command '{cmd}'. Type 'help'")

        # Cleanup highlight styles
        try:
            await self._engine.evaluate(
                "const s = document.getElementById('insuredesk-inspector-styles');"
                "if (s) s.remove();"
                "document.querySelectorAll('.insuredesk-inspector-highlight').forEach(el => {"
                "  el.style.outline = el.dataset.insuredeskOrig || '';"
                "  delete el.dataset.insuredeskOrig;"
                "  el.classList.remove('insuredesk-inspector-highlight');"
                "})"
            )
        except Exception:
            pass

        print("  Bye!")


# ══════════════════════════════════════════════════════════════════
# Offline / testing helpers
# ══════════════════════════════════════════════════════════════════

def from_element_dict(data: dict) -> CapturedElement:
    """Create CapturedElement from a dict (for testing without browser)."""
    attrs = data.get("attributes", {})
    tag = data.get("tag", "div")
    text = data.get("text", "")
    label = data.get("label", "")

    candidates = generate_candidate_selectors(tag, attrs, label or text)

    return CapturedElement(
        tag=tag,
        text=text,
        attributes=attrs,
        selector=data.get("selector", next(iter(candidates)) if candidates else ""),
        input_type=data.get("input_type", "") or attrs.get("type", ""),
        placeholder=attrs.get("placeholder", ""),
        label=label,
        role=attrs.get("role", ""),
        candidate_selectors=candidates,
    )
