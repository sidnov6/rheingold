"""RHEINGOLD deterministic finance engine — pure Python, no network, no LLM,
no unseeded randomness (CLAUDE.md non-negotiable)."""

from .config import assumptions_from_defaults, load_defaults
from .models import (
    AnnualSeries,
    Assumptions,
    DebtResult,
    EnergyResult,
    EvidenceItem,
    FarmInput,
    MarketInputs,
    Shocks,
    TornadoItem,
    UnderwriteResult,
    ValuationResult,
)
from .scenarios import PRESETS
from .underwrite import solve_breakeven_bid, underwrite

__all__ = [
    "PRESETS",
    "AnnualSeries",
    "Assumptions",
    "DebtResult",
    "EnergyResult",
    "EvidenceItem",
    "FarmInput",
    "MarketInputs",
    "Shocks",
    "TornadoItem",
    "UnderwriteResult",
    "ValuationResult",
    "assumptions_from_defaults",
    "load_defaults",
    "solve_breakeven_bid",
    "underwrite",
]
