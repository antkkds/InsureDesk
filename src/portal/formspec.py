"""InsureDesk — FormSpec: declarative portal form definitions.

FormSpec is the *thin contract* between business data and browser
execution (ChatGPT review step 2-4):

    FormSpec (Pydantic, YAML-serializable)
        └── sections (ordered steps)
              └── fields (name → selector/type/behavior)
                    └── FillEngine strategies do the actual filling

It deliberately does NOT import or depend on browser internals. The same
FormSpec can be executed against Playwright, CDP, or a mock browser.

Pydantic is the in-memory representation; YAML is the on-disk format so
non-engineers can add/edit form mappings without touching Python.

    from src.portal.formspec import MotorPrivateCarSpec
    spec = MotorPrivateCarSpec.from_yaml(open("motor_private_car.yaml").read())
    schema = spec.to_fill_schema("owner")          # → FillSchema
"""
from __future__ import annotations

from typing import Any, Optional
import io

import yaml
from pydantic import BaseModel, Field, field_validator

from src.fill.schema import FieldType, FillSchema, FieldDefinition


# ---------------------------------------------------------------------------
# Field / section models
# ---------------------------------------------------------------------------

class FormFieldSpec(BaseModel):
    """One form field in a section. Mirrors FieldDefinition for YAML ergonomics.

    YAML:
        vehicleNumber:
          selector: "#vehicleNumber"
          type: text
          required: true
          verify: true
          clear_first: true
          autocomplete: true      # extra behavior hint (mat-option click)
    """
    name: str
    selector: str
    type: str = "text"
    required: bool = False
    verify: bool = True
    retry: int = 2
    clear_first: bool = True
    timeout: int = 5000
    transform: Optional[str] = None
    format: Optional[str] = None
    options: dict[str, Any] = Field(default_factory=dict)
    max_length: Optional[int] = None
    # Status gate (ChatGPT review 2026-08):
    #   confirmed      — selector verified against live GEARS (locate→interact→read-back)
    #   needs_capture  — reasonable inference, NOT yet live-verified
    #   blocked        — attempted capture failed; selector/interaction model invalid
    # HARD RULE: only confirmed fields may enter live execution.
    status: str = "confirmed"

    @field_validator("status")
    @classmethod
    def _valid_status(cls, v: str) -> str:
        if v not in ("confirmed", "needs_capture", "blocked"):
            raise ValueError(f"status must be confirmed|needs_capture|blocked, got '{v}'")
        return v

    @property
    def is_live_ready(self) -> bool:
        """Only confirmed selectors may run against a live portal."""
        return self.status == "confirmed"

    @field_validator("type")
    @classmethod
    def _valid_type(cls, v: str) -> str:
        # Validate against existing FieldType vocabulary (case-insensitive)
        FieldType(v)
        return v

    def to_field_definition(self) -> FieldDefinition:
        """Convert to the FillEngine FieldDefinition."""
        return FieldDefinition(
            name=self.name,
            selector=self.selector,
            type=FieldType(self.type),
            required=self.required,
            verify=self.verify,
            retry=self.retry,
            clear_first=self.clear_first,
            timeout=self.timeout,
            transform=self.transform,
            format=self.format,
            options=dict(self.options),
            max_length=self.max_length,
        )


class FormSectionSpec(BaseModel):
    """An ordered step in the form (e.g. Quotation Details, Details, Payment).

    YAML:
        - name: quotation_details
          description: "Step 1 — applicant & vehicle identifiers"
          submit: "button:has-text('Next')"
          fields: [...]
    """
    name: str
    description: str = ""
    submit: Optional[str] = None      # selector to advance to next section
    fields: list[FormFieldSpec] = Field(default_factory=list)

    def to_fill_schema(self) -> FillSchema:
        """Convert to a FillEngine FillSchema (ordered fields preserved)."""
        return FillSchema(
            name=self.name,
            fields={f.name: f.to_field_definition() for f in self.fields},
        )


# ---------------------------------------------------------------------------
# Motor Private Car FormSpec
# ---------------------------------------------------------------------------

class MotorPrivateCarSpec(BaseModel):
    """Declarative spec for the GEARS Private Motor (Private Car) quote flow.

    Source: gears_research/products_map.md (Motor Insurance section, 2026-08).
    Flow:  Quotation Details → Details → Sum Insured/Add-on → Payment
    Entry: introduce/product-list?id=PMOT → Get quote

    Usage:
        spec = MotorPrivateCarSpec.from_yaml(text)
        for section in spec.sections:
            schema = section.to_fill_schema()
            result = await engine.fill_section(browser, schema, data)
    """
    product_id: str = "PMOT"
    product_name: str = "Private Motor Insurance (Private Car)"
    portal: str = "great_eastern_gears"
    version: str = "1.0"
    entry_url: str = "/MY/AgencySales/quotations/introduce"
    sections: list[FormSectionSpec] = Field(default_factory=list)

    # -- YAML round-trip ------------------------------------------------

    def to_yaml(self) -> str:
        """Serialize to YAML (for Config Studio / git diffs)."""
        return yaml.safe_dump(
            self.model_dump(mode="json"),
            sort_keys=False,
            allow_unicode=True,
        )

    @classmethod
    def from_yaml(cls, text: str) -> "MotorPrivateCarSpec":
        """Load from YAML text."""
        data = yaml.safe_load(text)
        return cls.model_validate(data)

    @classmethod
    def from_yaml_file(cls, path: str) -> "MotorPrivateCarSpec":
        with io.open(path, "r", encoding="utf-8") as fh:
            return cls.from_yaml(fh.read())

    # -- FillEngine integration -----------------------------------------

    def to_fill_schemas(self) -> dict[str, FillSchema]:
        """All sections as FillSchemas keyed by section name."""
        return {s.name: s.to_fill_schema() for s in self.sections}

    def section(self, name: str) -> Optional[FormSectionSpec]:
        """Lookup a section by name."""
        for s in self.sections:
            if s.name == name:
                return s
        return None

    def field(self, section_name: str, field_name: str) -> Optional[FormFieldSpec]:
        """Lookup a field within a section."""
        sec = self.section(section_name)
        if sec is None:
            return None
        for f in sec.fields:
            if f.name == field_name:
                return f
        return None

    def required_fields(self, section_name: str) -> list[str]:
        """Names of required fields in a section (for validation)."""
        sec = self.section(section_name)
        if sec is None:
            return []
        return [f.name for f in sec.fields if f.required]

    def live_ready_fields(self, section_name: str) -> list[FormFieldSpec]:
        """Fields allowed into live execution: status == confirmed only.

        HARD RULE (ChatGPT review): needs_capture/blocked fields never
        enter a live portal run. This is the calibration gate — run
        capture first, then this list grows.
        """
        sec = self.section(section_name)
        if sec is None:
            return []
        return [f for f in sec.fields if f.is_live_ready]

    def live_schema(self, section_name: str) -> Optional[FillSchema]:
        """FillSchema containing ONLY live-ready fields for a section.

        Returns None if no fields are confirmed yet.
        """
        fields = self.live_ready_fields(section_name)
        if not fields:
            return None
        return FillSchema(
            name=section_name,
            fields={f.name: f.to_field_definition() for f in fields},
        )
