"""
Tests for detect_algorithm_class and the tool-aware rating changes it drives.
"""

from __future__ import annotations

import pytest

from skydiscover.extras.evolve_analyzer.ingestion.checkpoint_adapter import detect_algorithm_class
from skydiscover.extras.evolve_analyzer.report_synthesizer import (
    _build_rating_context,
    _rate_by_thresholds,
    _DEFAULT_REGRESSION_THRESHOLDS,
    _DEFAULT_EXPLORATION_THRESHOLDS,
)


# ---------------------------------------------------------------------------
# detect_algorithm_class
# ---------------------------------------------------------------------------

class TestDetectAlgorithmClass:
    def test_skydiscover_is_population_evolutionary(self):
        assert detect_algorithm_class("skydiscover", []) == "population_evolutionary"

    def test_openevolve_is_population_evolutionary(self):
        assert detect_algorithm_class("openevolve", []) == "population_evolutionary"

    def test_shinkaevolve_is_population_evolutionary(self):
        assert detect_algorithm_class("shinkaevolve", []) == "population_evolutionary"

    def test_source_case_insensitive(self):
        assert detect_algorithm_class("SkyDiscover", []) == "population_evolutionary"
        assert detect_algorithm_class("OPENEVOLVE", []) == "population_evolutionary"

    def test_jsonl_with_island_id_is_population_evolutionary(self):
        records = [{"iteration": 0, "child_score": 0.5, "island_id": "island_0"}]
        assert detect_algorithm_class("jsonl", records) == "population_evolutionary"

    def test_jsonl_island_id_none_does_not_trigger(self):
        records = [{"iteration": 0, "child_score": 0.5, "island_id": None}]
        # None island_id should NOT classify as population_evolutionary
        result = detect_algorithm_class("jsonl", records)
        assert result != "population_evolutionary"

    def test_jsonl_with_numeric_parameters_is_bayesian_optimization(self):
        records = [
            {"iteration": i, "child_score": 0.5, "parameters": {"lr": 0.01, "depth": 3}}
            for i in range(5)
        ]
        assert detect_algorithm_class("jsonl", records) == "bayesian_optimization"

    def test_jsonl_with_only_string_parameters_is_not_bayesian_optimization(self):
        records = [
            {"iteration": 0, "child_score": 0.5, "parameters": {"mutation_type": "diff"}}
        ]
        result = detect_algorithm_class("jsonl", records)
        assert result == "serial_refinement"

    def test_jsonl_minimal_records_is_serial_refinement(self):
        records = [{"iteration": i, "child_score": float(i) * 0.1} for i in range(5)]
        assert detect_algorithm_class("jsonl", records) == "serial_refinement"

    def test_jsonl_empty_records_is_serial_refinement(self):
        assert detect_algorithm_class("jsonl", []) == "serial_refinement"

    def test_island_id_takes_priority_over_numeric_parameters(self):
        # A record with both island_id and numeric parameters → population_evolutionary
        records = [
            {
                "iteration": 0,
                "child_score": 0.5,
                "island_id": "island_1",
                "parameters": {"lr": 0.01},
            }
        ]
        assert detect_algorithm_class("jsonl", records) == "population_evolutionary"

    def test_only_first_ten_records_inspected(self):
        # First 10 records have no island_id; record 11 does — should still be serial
        records = [{"iteration": i, "child_score": 0.5} for i in range(10)]
        records.append({"iteration": 10, "child_score": 0.5, "island_id": "island_0"})
        assert detect_algorithm_class("jsonl", records) == "serial_refinement"


# ---------------------------------------------------------------------------
# _rate_by_thresholds
# ---------------------------------------------------------------------------

class TestRateByThresholds:
    thresholds = [0.05, 0.15, 0.30, 0.50]  # default regression thresholds

    def test_lower_is_better_rating_5(self):
        assert _rate_by_thresholds(0.04, self.thresholds, lower_is_better=True) == 5

    def test_lower_is_better_boundary_at_t5(self):
        assert _rate_by_thresholds(0.05, self.thresholds, lower_is_better=True) == 4

    def test_lower_is_better_rating_4(self):
        assert _rate_by_thresholds(0.10, self.thresholds, lower_is_better=True) == 4

    def test_lower_is_better_rating_3(self):
        assert _rate_by_thresholds(0.20, self.thresholds, lower_is_better=True) == 3

    def test_lower_is_better_rating_2(self):
        assert _rate_by_thresholds(0.40, self.thresholds, lower_is_better=True) == 2

    def test_lower_is_better_rating_1(self):
        assert _rate_by_thresholds(0.60, self.thresholds, lower_is_better=True) == 1

    def test_higher_is_better_rating_5(self):
        thresholds = [0.70, 0.50, 0.30, 0.10]  # exploration thresholds
        assert _rate_by_thresholds(0.75, thresholds, lower_is_better=False) == 5

    def test_higher_is_better_boundary_at_t5(self):
        thresholds = [0.70, 0.50, 0.30, 0.10]
        assert _rate_by_thresholds(0.70, thresholds, lower_is_better=False) == 4

    def test_higher_is_better_rating_1(self):
        thresholds = [0.70, 0.50, 0.30, 0.10]
        assert _rate_by_thresholds(0.05, thresholds, lower_is_better=False) == 1


