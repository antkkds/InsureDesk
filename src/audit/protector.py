"""InsureDesk — Audit: Sensitive Data Protection.

Field masking, audit redaction, and credential access logging
for production security compliance.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set

from src.audit.models import (
    PARTIAL_MASK_FIELDS,
    REDACTED_FIELDS,
    SENSITIVE_FIELD_PATTERNS,
    AuditEntry,
    AuditCategory,
    AuditLevel,
)


class SensitiveDataProtector:
    """Masks and redacts sensitive fields in audit logs and data.

    Rules:
    - Fields in REDACTED_FIELDS: completely removed (show "[REDACTED]")
    - Fields in PARTIAL_MASK_FIELDS: show only last 4 chars
    - Fields matching SENSITIVE_FIELD_PATTERNS by substring: partial mask
    - All other fields pass through unchanged
    """

    def __init__(self, custom_patterns: Optional[List[str]] = None):
        self._redacted: Set[str] = set(REDACTED_FIELDS)
        self._partial: Set[str] = set(PARTIAL_MASK_FIELDS)
        self._patterns: List[str] = custom_patterns or []

    def mask_value(self, field_name: str, value: Any) -> Any:
        """Mask a single field value based on field name rules."""
        field_lower = field_name.lower()

        # Full redaction
        if self._is_redacted(field_lower):
            return "[REDACTED]"

        # Partial mask
        if self._is_partial(field_lower) or self._matches_pattern(field_lower):
            return self._partial_mask(str(value))

        return value

    def mask_dict(self, data: Dict[str, Any], path: str = "") -> Dict[str, Any]:
        """Recursively mask sensitive fields in a dictionary.

        Args:
            data: Dict to mask.
            path: Dot-separated path prefix for nested fields.

        Returns:
            New dict with sensitive fields masked (original unchanged).
        """
        result: Dict[str, Any] = {}
        for key, value in data.items():
            full_path = f"{path}.{key}" if path else key

            if isinstance(value, dict):
                result[key] = self.mask_dict(value, full_path)
            elif isinstance(value, list):
                result[key] = [
                    self.mask_dict(item, full_path) if isinstance(item, dict)
                    else self.mask_value(full_path, item)
                    for item in value
                ]
            else:
                result[key] = self.mask_value(full_path, value)
        return result

    def redact_entry(self, entry: AuditEntry) -> AuditEntry:
        """Return a redacted copy of an audit entry."""
        redacted = AuditEntry(
            id=entry.id,
            timestamp=entry.timestamp,
            level=entry.level,
            category=entry.category,
            action=entry.action,
            actor=entry.actor,
            portal_id=entry.portal_id,
            workflow_id=entry.workflow_id,
            execution_id=entry.execution_id,
            message=entry.message,
            details=self.mask_dict(entry.details),
            sensitive=True,
            duration_ms=entry.duration_ms,
            error=entry.error,
        )
        return redacted

    def is_sensitive_field(self, field_name: str) -> bool:
        """Check if a field name looks sensitive."""
        f = field_name.lower()
        return self._is_redacted(f) or self._is_partial(f) or self._matches_pattern(f)

    def _is_redacted(self, field_lower: str) -> bool:
        leaf = field_lower.split(".")[-1]
        return leaf in self._redacted

    def _is_partial(self, field_lower: str) -> bool:
        leaf = field_lower.split(".")[-1]
        return leaf in self._partial

    def _matches_pattern(self, field_lower: str) -> bool:
        leaf = field_lower.split(".")[-1]
        for pattern in SENSITIVE_FIELD_PATTERNS:
            if pattern in leaf:
                return True
        for pattern in self._patterns:
            if re.search(pattern, leaf):
                return True
        return False

    @staticmethod
    def _partial_mask(value: str) -> str:
        """Mask all but the last 4 characters."""
        s = str(value)
        if len(s) <= 4:
            return "****"
        return "*" * (len(s) - 4) + s[-4:]


class CredentialAccessLogger:
    """Logs credential access events for security auditing.

    Records who accessed which credential and when,
    without logging the actual credential value.
    """

    def __init__(self, protector: Optional[SensitiveDataProtector] = None):
        self._protector = protector or SensitiveDataProtector()
        self._access_log: List[AuditEntry] = []

    def log_access(
        self,
        portal_id: str,
        actor: str,
        credential_type: str,
        workflow_id: str = "",
    ) -> AuditEntry:
        """Log a credential access event.

        The actual credential value is NEVER logged.
        """
        entry = AuditEntry(
            level=AuditLevel.INFO,
            category=AuditCategory.CREDENTIAL,
            action="credential_access",
            actor=actor,
            portal_id=portal_id,
            workflow_id=workflow_id,
            message=f"Credential accessed: {credential_type} for {portal_id}",
            details={
                "credential_type": credential_type,
                "portal_id": portal_id,
                "actor": actor,
            },
            sensitive=False,  # No actual credential value
        )
        self._access_log.append(entry)
        return entry

    def log_access_failure(
        self,
        portal_id: str,
        actor: str,
        credential_type: str,
        error: str,
    ) -> AuditEntry:
        entry = AuditEntry(
            level=AuditLevel.ERROR,
            category=AuditCategory.CREDENTIAL,
            action="credential_access_failed",
            actor=actor,
            portal_id=portal_id,
            message=f"Credential access failed: {credential_type} for {portal_id}",
            details={
                "credential_type": credential_type,
                "portal_id": portal_id,
            },
            error=error,
        )
        self._access_log.append(entry)
        return entry

    def get_recent_accesses(self, limit: int = 20) -> List[AuditEntry]:
        return self._access_log[-limit:]


# Default global protector
default_protector = SensitiveDataProtector()
