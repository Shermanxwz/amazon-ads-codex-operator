from __future__ import annotations
from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True)
class Action:
    action_id: str
    action_type: str
    tool_name: str
    ad_product: str
    entity_type: str
    entity_id: str
    arguments: dict[str, Any]
    before: dict[str, Any]
    after: dict[str, Any]
    spend_delta: float
    confidence: float
    evidence_refs: tuple[str, ...]
    dependencies: tuple[str, ...]
    reversible: bool
    rollback: dict[str, Any] | None
    prewrite_observed_at: str | None
    rationale: str = ""

    @classmethod
    def from_dict(cls, row: dict[str, Any]) -> "Action":
        return cls(
            action_id=str(row.get("action_id") or ""), action_type=str(row.get("action_type") or ""), tool_name=str(row.get("tool_name") or ""),
            ad_product=str(row.get("ad_product") or ""), entity_type=str(row.get("entity_type") or ""), entity_id=str(row.get("entity_id") or ""),
            arguments=dict(row.get("arguments") or {}), before=dict(row.get("before") or {}), after=dict(row.get("after") or {}), spend_delta=float(row.get("spend_delta") or 0),
            confidence=float(row.get("confidence") or 0), evidence_refs=tuple(str(x) for x in (row.get("evidence_refs") or [])), dependencies=tuple(str(x) for x in (row.get("dependencies") or [])),
            reversible=bool(row.get("reversible", True)), rollback=dict(row["rollback"]) if isinstance(row.get("rollback"), dict) else None,
            prewrite_observed_at=str(row.get("prewrite_observed_at")) if row.get("prewrite_observed_at") else None, rationale=str(row.get("rationale") or ""),
        )
