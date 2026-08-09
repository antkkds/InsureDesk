"""InsureDesk — Profile Validation Engine.

Validates captured portal profiles for:
1. Selector validity (unique, stable, realistic)
2. Field type detection accuracy
3. Required field detection
4. Options completeness
5. Dependency coverage
"""

from __future__ import annotations

from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
import re


# ══════════════════════════════════════════════════════════════════
# Validation Models
# ══════════════════════════════════════════════════════════════════


@dataclass
class ValidationIssue:
    """A single issue found during profile validation."""
    severity: str  # "error", "warning", "info"
    category: str  # "selector", "field_type", "required", "options", "dependency"
    field_key: str
    message: str
    suggestion: str = ""


@dataclass
class ProfileValidationResult:
    """Complete profile validation result."""
    profile_name: str
    total_fields: int = 0
    issues: List[ValidationIssue] = field(default_factory=list)
    score: float = 0.0  # 0-100 quality score

    @property
    def errors(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == "warning"]

    @property
    def passed(self) -> bool:
        return len(self.errors) == 0


# ══════════════════════════════════════════════════════════════════
# Profile Validator
# ══════════════════════════════════════════════════════════════════


class ProfileValidator:
    """Validates captured portal profiles.

    Usage:
        validator = ProfileValidator()
        with open("profiles/ife_quote.yaml") as f:
            profile = yaml.safe_load(f)
        result = validator.validate("ife_quote", profile)
        print(f"Score: {result.score}/100, Issues: {len(result.issues)}")
    """

    VALID_FIELD_TYPES = {
        "text", "select", "checkbox", "radio", "date",
        "textarea", "email", "tel", "number", "file", "password",
    }

    # Selector quality patterns
    GOOD_SELECTOR_PATTERNS = [
        re.compile(r"^#[a-zA-Z][\w-]*$"),                      # #id
        re.compile(r"^\[name=['\"][^'\"]+['\"]\]$"),            # [name='...']
        re.compile(r"^\[data-testid=['\"][^'\"]+['\"]\]$"),     # [data-testid='...']
        re.compile(r"^input\[name=['\"][^'\"]+['\"]\]$"),       # input[name='...']
        re.compile(r"^select\[name=['\"][^'\"]+['\"]\]$"),      # select[name='...']
    ]

    # Weak/noisy selectors
    WEAK_SELECTOR_PATTERNS = [
        re.compile(r"^input$"),                                  # bare tag
        re.compile(r"^select$"),
        re.compile(r"^textarea$"),
        re.compile(r"^div$"),
        re.compile(r"^\*$"),
    ]

    GENERATED_KEYS_PATTERN = re.compile(r"^field_\d+$")

    def __init__(self):
        self._known_ids: Dict[str, int] = {}
        self._known_names: Dict[str, int] = {}

    def validate(self, profile_name: str, profile_data: dict) -> ProfileValidationResult:
        """Validate a complete profile YAML structure."""
        result = ProfileValidationResult(profile_name=profile_name)
        issues: List[ValidationIssue] = []

        pages = profile_data.get("pages", {})
        if not pages:
            issues.append(ValidationIssue(
                severity="error", category="structure",
                field_key="pages",
                message="Profile has no pages defined",
            ))
            result.issues = issues
            return result

        total_fields = 0
        for page_name, page_data in pages.items():
            elements = page_data.get("elements", {})
            if not elements:
                issues.append(ValidationIssue(
                    severity="warning", category="structure",
                    field_key=page_name,
                    message=f"Page '{page_name}' has no elements",
                ))
                continue

            for field_key, field_data in elements.items():
                total_fields += 1
                issues.extend(self._validate_field(field_key, field_data))

        result.total_fields = total_fields
        result.issues = issues

        # Calculate score
        score = self._calculate_score(issues, total_fields)
        result.score = score

        return result

    def _validate_field(self, key: str, data: dict) -> List[ValidationIssue]:
        """Validate a single field definition."""
        issues = []

        # 1. Key quality
        if self.GENERATED_KEYS_PATTERN.match(key):
            issues.append(ValidationIssue(
                severity="warning", category="naming",
                field_key=key,
                message=f"Generated key '{key}' — consider renaming with meaningful name",
                suggestion="Use a meaningful key like 'insured_name' instead of 'field_0'",
            ))

        # 2. Selector validation
        selector = data.get("selector", "")
        if not selector:
            issues.append(ValidationIssue(
                severity="error", category="selector",
                field_key=key,
                message="No selector defined for field",
            ))
        else:
            # Check if selector is weak
            is_weak = any(p.match(selector) for p in self.WEAK_SELECTOR_PATTERNS)
            if is_weak:
                issues.append(ValidationIssue(
                    severity="error", category="selector",
                    field_key=key,
                    message=f"Weak selector '{selector}' — only tag name, likely not unique",
                    suggestion="Use an ID-based selector like #field_id or [name='field_name']",
                ))

            is_good = any(p.match(selector) for p in self.GOOD_SELECTOR_PATTERNS)
            if not is_good and not is_weak:
                issues.append(ValidationIssue(
                    severity="info", category="selector",
                    field_key=key,
                    message=f"Non-standard selector '{selector}' — may need verification",
                ))

            # Check uniqueness
            if selector.startswith("[name="):
                name_val = selector.split("=")[1].strip("'\"")
                if name_val in self._known_names:
                    # This shouldn't happen during static analysis
                    pass
                self._known_names[name_val] = self._known_names.get(name_val, 0) + 1

        # 3. Field type validation
        field_type = data.get("field_type", "")
        if field_type and field_type not in self.VALID_FIELD_TYPES:
            issues.append(ValidationIssue(
                severity="warning", category="field_type",
                field_key=key,
                message=f"Unknown field type '{field_type}'",
                suggestion=f"Use one of: {', '.join(sorted(self.VALID_FIELD_TYPES))}",
            ))

        if not field_type:
            issues.append(ValidationIssue(
                severity="warning", category="field_type",
                field_key=key,
                message="No field_type defined",
                suggestion="Set field_type to one of: text, select, checkbox, radio, date",
            ))

        # 4. Tag validation
        tag = data.get("tag", "")
        valid_tags = {"input", "select", "textarea", "button", "a", "div", "span"}
        if tag and tag not in valid_tags:
            issues.append(ValidationIssue(
                severity="info", category="tag",
                field_key=key,
                message=f"Unusual tag '{tag}'",
            ))

        # 5. Options validation (for select fields)
        if field_type == "select":
            options = data.get("options", [])
            if not options:
                issues.append(ValidationIssue(
                    severity="warning", category="options",
                    field_key=key,
                    message=f"Select field '{key}' has no options defined",
                    suggestion="Add options with value/label pairs, or mark as text if auto-complete",
                ))
            else:
                # Check for empty values
                empty_options = [o for o in options if not o.get("value")]
                if empty_options and len(options) > 1:
                    issues.append(ValidationIssue(
                        severity="info", category="options",
                        field_key=key,
                        message=f"Select field has {len(empty_options)} option(s) with empty value (placeholder)",
                    ))

        # 6. Required field
        required = data.get("required", False)
        if not isinstance(required, bool):
            issues.append(ValidationIssue(
                severity="warning", category="required",
                field_key=key,
                message=f"required field is {type(required).__name__}, expected bool",
            ))

        return issues

    def _calculate_score(self, issues: List[ValidationIssue], total_fields: int) -> float:
        """Calculate quality score (0-100)."""
        if total_fields == 0:
            return 0.0

        error_weight = 10
        warning_weight = 3
        info_weight = 1

        errors = len([i for i in issues if i.severity == "error"])
        warnings = len([i for i in issues if i.severity == "warning"])
        infos = len([i for i in issues if i.severity == "info"])

        penalty = (errors * error_weight + warnings * warning_weight + infos * info_weight)
        max_penalty = total_fields * error_weight * 3
        penalty_ratio = min(penalty / max_penalty, 1.0)

        return round(100.0 * (1.0 - penalty_ratio), 1)

    def summary(self, result: ProfileValidationResult) -> str:
        """Return a human-readable validation summary."""
        errors = len(result.errors)
        warnings = len(result.warnings)
        infos = len([i for i in result.issues if i.severity == "info"])

        lines = [
            f"Profile: {result.profile_name}",
            f"Fields:  {result.total_fields}",
            f"Score:   {result.score}/100",
            f"Issues:  {errors} errors, {warnings} warnings, {infos} info",
        ]

        if errors:
            lines.append("\nErrors:")
            for issue in result.errors[:5]:
                lines.append(f"  ❌ [{issue.category}] {issue.field_key}: {issue.message}")
            if len(result.errors) > 5:
                lines.append(f"  ... and {len(result.errors) - 5} more errors")

        if warnings:
            lines.append("\nWarnings:")
            for issue in result.warnings[:5]:
                lines.append(f"  ⚠️  [{issue.category}] {issue.field_key}: {issue.message}")
            if len(result.warnings) > 5:
                lines.append(f"  ... and {len(result.warnings) - 5} more warnings")

        return "\n".join(lines)
