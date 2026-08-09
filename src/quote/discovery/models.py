"""InsureDesk — Form Discovery Models.

Data models for form field structure, used by FormScanner
to represent discovered form schemas.

Flow:
    FormScanner.scan() → FormSchema
        ↓
    FormSchema.to_profile() → Profile YAML
        ↓
    QuoteAdapter reads profile → fills form
"""

from __future__ import annotations

from dataclasses import dataclass, field as dataclass_field
from typing import Optional, Dict, Any, List


@dataclass
class FieldOption:
    """A single option in a dropdown/select field."""
    value: str = ""
    label: str = ""
    selected: bool = False


@dataclass
class FieldDependency:
    """A conditional dependency: when field == value → show/hide fields."""
    field: str = ""
    equals: str = ""
    show_fields: List[str] = dataclass_field(default_factory=list)
    hide_fields: List[str] = dataclass_field(default_factory=list)


@dataclass
class FormField:
    """A single form field discovered on the page.

    Captures all metadata needed for QuoteAdapter to interact with it.
    """
    # Identity
    key: str = ""               # unique field key (e.g. "proposer_name")
    label: str = ""             # visible label text
    placeholder: str = ""       # placeholder text

    # Location
    selector: str = ""          # best CSS selector
    best_selector: str = ""     # highest-scored selector
    candidate_selectors: Dict[str, int] = dataclass_field(default_factory=dict)
    page_url: str = ""          # page where this field was found
    iframe_selector: str = ""   # if any, selector for parent iframe
    frame_index: int = -1       # iframe index (-1 = main page)

    # Type
    field_type: str = "text"    # text, select, checkbox, radio, textarea, file, button, email, tel, number, date
    tag: str = "input"          # input, select, textarea, button, a

    # Validation
    required: bool = False
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    pattern: str = ""           # regex validation pattern

    # Options (for select/radio)
    options: List[FieldOption] = dataclass_field(default_factory=list)
    multiple: bool = False

    # Dependencies
    dependencies: List[FieldDependency] = dataclass_field(default_factory=list)

    # Metadata
    section: str = ""           # form section/group name
    order: int = 0              # display order within section
    discovered_at: str = ""     # timestamp

    def to_dict(self) -> dict:
        d = {
            "key": self.key,
            "label": self.label,
            "selector": self.best_selector or self.selector,
            "tag": self.tag,
            "field_type": self.field_type,
            "required": self.required,
        }
        if self.placeholder:
            d["placeholder"] = self.placeholder
        if self.options:
            d["options"] = [{"value": o.value, "label": o.label} for o in self.options]
        if self.multiple:
            d["multiple"] = True
        if self.min_length is not None:
            d["min_length"] = self.min_length
        if self.max_length is not None:
            d["max_length"] = self.max_length
        if self.pattern:
            d["pattern"] = self.pattern
        if self.section:
            d["section"] = self.section
        return d


@dataclass
class FormPage:
    """A page within a multi-page form or wizard."""
    name: str = ""
    url_pattern: str = ""
    title_pattern: str = ""
    fields: List[FormField] = dataclass_field(default_factory=list)
    actions: List[dict] = dataclass_field(default_factory=list)
    # actions: [{"key": "next", "selector": "...", "type": "button"}, ...]

    def get_field(self, key: str) -> Optional[FormField]:
        for f in self.fields:
            if f.key == key:
                return f
        return None

    def list_field_keys(self) -> List[str]:
        return [f.key for f in self.fields]

    def required_fields(self) -> List[FormField]:
        return [f for f in self.fields if f.required]


@dataclass
class FormSchema:
    """Complete schema for a quote form, discovered by scanning."""
    portal: str = ""
    quote_channel: str = ""     # "IFE", "EQ"
    product_code: str = ""      # e.g. "IFE_FIRE"
    version: str = "1.0"
    captured_at: str = ""
    pages: List[FormPage] = dataclass_field(default_factory=list)

    def get_page(self, name: str) -> Optional[FormPage]:
        for p in self.pages:
            if p.name == name:
                return p
        return None

    def all_fields(self) -> List[FormField]:
        fields = []
        for page in self.pages:
            fields.extend(page.fields)
        return fields

    def required_fields(self) -> List[FormField]:
        return [f for f in self.all_fields() if f.required]

    def total_fields(self) -> int:
        return len(self.all_fields())

    def to_profile_yaml(self) -> dict:
        """Convert to profile YAML structure (compatible with profiles/*.yaml)."""
        pages_dict = {}
        for page in self.pages:
            elements = {}
            for f in page.fields:
                elements[f.key] = f.to_dict()
            actions_list = []
            for a in page.actions:
                actions_list.append({
                    "key": a.get("key", ""),
                    "selector": a.get("selector", ""),
                    "type": a.get("type", "button"),
                })
            page_data = {
                "description": f"{page.name} form page",
                "url_pattern": page.url_pattern,
                "elements": elements,
            }
            if actions_list:
                page_data["actions"] = actions_list
            pages_dict[page.name] = page_data

        return {
            "version": self.version,
            "portal": self.portal,
            "quote_channel": self.quote_channel,
            "product_code": self.product_code,
            "captured_at": self.captured_at,
            "pages": pages_dict,
        }
