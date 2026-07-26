"""InsureDesk Runtime — Adapter Selector.

Auto-detects which portal adapter to use based on raw data fields.

Strategy:
1. If portal_hint is provided, use it directly
2. Otherwise, score each registered adapter by:
   - How many of its FIELD_MAP raw keys appear in the data
   - Special portal-specific signatures (e.g. 'certificate_no' → Allianz)
3. The adapter with the highest score wins

Returns DetectionResult with confidence scores and alternatives.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Any, TYPE_CHECKING
from dataclasses import dataclass, field

if TYPE_CHECKING:
    from src.runtime.registry import AdapterRegistry

from src.runtime.errors import AdapterNotFoundError, MissingDataError


# ══════════════════════════════════════════════════════════════════
# Detection Result Types
# ══════════════════════════════════════════════════════════════════


@dataclass
class DetectionCandidate:
    """A single adapter candidate with its confidence score.

    Attributes:
        adapter: Canonical adapter key (e.g. 'allianz')
        confidence: Confidence score 0.0–1.0
    """
    adapter: str
    confidence: float


@dataclass
class DetectionResult:
    """Result of portal detection.

    Attributes:
        adapter: The selected adapter key, or None if no match
        confidence: Confidence score 0.0–1.0 for the selected adapter
        matched_fields: Raw data field names that matched this adapter's map
        alternatives: Other candidates ranked by confidence (descending)
        detection_method: How detection was resolved
            'explicit' = portal_hint provided
            'signature' = portal-specific key matched
            'field_match' = FIELD_MAP scoring
            'fallback' = default adapter used
            'none' = no match
        reason: Human-readable explanation
    """
    adapter: Optional[str] = None
    confidence: float = 0.0
    matched_fields: List[str] = field(default_factory=list)
    alternatives: List[DetectionCandidate] = field(default_factory=list)
    detection_method: str = "none"
    reason: str = ""

    def get_adapter(self, registry: "AdapterRegistry"):
        """Get the ModelAdapter instance for the selected adapter."""
        if not self.adapter:
            return None
        return registry.get(self.adapter)

    def is_certain(self, threshold: float = 0.5) -> bool:
        """Whether detection is confident enough."""
        return self.confidence >= threshold


# ── Portal-specific signature keys (high confidence) ──

PORTAL_SIGNATURES: Dict[str, List[str]] = {
    "great_eastern": ["cover_note_no", "cover_note", "policy_no"],
    "allianz": ["certificate_no", "certificate_number"],
    "aia": ["life_assured", "policy_id", "plan_name"],
}

# Fields to ignore when scoring (generic/common)
IGNORED_FIELDS = {"status", "source", "raw_text", "type", "id", "name"}

# Signature bonus contributes this fraction of max confidence
SIGNATURE_BONUS_WEIGHT = 0.3


def compute_confidence(
    raw_score: int,
    max_possible: int,
    has_signature: bool,
) -> float:
    """Convert raw score to normalized confidence 0.0–1.0.

    Args:
        raw_score: Integer score from score_adapter
        max_possible: Maximum score any adapter could achieve
        has_signature: Whether a portal-specific signature matched

    Returns:
        Confidence between 0.0 and 1.0
    """
    if max_possible <= 0:
        return 0.0
    if raw_score <= 0:
        return 0.0

    # Base confidence from field match proportion
    base = raw_score / max_possible

    # Boost for signature match (caps at 1.0)
    boost = SIGNATURE_BONUS_WEIGHT if has_signature else 0.0

    return min(base + boost, 1.0)


def score_adapter(adapter_cls, raw_keys: set) -> tuple:
    """Score how well an adapter matches raw data keys.

    Scoring logic:
    - +1 for each FIELD_MAP raw key found in data
    - +5 bonus if a portal-specific signature key is present

    Args:
        adapter_cls: ModelAdapter class
        raw_keys: Set of keys in the raw data

    Returns:
        Tuple of (score: int, matched_fields: list[str], has_signature: bool)
    """
    field_map = getattr(adapter_cls, "FIELD_MAP", {})
    raw_map_keys = {k.lower() for k in field_map.keys()}

    # Lowercase data keys for matching
    data_keys = {k.lower() for k in raw_keys if k.lower() not in IGNORED_FIELDS}

    # Find matching keys
    matched = raw_map_keys & data_keys
    matched_original = [k for k in raw_keys if k.lower() in matched]
    score = len(matched)
    has_signature = False

    # Check for portal-specific signatures
    portal_name = getattr(adapter_cls, "PORTAL_NAME", "")
    for portal, signatures in PORTAL_SIGNATURES.items():
        if portal.lower() in portal_name.lower() or any(
            s.lower() in portal_name.lower() for s in signatures
        ):
            for sig in signatures:
                if sig.lower() in data_keys or sig.lower() in raw_keys:
                    score += 5  # High-confidence match
                    has_signature = True

    return score, matched_original, has_signature


def detect_portal_from_data(raw_data: Dict[str, Any]) -> Optional[str]:
    """Detect portal type from raw data keys.

    Uses signature keys for quick detection first.

    Args:
        raw_data: Raw portal data dict

    Returns:
        Canonical adapter key or None if inconclusive
    """
    if not raw_data:
        return None

    raw_keys = set(raw_data.keys())

    # Quick signature detection
    for portal, signatures in PORTAL_SIGNATURES.items():
        for sig in signatures:
            if sig in raw_keys:
                return portal

    return None


def select_adapter(
    raw_data: Dict[str, Any],
    portal_hint: Optional[str] = None,
    registry: Optional["AdapterRegistry"] = None,
) -> DetectionResult:
    """Select the best adapter for raw portal data.

    Returns a DetectionResult with full scoring info,
    confidence scores, and alternative candidates.

    Args:
        raw_data: Raw portal data as a dict
        portal_hint: Optional portal name (skips detection if provided)
        registry: AdapterRegistry instance (creates default if None)

    Returns:
        DetectionResult with selected adapter and alternatives

    Raises:
        MissingDataError: If raw_data is empty or too sparse
    """
    from src.runtime.registry import AdapterRegistry

    if not raw_data:
        raise MissingDataError([])

    reg = registry or AdapterRegistry()

    # ── 1. Explicit portal hint ──
    if portal_hint:
        adapter = reg.get(portal_hint)
        if adapter:
            return DetectionResult(
                adapter=reg._resolve_key(portal_hint),
                confidence=1.0,
                matched_fields=[],
                alternatives=[],
                detection_method="explicit",
                reason=f"Explicit portal hint: {portal_hint}",
            )

    # ── 2. Quick signature detection ──
    detected = detect_portal_from_data(raw_data)
    if detected:
        adapter = reg.get(detected)
        if adapter:
            # Compute alternatives for context
            raw_keys = set(raw_data.keys())
            alternatives = _compute_alternatives(reg, raw_keys, exclude_key=detected)
            return DetectionResult(
                adapter=detected,
                confidence=1.0,
                matched_fields=[s for s in PORTAL_SIGNATURES[detected] if s in raw_data],
                alternatives=alternatives,
                detection_method="signature",
                reason=f"Portal-specific key matched: {detected}",
            )

    # ── 3. Full scoring ──
    raw_keys = set(raw_data.keys())
    scored = _score_all_adapters(reg, raw_keys)

    if not scored:
        raise AdapterNotFoundError(available=reg.list())

    # Best match
    best = scored[0]

    if best["score"] <= 0:
        raise MissingDataError(list(raw_keys)[:20])

    # Normalize confidence against max possible score
    max_score = max(s["score"] for s in scored)
    confidence = compute_confidence(
        best["score"], max_score, best["has_signature"]
    )

    alternatives = [
        DetectionCandidate(adapter=s["key"], confidence=compute_confidence(s["score"], max_score, s["has_signature"]))
        for s in scored[1:4]  # Top 3 alternatives
        if s["score"] > 0
    ]

    return DetectionResult(
        adapter=best["key"],
        confidence=round(confidence, 4),
        matched_fields=best["matched_fields"],
        alternatives=alternatives,
        detection_method="field_match",
        reason=f"Scored {best['score']}/{max_score} on field match",
    )


# ── Internal Helpers ──


def _compute_alternatives(reg, raw_keys: set, exclude_key: str) -> List[DetectionCandidate]:
    """Compute alternative candidates (for signature-match results)."""
    scored = _score_all_adapters(reg, raw_keys)
    if not scored:
        return []

    scored = [s for s in scored if s["key"] != exclude_key]
    if not scored:
        return []

    max_score = max(s["score"] for s in scored) or 1
    return [
        DetectionCandidate(adapter=s["key"], confidence=round(compute_confidence(s["score"], max_score, s["has_signature"]), 4))
        for s in scored[:3]
        if s["score"] > 0
    ]


def _score_all_adapters(reg, raw_keys: set) -> List[dict]:
    """Score all adapters against raw keys."""
    scored = []
    for entry in reg.list():
        key = entry["key"]
        cls = _get_adapter_class(reg, key)
        if cls:
            score, matched, has_sig = score_adapter(cls, raw_keys)
            scored.append({
                "key": key,
                "name": entry["name"],
                "score": score,
                "matched_fields": matched,
                "has_signature": has_sig,
            })
    scored.sort(key=lambda x: -x["score"])
    return scored


def _get_adapter_class(registry, key: str):
    """Get the adapter class from the registry."""
    inst = registry.get(key)
    if inst:
        return type(inst)
    return None
