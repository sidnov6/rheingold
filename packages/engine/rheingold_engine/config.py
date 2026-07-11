"""Defaults loader: packaged defaults.yaml → Assumptions (spec Appendix B).

defaults.yaml mirrors models.Assumptions field-for-field; every node carries a
``value`` key (the default) and a ``source`` string (rendered on the methodology
page — config IS documentation). This module reads only the ``value`` keys.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .models import Assumptions

_DEFAULTS_PATH = Path(__file__).parent / "defaults.yaml"


def load_defaults() -> dict[str, Any]:
    """Return {field_name: default_value} from the packaged defaults.yaml."""
    with open(_DEFAULTS_PATH, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    if not isinstance(raw, dict):
        raise ValueError(f"defaults.yaml is malformed: expected a mapping, got {type(raw)}")
    values: dict[str, Any] = {}
    for field, node in raw.items():
        if not isinstance(node, dict) or "value" not in node:
            raise ValueError(f"defaults.yaml field '{field}' has no 'value' key")
        values[field] = node["value"]
    return values


def assumptions_from_defaults(overrides: dict[str, Any] | None = None) -> Assumptions:
    """Build Assumptions from defaults.yaml 'value' keys, applying overrides on top.

    Unknown override keys raise (pydantic would otherwise silently ignore them).
    """
    values = load_defaults()
    overrides = overrides or {}
    unknown = set(overrides) - set(Assumptions.model_fields)
    if unknown:
        raise ValueError(f"unknown assumption override(s): {sorted(unknown)}")
    values.update(overrides)
    return Assumptions(**values)
