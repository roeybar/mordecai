"""Typed hand-offs between the pipeline stages. Data only; no behaviour."""
from __future__ import annotations

from dataclasses import dataclass, field

from ..sense_solver import Reading


@dataclass
class Analysis:
    source: str
    src_lang: str
    tokens: list[str]
    lattice: list[list[Reading]]


@dataclass
class Resolution:
    choice: list[int | None]
    greedy: list[int | None]
    score: int
    evaluated: int


@dataclass
class Rendered:
    text: str
    provider: str
    notice: str


@dataclass
class Repaired:
    text: str
    notes: list[str] = field(default_factory=list)


@dataclass
class Verdict:
    ok: bool
    notes: list[dict] = field(default_factory=list)


@dataclass
class PipelineResult:
    text: str
    source_lang: str
    target_lang: str
    analysis: Analysis
    resolution: Resolution
    rendered: Rendered
    repaired: Repaired
    verdict: Verdict
