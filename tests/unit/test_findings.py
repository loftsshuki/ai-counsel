"""Unit tests for structured findings and health score."""
import json
import pytest
from unittest.mock import AsyncMock

from deliberation.findings import FindingsExtractor
from deliberation.health_score import compute_health_score, letter_grade, SEVERITY_DEDUCTIONS
from models.schema import Finding, StructuredFindings, RoundResponse


class TestFindingSchema:
    """Tests for Finding and StructuredFindings models."""

    def test_finding_creation(self):
        f = Finding(
            severity="high",
            category="security",
            description="SQL injection in login form",
            file="auth/login.py",
            line=42,
            suggested_fix="Use parameterized queries",
            flagged_by=["claude", "grok"],
        )
        assert f.severity == "high"
        assert f.category == "security"
        assert "SQL injection" in f.description

    def test_finding_minimal(self):
        """Finding with only required fields."""
        f = Finding(severity="low", category="other", description="Minor style issue")
        assert f.file is None
        assert f.line is None
        assert f.suggested_fix is None
        assert f.flagged_by == []

    def test_structured_findings(self):
        sf = StructuredFindings(
            verdict="REQUEST_CHANGES",
            risk_level="high",
            findings=[
                Finding(severity="critical", category="security", description="Auth bypass"),
                Finding(severity="medium", category="performance", description="Slow query"),
            ],
            findings_by_severity={"critical": 1, "medium": 1},
        )
        assert sf.verdict == "REQUEST_CHANGES"
        assert len(sf.findings) == 2

    def test_structured_findings_approve(self):
        sf = StructuredFindings(
            verdict="APPROVE",
            risk_level="low",
            findings=[],
            findings_by_severity={},
        )
        assert sf.verdict == "APPROVE"
        assert len(sf.findings) == 0


class TestFindingsExtractor:
    """Tests for FindingsExtractor."""

    def test_extraction_prompt_requests_json(self):
        from adapters.base import BaseCLIAdapter

        class FakeAdapter(BaseCLIAdapter):
            def parse_output(self, raw): return raw

        adapter = FakeAdapter(command="fake", args=[])
        extractor = FindingsExtractor(adapter, "test")
        prompt = extractor._create_extraction_prompt("Test code review")
        assert "JSON" in prompt
        assert "verdict" in prompt
        assert "severity" in prompt

    def test_parse_findings_valid_json(self):
        from adapters.base import BaseCLIAdapter

        class FakeAdapter(BaseCLIAdapter):
            def parse_output(self, raw): return raw

        adapter = FakeAdapter(command="fake", args=[])
        extractor = FindingsExtractor(adapter, "test")

        responses = [
            RoundResponse(round=1, participant="test@cli", response="review", timestamp="2024-01-01"),
        ]

        raw = json.dumps({
            "verdict": "APPROVE_WITH_NOTES",
            "risk_level": "medium",
            "findings": [
                {
                    "severity": "high",
                    "category": "security",
                    "description": "Missing input validation",
                    "file": "api/routes.py",
                    "suggested_fix": "Add validation middleware",
                }
            ],
        })

        result = extractor._parse_findings(raw, responses)
        assert result is not None
        assert result.verdict == "APPROVE_WITH_NOTES"
        assert len(result.findings) == 1
        assert result.findings[0].severity == "high"
        assert result.findings_by_severity == {"high": 1}

    def test_parse_findings_with_markdown_wrapper(self):
        from adapters.base import BaseCLIAdapter

        class FakeAdapter(BaseCLIAdapter):
            def parse_output(self, raw): return raw

        adapter = FakeAdapter(command="fake", args=[])
        extractor = FindingsExtractor(adapter, "test")

        responses = [
            RoundResponse(round=1, participant="test@cli", response="review", timestamp="2024-01-01"),
        ]

        raw = '```json\n{"verdict": "APPROVE", "risk_level": "low", "findings": []}\n```'

        result = extractor._parse_findings(raw, responses)
        assert result is not None
        assert result.verdict == "APPROVE"

    def test_parse_findings_invalid_json(self):
        from adapters.base import BaseCLIAdapter

        class FakeAdapter(BaseCLIAdapter):
            def parse_output(self, raw): return raw

        adapter = FakeAdapter(command="fake", args=[])
        extractor = FindingsExtractor(adapter, "test")

        result = extractor._parse_findings("not json at all", [])
        assert result is None


class TestHealthScore:
    """Tests for health score computation."""

    def test_perfect_score_no_findings(self):
        result = compute_health_score([])
        assert result["overall_score"] == 100.0
        assert result["grade"] == "A"
        assert result["total_findings"] == 0

    def test_score_deduction_for_critical(self):
        sf = StructuredFindings(
            verdict="REQUEST_CHANGES",
            risk_level="critical",
            findings=[
                Finding(severity="critical", category="security", description="Auth bypass"),
            ],
            findings_by_severity={"critical": 1},
        )
        result = compute_health_score([sf])
        # Security starts at 100, deducts 20 for critical = 80
        assert result["category_scores"]["security"]["score"] == 80.0
        assert result["overall_score"] < 100.0

    def test_multiple_findings_compound(self):
        sf = StructuredFindings(
            verdict="REQUEST_CHANGES",
            risk_level="high",
            findings=[
                Finding(severity="critical", category="security", description="Issue 1"),
                Finding(severity="high", category="security", description="Issue 2"),
                Finding(severity="medium", category="performance", description="Issue 3"),
            ],
            findings_by_severity={"critical": 1, "high": 1, "medium": 1},
        )
        result = compute_health_score([sf])
        # Security: 100 - 20 (critical) - 10 (high) = 70
        assert result["category_scores"]["security"]["score"] == 70.0
        # Performance: 100 - 5 (medium) = 95
        assert result["category_scores"]["performance"]["score"] == 95.0

    def test_none_findings_skipped(self):
        result = compute_health_score([None, None])
        assert result["overall_score"] == 100.0

    def test_report_is_plain_english(self):
        sf = StructuredFindings(
            verdict="APPROVE_WITH_NOTES",
            risk_level="medium",
            findings=[
                Finding(severity="high", category="security", description="Issue"),
            ],
            findings_by_severity={"high": 1},
        )
        result = compute_health_score([sf])
        assert "report" in result
        assert len(result["report"]) > 20
        assert "/100" in result["report"]

    def test_letter_grades(self):
        assert letter_grade(95) == "A"
        assert letter_grade(85) == "B"
        assert letter_grade(75) == "C"
        assert letter_grade(65) == "D"
        assert letter_grade(50) == "F"
