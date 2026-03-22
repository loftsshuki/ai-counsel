"""Codebase health score computation via multi-panel deliberation."""
import json
import logging
from typing import Dict, List, Optional, Union

from adapters.base import BaseCLIAdapter
from adapters.base_http import BaseHTTPAdapter
from models.schema import StructuredFindings

logger = logging.getLogger(__name__)

# Health score categories and their weights
HEALTH_CATEGORIES = {
    "security": {"weight": 0.25, "label": "Security"},
    "architecture": {"weight": 0.20, "label": "Architecture & Maintainability"},
    "correctness": {"weight": 0.20, "label": "Correctness"},
    "performance": {"weight": 0.15, "label": "Performance"},
    "error-handling": {"weight": 0.10, "label": "Error Handling"},
    "testing": {"weight": 0.10, "label": "Test Coverage"},
}

# Severity deductions (points deducted per finding)
SEVERITY_DEDUCTIONS = {
    "critical": 20,
    "high": 10,
    "medium": 5,
    "low": 2,
    "info": 0,
}


def letter_grade(score: float) -> str:
    """Convert numeric score (0-100) to letter grade."""
    if score >= 93:
        return "A"
    elif score >= 90:
        return "A-"
    elif score >= 87:
        return "B+"
    elif score >= 83:
        return "B"
    elif score >= 80:
        return "B-"
    elif score >= 77:
        return "C+"
    elif score >= 73:
        return "C"
    elif score >= 70:
        return "C-"
    elif score >= 67:
        return "D+"
    elif score >= 60:
        return "D"
    else:
        return "F"


def compute_health_score(
    findings_list: List[Optional[StructuredFindings]],
) -> Dict:
    """
    Compute a codebase health score from structured findings.

    Starts at 100 and deducts points based on finding severity and category.
    Returns category scores, overall score, letter grade, and a plain-English report.

    Args:
        findings_list: List of StructuredFindings from multiple deliberations.
            None entries are skipped.

    Returns:
        Dict with overall_score, grade, category_scores, report, and findings_summary.
    """
    # Collect all findings across deliberations
    all_findings = []
    for sf in findings_list:
        if sf and sf.findings:
            all_findings.extend(sf.findings)

    # Score each category starting at 100
    category_scores: Dict[str, Dict] = {}
    for cat_key, cat_info in HEALTH_CATEGORIES.items():
        cat_findings = [f for f in all_findings if f.category == cat_key]
        score = 100.0
        for f in cat_findings:
            score -= SEVERITY_DEDUCTIONS.get(f.severity, 0)
        score = max(0.0, score)

        category_scores[cat_key] = {
            "label": cat_info["label"],
            "score": round(score, 1),
            "grade": letter_grade(score),
            "findings_count": len(cat_findings),
            "weight": cat_info["weight"],
        }

    # Compute weighted overall score
    overall_score = sum(
        category_scores[cat]["score"] * HEALTH_CATEGORIES[cat]["weight"]
        for cat in HEALTH_CATEGORIES
    )
    overall_score = round(overall_score, 1)

    # Count findings not in standard categories
    categorized = set(HEALTH_CATEGORIES.keys())
    other_findings = [f for f in all_findings if f.category not in categorized]

    # Deduct for "other" category findings from overall
    for f in other_findings:
        overall_score -= SEVERITY_DEDUCTIONS.get(f.severity, 0) * 0.1
    overall_score = max(0.0, round(overall_score, 1))

    # Build plain-English report
    report = _build_report(overall_score, category_scores, all_findings)

    # Findings summary
    severity_summary = {}
    for f in all_findings:
        severity_summary[f.severity] = severity_summary.get(f.severity, 0) + 1

    return {
        "overall_score": overall_score,
        "grade": letter_grade(overall_score),
        "category_scores": category_scores,
        "total_findings": len(all_findings),
        "findings_by_severity": severity_summary,
        "report": report,
    }


def _build_report(
    overall_score: float,
    category_scores: Dict[str, Dict],
    all_findings: list,
) -> str:
    """Build a plain-English health report."""
    grade = letter_grade(overall_score)
    lines = [f"Your codebase scores {overall_score}/100 ({grade})."]

    # Highlight best and worst categories
    sorted_cats = sorted(
        category_scores.items(), key=lambda x: x[1]["score"], reverse=True
    )
    if sorted_cats:
        best = sorted_cats[0]
        worst = sorted_cats[-1]
        if best[1]["score"] > worst[1]["score"]:
            lines.append(
                f"{best[1]['label']} is your strongest area ({best[1]['grade']}). "
                f"{worst[1]['label']} needs the most attention ({worst[1]['grade']})."
            )

    # Count critical/high findings
    critical_count = sum(1 for f in all_findings if f.severity == "critical")
    high_count = sum(1 for f in all_findings if f.severity == "high")

    if critical_count > 0:
        lines.append(
            f"You have {critical_count} critical issue(s) that should be fixed before launch."
        )
    if high_count > 0:
        lines.append(
            f"There are {high_count} high-priority issue(s) to address soon."
        )
    if critical_count == 0 and high_count == 0:
        lines.append("No critical or high-priority issues found.")

    return " ".join(lines)
