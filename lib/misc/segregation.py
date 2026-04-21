from __future__ import annotations

from dataclasses import dataclass
from math import inf, log10

# Figure 6 matrix: (lod_min inclusive, lod_max exclusive, candidate_pts, exome_pts)
_LOD_POINT_TABLE: list[tuple[float, float, float, float]] = [
    (0.0, 2.0, 0.0, 0.0),
    (2.0, 3.0, 0.5, 1.0),
    (3.0, 5.0, 1.0, 2.0),
    (5.0, inf, 1.5, 3.0),
]

EXOME_GENOME_METHODS = {'Exome Sequencing', 'Genome Sequencing'}


@dataclass
class FamilySegregationInput:
    family_id: int
    lod_score: float
    method_class: str  # 'candidate_gene' | 'exome_genome'
    include_in_score: bool = True


@dataclass
class SegregationSummary:
    total_lod: float
    candidate_lod: float
    exome_lod: float
    points: float


def estimate_lod_dominant(n_segregations: int) -> float:
    """Z = log10(1 / 0.5^n) = n * log10(2)."""
    if n_segregations <= 0:
        return 0.0
    return n_segregations * log10(2)


def estimate_lod_recessive(
    n_affected: int,
    n_unaffected: int,
    affected_risk: float = 0.25,
) -> float:
    """Z = log10(1 / (affected_risk^(n_affected-1) * (1-affected_risk)^n_unaffected)).

    affected_risk defaults to 0.25 (classic AR, both parents heterozygous carriers).
    Use 0.5 when one parent is affected and the other is a carrier.
    """
    if n_affected <= 1:
        return 0.0
    unaffected_risk = 1.0 - affected_risk
    denom = (affected_risk ** (n_affected - 1)) * (unaffected_risk**n_unaffected)
    if denom <= 0:
        return 0.0
    return log10(1.0 / denom)


def _lod_to_points(total_lod: float, is_exome: bool) -> float:
    """Look up point value from Figure 6 table."""
    for lod_min, lod_max, candidate_pts, exome_pts in _LOD_POINT_TABLE:
        if lod_min <= total_lod < lod_max:
            return exome_pts if is_exome else candidate_pts
    return 0.0


def assign_points(lod_candidate: float, lod_exome: float) -> float:
    """Assign points per Figure 6 matrix with blended formula and dilution guard.

    When mixing candidate and exome LOD sources, the blended result is guarded
    against the case where adding candidate evidence would reduce the score
    below what exome evidence alone would have earned (SOP 'additional logic').
    """
    total_lod = lod_candidate + lod_exome
    if total_lod <= 0:
        return 0.0

    if lod_candidate == 0:
        return _lod_to_points(total_lod, is_exome=True)
    if lod_exome == 0:
        return _lod_to_points(total_lod, is_exome=False)

    candidate_pts = _lod_to_points(total_lod, is_exome=False)
    exome_pts = _lod_to_points(total_lod, is_exome=True)

    blended = (lod_candidate / total_lod) * candidate_pts + (
        lod_exome / total_lod
    ) * exome_pts

    # Guard: adding candidate LOD must not reduce below exome-only points
    exome_only_pts = _lod_to_points(lod_exome, is_exome=True)
    return max(blended, exome_only_pts)


def summarize_segregation(families: list[FamilySegregationInput]) -> SegregationSummary:
    """Sum LOD scores across included families and compute the final point score."""
    included = [f for f in families if f.include_in_score]

    candidate_lod = sum(
        f.lod_score for f in included if f.method_class == 'candidate_gene'
    )
    exome_lod = sum(f.lod_score for f in included if f.method_class == 'exome_genome')
    total_lod = candidate_lod + exome_lod

    raw_points = assign_points(candidate_lod, exome_lod)
    points = round(raw_points * 10) / 10

    return SegregationSummary(
        total_lod=total_lod,
        candidate_lod=candidate_lod,
        exome_lod=exome_lod,
        points=points,
    )
