"""Extract structured findings from deliberation responses."""
import json
import logging
import re
from typing import Dict, List, Optional, Union

from adapters.base import BaseCLIAdapter
from adapters.base_http import BaseHTTPAdapter
from models.schema import Finding, RoundResponse, StructuredFindings

logger = logging.getLogger(__name__)


class FindingsExtractor:
    """
    Extract structured findings from deliberation model responses.

    Uses an AI model to parse unstructured review text into categorized,
    severity-rated findings with file references and suggested fixes.
    """

    def __init__(self, adapter: Union[BaseCLIAdapter, BaseHTTPAdapter], model: str):
        self.adapter = adapter
        self.model = model

    async def extract_findings(
        self, question: str, responses: List[RoundResponse]
    ) -> Optional[StructuredFindings]:
        """
        Extract structured findings from deliberation responses.

        Uses the final round's responses (most refined) to generate findings.
        Falls back to all responses if final round has issues.
        """
        # Use final round responses (most refined after debate)
        final_round = max(r.round for r in responses) if responses else 0
        final_responses = [r for r in responses if r.round == final_round]

        if not final_responses:
            return None

        # Build extraction prompt
        debate_text = self._format_responses(question, final_responses)
        prompt = self._create_extraction_prompt(debate_text)

        try:
            raw_output = await self.adapter.invoke(
                prompt=prompt, model=self.model, context=None
            )
            return self._parse_findings(raw_output, final_responses)
        except Exception as e:
            logger.warning(f"Findings extraction failed: {e}")
            return None

    def _format_responses(self, question: str, responses: List[RoundResponse]) -> str:
        """Format responses for the extraction prompt."""
        lines = [f"Question: {question}\n"]
        for resp in responses:
            lines.append(f"\n{resp.participant}:")
            lines.append(resp.response)
        return "\n".join(lines)

    def _create_extraction_prompt(self, debate_text: str) -> str:
        """Create the prompt that asks the model to extract structured findings."""
        return f"""You are a code review findings extractor. Analyze the following review and extract structured findings.

{debate_text}

Respond with ONLY valid JSON in this exact format (no markdown, no explanation, just JSON):

{{
  "verdict": "APPROVE" or "APPROVE_WITH_NOTES" or "REQUEST_CHANGES" or "NEEDS_DISCUSSION",
  "risk_level": "low" or "medium" or "high" or "critical",
  "findings": [
    {{
      "severity": "critical" or "high" or "medium" or "low" or "info",
      "category": "security" or "performance" or "correctness" or "architecture" or "maintainability" or "error-handling" or "testing" or "other",
      "description": "Plain-English description of the issue",
      "file": "path/to/file.py or null if not specific to a file",
      "line": null,
      "suggested_fix": "What to do about it, or null"
    }}
  ]
}}

Rules:
- Extract EVERY distinct issue mentioned by ANY reviewer
- Use plain English descriptions (no jargon)
- If multiple reviewers flagged the same issue, combine into one finding
- If no real issues found, return verdict "APPROVE" with empty findings list
- Be conservative with severity: "critical" = blocks launch, "high" = fix soon, "medium" = should fix, "low" = nice to have, "info" = observation"""

    def _parse_findings(
        self, raw_output: str, responses: List[RoundResponse]
    ) -> Optional[StructuredFindings]:
        """Parse the model's JSON output into StructuredFindings."""
        try:
            # Extract JSON from response (model might wrap in markdown code blocks)
            json_text = raw_output.strip()
            if "```json" in json_text:
                json_text = json_text.split("```json")[1].split("```")[0].strip()
            elif "```" in json_text:
                json_text = json_text.split("```")[1].split("```")[0].strip()

            data = json.loads(json_text)

            # Build participant list for flagged_by
            participant_names = [r.participant for r in responses]

            # Parse findings
            findings = []
            for f in data.get("findings", []):
                finding = Finding(
                    severity=f.get("severity", "medium"),
                    category=f.get("category", "other"),
                    description=f.get("description", ""),
                    file=f.get("file"),
                    line=f.get("line"),
                    suggested_fix=f.get("suggested_fix"),
                    flagged_by=participant_names,  # All final-round participants
                )
                findings.append(finding)

            # Count by severity
            severity_counts: Dict[str, int] = {}
            for f in findings:
                severity_counts[f.severity] = severity_counts.get(f.severity, 0) + 1

            return StructuredFindings(
                verdict=data.get("verdict", "NEEDS_DISCUSSION"),
                risk_level=data.get("risk_level", "medium"),
                findings=findings,
                findings_by_severity=severity_counts,
            )

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.warning(f"Failed to parse findings JSON: {e}")
            return None
