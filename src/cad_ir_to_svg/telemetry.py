"""
Structured telemetry, warning taxonomy, and compilation reporting for cad-ir-to-svg.
Implements the MCP & AI Agent Interoperability Invariant: deterministic structured error reporting.
"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, List, Optional, Dict


class HardeningCategory(str, Enum):
    COORDINATE_SINGULARITY = "coordinate_singularity"
    DEGENERATE_GEOMETRY = "degenerate_geometry"
    TRANSFORM_ABUSE = "transform_abuse"
    METADATA_MALFORMED = "metadata_malformed"
    FONT_FALLBACK = "font_fallback"
    COLOR_FALLBACK = "color_fallback"
    OUTLIER_PRUNED = "outlier_pruned"


class ActionTaken(str, Enum):
    DROPPED = "dropped"
    CLAMPED = "clamped"
    FALLBACK_APPLIED = "fallback_applied"
    SANITIZED = "sanitized"


@dataclass
class HardeningWarning:
    category: HardeningCategory
    action: ActionTaken
    entity_type: str
    reason: str
    entity_index: Optional[int] = None
    layer: Optional[str] = None
    original_value: Any = None
    sanitized_value: Any = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "category": self.category.value,
            "action": self.action.value,
            "entity_type": self.entity_type,
            "reason": self.reason,
            "entity_index": self.entity_index,
            "layer": self.layer,
            "original_value": str(self.original_value) if self.original_value is not None else None,
            "sanitized_value": str(self.sanitized_value) if self.sanitized_value is not None else None,
        }


@dataclass
class CompilationReport:
    output_target: Optional[str] = None
    success: bool = True
    total_entities_read: int = 0
    total_entities_rendered: int = 0
    total_entities_dropped: int = 0
    total_entities_sanitized: int = 0
    viewbox: Optional[str] = None
    width: float = 0.0
    height: float = 0.0
    layers_rendered: List[str] = field(default_factory=list)
    warnings: List[HardeningWarning] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "output_target": self.output_target,
            "success": self.success,
            "total_entities_read": self.total_entities_read,
            "total_entities_rendered": self.total_entities_rendered,
            "total_entities_dropped": self.total_entities_dropped,
            "total_entities_sanitized": self.total_entities_sanitized,
            "viewbox": self.viewbox,
            "width": self.width,
            "height": self.height,
            "layers_rendered": self.layers_rendered,
            "warnings_count": len(self.warnings),
            "warnings": [w.to_dict() for w in self.warnings],
        }
