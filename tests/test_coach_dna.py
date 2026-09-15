from app.coach_dna import CoachTendency, build_fingerprint, compare_player_under_coach, influence_score


def test_influence_score_rewards_persistent_positive_tendency():
    result = influence_score(0.62, 0.50, sample_size=64, seasons=3)
    assert result["score"] > 50
    assert result["confidence"] == "high"


def test_small_sample_is_low_confidence():
    result = influence_score(0.80, 0.50, sample_size=5, seasons=1)
    assert result["confidence"] == "low"


def test_fingerprint_aggregates_evidence():
    rows = [
        CoachTendency("c1", "Example Coach", 2025, "T1", "OC", "rb_target_rate", "neutral", .19, .14, 32, "correlated", "medium", "RB"),
        CoachTendency("c1", "Example Coach", 2026, "T1", "OC", "rb_target_rate", "neutral", .20, .14, 32, "persistent", "medium", "RB"),
    ]
    result = build_fingerprint(rows)
    assert result["status"] == "EVIDENCE_PROFILE"
    assert result["metrics"]["rb_target_rate"]["score"] > 50
    assert result["metrics"]["rb_target_rate"]["confidence"] == "high"


def test_player_coach_comparison_does_not_claim_causation():
    result = compare_player_under_coach(50.0, 62.0, 54.0, 30)
    assert result["difference"] == 10.0
    assert result["causal_claim"] is False
