"""Unit tests for Tier 2 features: Debt Tracker, Model Calibration, Chains, Regression Sentinel."""
import json
import os
import tempfile

import pytest

from decision_graph.storage import DecisionGraphStorage
from decision_graph.debt_tracker import DebtTracker, DebtItem
from deliberation.calibration import ModelCalibration
from models.schema import (
    DeliberateRequest, DeliberationResult, Finding, Participant,
    StructuredFindings, Summary,
)


@pytest.fixture
def storage():
    """Create in-memory storage for testing."""
    s = DecisionGraphStorage(db_path=":memory:")
    yield s
    s.close()


class TestDebtTracker:
    """Tests for the Architecture Debt Tracker."""

    def test_store_new_finding(self, storage):
        tracker = DebtTracker(storage)
        findings = [
            Finding(severity="high", category="security", description="Missing input validation on login form"),
        ]
        items = tracker.store_findings("decision-1", findings)
        assert len(items) == 1
        assert items[0].severity == "high"
        assert items[0].status == "open"
        assert items[0].recurrence_count == 1

    def test_regression_detection(self, storage):
        """Storing a similar finding twice should trigger regression."""
        tracker = DebtTracker(storage)

        # First time
        findings1 = [
            Finding(severity="high", category="security", description="Missing input validation on login form"),
        ]
        items1 = tracker.store_findings("decision-1", findings1)
        assert items1[0].status == "open"

        # Second time — similar description, same category
        findings2 = [
            Finding(severity="high", category="security", description="Missing input validation on login form endpoint"),
        ]
        items2 = tracker.store_findings("decision-2", findings2)
        assert items2[0].status == "recurring"
        assert items2[0].recurrence_count == 2

    def test_different_categories_not_regression(self, storage):
        tracker = DebtTracker(storage)

        findings1 = [
            Finding(severity="high", category="security", description="Missing validation"),
        ]
        findings2 = [
            Finding(severity="high", category="performance", description="Missing caching"),
        ]
        tracker.store_findings("d-1", findings1)
        items2 = tracker.store_findings("d-2", findings2)
        # Different category = not a regression
        assert items2[0].status == "open"

    def test_get_open_items(self, storage):
        tracker = DebtTracker(storage)
        findings = [
            Finding(severity="critical", category="security", description="Auth bypass"),
            Finding(severity="low", category="other", description="Minor style issue"),
        ]
        tracker.store_findings("d-1", findings)
        items = tracker.get_open_items()
        assert len(items) == 2
        # Critical should be first (sorted by severity)
        assert items[0]["severity"] == "critical"

    def test_get_open_items_filtered(self, storage):
        tracker = DebtTracker(storage)
        findings = [
            Finding(severity="high", category="security", description="Issue A"),
            Finding(severity="high", category="performance", description="Issue B"),
        ]
        tracker.store_findings("d-1", findings)
        security_items = tracker.get_open_items(category="security")
        assert len(security_items) == 1

    def test_resolve_item(self, storage):
        tracker = DebtTracker(storage)
        findings = [Finding(severity="high", category="security", description="Fix me")]
        items = tracker.store_findings("d-1", findings)
        item_id = items[0].id

        assert tracker.resolve_item(item_id)
        open_items = tracker.get_open_items()
        assert len(open_items) == 0

    def test_get_regressions(self, storage):
        tracker = DebtTracker(storage)

        # Create a recurring issue
        for i in range(3):
            findings = [
                Finding(severity="high", category="security", description="Missing input validation"),
            ]
            tracker.store_findings(f"d-{i}", findings)

        regressions = tracker.get_regressions(min_count=2)
        assert len(regressions) >= 1
        assert regressions[0]["recurrence_count"] >= 2

    def test_get_summary(self, storage):
        tracker = DebtTracker(storage)
        findings = [
            Finding(severity="critical", category="security", description="Critical issue"),
            Finding(severity="low", category="other", description="Minor issue"),
        ]
        tracker.store_findings("d-1", findings)
        summary = tracker.get_summary()
        assert summary["total_items"] == 2
        assert summary["open"] == 2
        assert summary["critical_open"] == 1