# ---------------------------------------------------------------------------
# _build_rating_context
# ---------------------------------------------------------------------------

class TestBuildRatingContext:
    def test_population_evolutionary_uses_wider_regression_thresholds(self):
        config = {
            "algorithm_classes": {
                "population_evolutionary": {
                    "regression_frequency_thresholds": [0.15, 0.30, 0.50, 0.70],
                    "exploration_sdi_thresholds": [0.70, 0.50, 0.30, 0.10],
                }
            }
        }
        ctx = _build_rating_context("population_evolutionary", config)
        assert ctx["regression_frequency_thresholds"] == [0.15, 0.30, 0.50, 0.70]
        assert ctx["algorithm_class"] == "population_evolutionary"

    def test_serial_refinement_uses_tighter_regression_thresholds(self):
        config = {
            "algorithm_classes": {
                "serial_refinement": {
                    "regression_frequency_thresholds": [0.03, 0.10, 0.20, 0.35],
                    "exploration_sdi_thresholds": [0.40, 0.25, 0.10, 0.05],
                }
            }
        }
        ctx = _build_rating_context("serial_refinement", config)
        assert ctx["regression_frequency_thresholds"][0] < _DEFAULT_REGRESSION_THRESHOLDS[0]

    def test_unknown_class_falls_back_to_defaults(self):
        ctx = _build_rating_context("unknown_class", {})
        assert ctx["regression_frequency_thresholds"] == _DEFAULT_REGRESSION_THRESHOLDS
        assert ctx["exploration_sdi_thresholds"] == _DEFAULT_EXPLORATION_THRESHOLDS

    def test_empty_config_falls_back_to_defaults(self):
        ctx = _build_rating_context("population_evolutionary", {})
        assert ctx["regression_frequency_thresholds"] == _DEFAULT_REGRESSION_THRESHOLDS

    def test_partial_config_falls_back_per_key(self):
        config = {
            "algorithm_classes": {
                "population_evolutionary": {
                    "regression_frequency_thresholds": [0.15, 0.30, 0.50, 0.70],
                    # no exploration_sdi_thresholds
                }
            }
        }
        ctx = _build_rating_context("population_evolutionary", config)
        assert ctx["regression_frequency_thresholds"] == [0.15, 0.30, 0.50, 0.70]
        assert ctx["exploration_sdi_thresholds"] == _DEFAULT_EXPLORATION_THRESHOLDS


# ---------------------------------------------------------------------------
# Tool-aware rating: same metric, different class → different rating
# ---------------------------------------------------------------------------

class TestToolAwareRatingDiffers:
    """Regression frequency of 0.20 should rate differently across algorithm classes."""

    freq = 0.20  # Fair for default, but should be Good for population_evolutionary

    def _regression_rating(self, algorithm_class: str, config: dict) -> int:
        ctx = _build_rating_context(algorithm_class, config)
        return _rate_by_thresholds(
            self.freq,
            ctx["regression_frequency_thresholds"],
            lower_is_better=True,
        )

    def test_population_evolutionary_rates_higher_for_moderate_regression(self):
        config = {
            "algorithm_classes": {
                "population_evolutionary": {
                    "regression_frequency_thresholds": [0.15, 0.30, 0.50, 0.70],
                    "exploration_sdi_thresholds": [0.70, 0.50, 0.30, 0.10],
                },
                "serial_refinement": {
                    "regression_frequency_thresholds": [0.03, 0.10, 0.20, 0.35],
                    "exploration_sdi_thresholds": [0.40, 0.25, 0.10, 0.05],
                },
            }
        }
        pop_rating = self._regression_rating("population_evolutionary", config)
        serial_rating = self._regression_rating("serial_refinement", config)
        assert pop_rating > serial_rating, (
            f"Expected population_evolutionary ({pop_rating}) > serial_refinement ({serial_rating})"
        )

    def test_exploration_sdi_rates_higher_for_serial_with_relaxed_thresholds(self):
        sdi = 0.30  # Poor for population_evolutionary, Fair for serial_refinement
        config = {
            "algorithm_classes": {
                "population_evolutionary": {
                    "regression_frequency_thresholds": [0.15, 0.30, 0.50, 0.70],
                    "exploration_sdi_thresholds": [0.70, 0.50, 0.30, 0.10],
                },
                "serial_refinement": {
                    "regression_frequency_thresholds": [0.03, 0.10, 0.20, 0.35],
                    "exploration_sdi_thresholds": [0.40, 0.25, 0.10, 0.05],
                },
            }
        }
        pop_ctx = _build_rating_context("population_evolutionary", config)
        serial_ctx = _build_rating_context("serial_refinement", config)
        pop_rating = _rate_by_thresholds(sdi, pop_ctx["exploration_sdi_thresholds"], lower_is_better=False)
        serial_rating = _rate_by_thresholds(sdi, serial_ctx["exploration_sdi_thresholds"], lower_is_better=False)
        assert serial_rating > pop_rating, (
            f"Expected serial_refinement ({serial_rating}) > population_evolutionary ({pop_rating}) for SDI={sdi}"
        )
