"""NFL Coach DNA: evidence-first coaching influence profiles for LSI."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

EvidenceStage = Literal["observed", "correlated", "persistent", "controlled", "predictive"]
Confidence = Literal["low", "medium", "high"]

PRIMARY_ROLES = ("HC", "OC", "DC", "STC", "OFF_PLAY_CALLER", "DEF_PLAY_CALLER")
SECONDARY_ROLES = ("QB", "RB", "WR", "TE", "OL", "DL", "LB", "DB")

@dataclass(frozen=True)
class CoachTendency:
    coach_id: str
    coach_name: str
    season: int
    team_id: str
    role: str
    metric: str
    situation: str
    rate: float
    baseline_rate: float
    sample_size: int
    evidence_stage: EvidenceStage
    confidence: Confidence
    affected_unit: str | None = None
    source: str | None = None
    observed_at: str | None = None

    @property
    def delta(self) -> float:
        return round(self.rate - self.baseline_rate, 4)


def confidence_from_sample(sample_size: int, seasons: int = 1) -> Confidence:
    if sample_size >= 48 and seasons >= 2:
        return "high"
    if sample_size >= 16:
        return "medium"
    return "low"


def influence_score(rate: float, baseline_rate: float, sample_size: int, seasons: int = 1) -> dict:
    """Return a transparent 0-100 fingerprint score; not a causal claim."""
    delta = rate - baseline_rate
    shrink = min(1.0, sample_size / 48.0) * min(1.0, 0.65 + 0.175 * seasons)
    score = max(0.0, min(100.0, 50.0 + (delta * 250.0 * shrink)))
    return {
        "score": round(score, 1),
        "delta": round(delta, 4),
        "sample_size": sample_size,
        "seasons": seasons,
        "confidence": confidence_from_sample(sample_size, seasons),
        "interpretation": "Measured tendency relative to baseline; correlation is not causation.",
    }


def build_fingerprint(tendencies: list[CoachTendency]) -> dict:
    if not tendencies:
        return {"status": "NO_EVIDENCE", "metrics": {}}
    grouped: dict[str, list[CoachTendency]] = {}
    for item in tendencies:
        grouped.setdefault(item.metric, []).append(item)
    metrics = {}
    for metric, rows in grouped.items():
        total_n = sum(max(1, row.sample_size) for row in rows)
        rate = sum(row.rate * max(1, row.sample_size) for row in rows) / total_n
        baseline = sum(row.baseline_rate * max(1, row.sample_size) for row in rows) / total_n
        seasons = len({row.season for row in rows})
        metrics[metric] = influence_score(rate, baseline, total_n, seasons)
    return {
        "status": "EVIDENCE_PROFILE",
        "coach_id": tendencies[0].coach_id,
        "coach_name": tendencies[0].coach_name,
        "metrics": metrics,
        "evidence": [asdict(row) | {"delta": row.delta} for row in tendencies],
    }


def compare_player_under_coach(before: float | None, under: float, after: float | None, sample_size: int) -> dict:
    references = [value for value in (before, after) if value is not None]
    if not references:
        return {"status": "INSUFFICIENT_BASELINE", "under_coach": under, "sample_size": sample_size}
    baseline = sum(references) / len(references)
    return {
        "status": "CORRELATION_SIGNAL",
        "under_coach": under,
        "comparison_baseline": round(baseline, 4),
        "difference": round(under - baseline, 4),
        "sample_size": sample_size,
        "evidence_stage": "correlated",
        "causal_claim": False,
    }