class TestModelCalibration:
    """Tests for the Model Calibration System."""

    def test_record_prediction(self, storage):
        cal = ModelCalibration(storage)
        cal.record_prediction(
            model_id="opus@claude",
            domain="security",
            decision_id="d-1",
            prediction="REQUEST_CHANGES",
            confidence=0.85,
        )
        accuracy = cal.get_model_accuracy("opus@claude")
        assert len(accuracy) == 1
        assert accuracy[0]["total_predictions"] == 1
        assert accuracy[0]["domain"] == "security"

    def test_record_outcome(self, storage):
        cal = ModelCalibration(storage)
        cal.record_prediction("opus@claude", "security", "d-1", "REQUEST_CHANGES", 0.9)
        cal.record_prediction("grok@openrouter", "security", "d-1", "APPROVE", 0.7)

        # Outcome matches opus's prediction
        cal.record_outcome("d-1", "REQUEST_CHANGES")

        accuracy = cal.get_model_accuracy()
        opus = [a for a in accuracy if a["model_id"] == "opus@claude"][0]
        grok = [a for a in accuracy if a["model_id"] == "grok@openrouter"][0]

        assert opus["correct"] == 1
        assert opus["accuracy_pct"] == 100.0
        assert grok["correct"] == 0
        assert grok["accuracy_pct"] == 0.0

    def test_model_ranking(self, storage):
        cal = ModelCalibration(storage)

        # Record multiple predictions with outcomes
        for i in range(5):
            cal.record_prediction("model-a", "security", f"d-{i}", "YES")
            cal.record_prediction("model-b", "security", f"d-{i}", "NO")
            cal.record_outcome(f"d-{i}", "YES")  # model-a is always right

        ranking = cal.get_model_ranking("security")
        assert len(ranking) == 2
        assert ranking[0]["model_id"] == "model-a"  # Higher accuracy first
        assert ranking[0]["accuracy_pct"] == 100.0

    def test_empty_calibration(self, storage):
        cal = ModelCalibration(storage)
        assert cal.get_model_accuracy() == []
        assert cal.get_model_ranking() == []


class TestDeliberationChains:
    """Tests for deliberation chain schema fields."""

    def test_chain_fields_optional(self):
        """Chain fields should be optional (backward compat)."""
        request = DeliberateRequest(
            question="Test question for chain test",
            participants=[
                Participant(cli="claude", model="sonnet"),
                Participant(cli="openrouter", model="x-ai/grok-4"),
            ],
            working_directory="/tmp",
        )
        assert request.chain_id is None
        assert request.chain_step is None

    def test_chain_fields_set(self):
        request = DeliberateRequest(
            question="Step 2 of chain review",
            participants=[
                Participant(cli="claude", model="sonnet"),
                Participant(cli="openrouter", model="x-ai/grok-4"),
            ],
            working_directory="/tmp",
            chain_id="chain-abc-123",
            chain_step=2,
        )
        assert request.chain_id == "chain-abc-123"
        assert request.chain_step == 2

    def test_chain_step_must_be_positive(self):
        with pytest.raises(Exception):
            DeliberateRequest(
                question="Invalid chain step test",
                participants=[
                    Participant(cli="claude", model="sonnet"),
                    Participant(cli="openrouter", model="x-ai/grok-4"),
                ],
                working_directory="/tmp",
                chain_id="chain-1",
                chain_step=0,  # Must be >= 1
            )

    def test_result_has_chain_fields(self):
        result = DeliberationResult(
            status="complete",
            mode="quick",
            rounds_completed=1,
            participants=["sonnet@claude"],
            summary=Summary(
                consensus="Test", key_agreements=["a"],
                key_disagreements=[], final_recommendation="b",
            ),
            transcript_path="test.md",
            full_debate=[],
            chain_id="chain-1",
            chain_step=2,
        )
        assert result.chain_id == "chain-1"
        assert result.chain_step == 2
