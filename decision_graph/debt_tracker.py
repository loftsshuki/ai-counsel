"""Architecture Debt Tracker — persistent ledger of findings from deliberations.

Stores structured findings in the decision graph SQLite database, enables
querying by severity/category/status, and detects recurring issues (Regression Sentinel).
"""
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field

from decision_graph.storage import DecisionGraphStorage

logger = logging.getLogger(__name__)


class DebtItem(BaseModel):
    """A tracked finding in the debt ledger."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    decision_id: str = Field(..., description="UUID of the deliberation that found this")
    severity: str = Field(..., description="critical, high, medium, low, info")
    category: str = Field(..., description="security, performance, correctness, etc.")
    description: str = Field(..., description="Plain-English description")
    file: Optional[str] = Field(default=None)
    suggested_fix: Optional[str] = Field(default=None)
    flagged_by: List[str] = Field(default_factory=list)
    status: str = Field(default="open", description="open, resolved, wont_fix, recurring")
    recurrence_count: int = Field(default=1, description="How many times this issue was flagged")
    first_seen: str = Field(default_factory=lambda: datetime.now().isoformat())
    last_seen: str = Field(default_factory=lambda: datetime.now().isoformat())


class DebtTracker:
    """Manages the debt ledger in SQLite."""

    def __init__(self, storage: DecisionGraphStorage):
        self.storage = storage
        self._ensure_table()

    def _ensure_table(self):
        """Create debt_items table if it doesn't exist."""
        try:
            with self.storage.transaction() as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS debt_items (
                        id TEXT PRIMARY KEY,
                        decision_id TEXT NOT NULL,
                        severity TEXT NOT NULL,
                        category TEXT NOT NULL,
                        description TEXT NOT NULL,
                        file TEXT,
                        suggested_fix TEXT,
                        flagged_by TEXT,
                        status TEXT NOT NULL DEFAULT 'open',
                        recurrence_count INTEGER DEFAULT 1,
                        first_seen TEXT NOT NULL,
                        last_seen TEXT NOT NULL
                    )
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_debt_severity
                    ON debt_items(severity)
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_debt_status
                    ON debt_items(status)
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_debt_category
                    ON debt_items(category)
                """)
            logger.debug("Debt tracker table initialized")
        except Exception as e:
            logger.warning(f"Failed to create debt_items table: {e}")

    def store_findings(self, decision_id: str, findings: list) -> List[DebtItem]:
        """
        Store findings from a deliberation into the debt ledger.

        Checks for similar existing findings (same category + similar description)
        and increments recurrence_count if found (Regression Sentinel).

        Args:
            decision_id: UUID of the deliberation
            findings: List of Finding objects from StructuredFindings

        Returns:
            List of DebtItem objects (new or updated)
        """
        items = []
        for finding in findings:
            # Check for existing similar finding (same category, similar description)
            existing = self._find_similar(finding.category, finding.description)

            if existing:
                # Regression detected — update existing item
                self._update_recurrence(existing["id"], decision_id)
                item = DebtItem(
                    id=existing["id"],
                    decision_id=decision_id,
                    severity=finding.severity,
                    category=finding.category,
                    description=finding.description,
                    file=finding.file,
                    suggested_fix=finding.suggested_fix,
                    flagged_by=finding.flagged_by,
                    status="recurring",
                    recurrence_count=existing["recurrence_count"] + 1,
                    first_seen=existing["first_seen"],
                    last_seen=datetime.now().isoformat(),
                )
                logger.warning(
                    f"Regression detected: '{finding.description[:60]}...' "
                    f"flagged {item.recurrence_count} times (first seen: {existing['first_seen'][:10]})"
                )
            else:
                # New finding
                item = DebtItem(
                    decision_id=decision_id,
                    severity=finding.severity,
                    category=finding.category,
                    description=finding.description,
                    file=finding.file,
                    suggested_fix=finding.suggested_fix,
                    flagged_by=finding.flagged_by,
                )
                self._insert(item)

            items.append(item)

        return items

    def get_open_items(
        self,
        severity: Optional[str] = None,
        category: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict]:
        """Query open debt items, optionally filtered."""
        query = "SELECT * FROM debt_items WHERE status IN ('open', 'recurring')"
        params = []

        if severity:
            query += " AND severity = ?"
            params.append(severity)
        if category:
            query += " AND category = ?"
            params.append(category)

        query += " ORDER BY CASE severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 WHEN 'low' THEN 3 ELSE 4 END, last_seen DESC"
        query += f" LIMIT {limit}"

        try:
            cursor = self.storage.conn.execute(query, params)
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in rows]
        except Exception as e:
            logger.error(f"Error querying debt items: {e}")
            return []

    def get_regressions(self, min_count: int = 2) -> List[Dict]:
        """Get recurring issues (Regression Sentinel)."""
        try:
            cursor = self.storage.conn.execute(
                "SELECT * FROM debt_items WHERE recurrence_count >= ? ORDER BY recurrence_count DESC",
                (min_count,),
            )
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in rows]
        except Exception as e:
            logger.error(f"Error querying regressions: {e}")
            return []

    def resolve_item(self, item_id: str) -> bool:
        """Mark a debt item as resolved."""
        try:
            with self.storage.transaction() as conn:
                conn.execute(
                    "UPDATE debt_items SET status = 'resolved' WHERE id = ?",
                    (item_id,),
                )
            return True
        except Exception as e:
            logger.error(f"Error resolving debt item: {e}")
            return False

    def get_summary(self) -> Dict:
        """Get a summary of the debt ledger."""
        try:
            cursor = self.storage.conn.execute("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN status IN ('open', 'recurring') THEN 1 ELSE 0 END) as open_count,
                    SUM(CASE WHEN status = 'resolved' THEN 1 ELSE 0 END) as resolved_count,
                    SUM(CASE WHEN status = 'recurring' THEN 1 ELSE 0 END) as recurring_count,
                    SUM(CASE WHEN severity = 'critical' AND status != 'resolved' THEN 1 ELSE 0 END) as critical_open,
                    SUM(CASE WHEN severity = 'high' AND status != 'resolved' THEN 1 ELSE 0 END) as high_open
                FROM debt_items
            """)
            row = cursor.fetchone()
            return {
                "total_items": row[0] or 0,
                "open": row[1] or 0,
                "resolved": row[2] or 0,
                "recurring": row[3] or 0,
                "critical_open": row[4] or 0,
                "high_open": row[5] or 0,
            }
        except Exception as e:
            logger.error(f"Error getting debt summary: {e}")
            return {"total_items": 0, "open": 0, "resolved": 0, "recurring": 0, "critical_open": 0, "high_open": 0}

    def _find_similar(self, category: str, description: str) -> Optional[Dict]:
        """Find an existing open finding with the same category and similar description."""
        try:
            # Simple match: same category and description contains key words
            # For a more sophisticated match, we could use semantic similarity
            cursor = self.storage.conn.execute(
                "SELECT * FROM debt_items WHERE category = ? AND status != 'resolved' ORDER BY last_seen DESC",
                (category,),
            )
            rows = cursor.fetchall()
            if not rows:
                return None

            columns = [desc[0] for desc in cursor.description]
            desc_words = set(description.lower().split())

            for row in rows:
                row_dict = dict(zip(columns, row))
                existing_words = set(row_dict["description"].lower().split())
                # If >50% word overlap, consider it the same issue
                overlap = len(desc_words & existing_words)
                total = len(desc_words | existing_words)
                if total > 0 and overlap / total > 0.5:
                    return row_dict

            return None
        except Exception as e:
            logger.error(f"Error finding similar debt item: {e}")
            return None

    def _insert(self, item: DebtItem):
        """Insert a new debt item."""
        try:
            with self.storage.transaction() as conn:
                conn.execute(
                    """INSERT INTO debt_items
                    (id, decision_id, severity, category, description, file,
                     suggested_fix, flagged_by, status, recurrence_count, first_seen, last_seen)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        item.id, item.decision_id, item.severity, item.category,
                        item.description, item.file, item.suggested_fix,
                        json.dumps(item.flagged_by), item.status,
                        item.recurrence_count, item.first_seen, item.last_seen,
                    ),
                )
        except Exception as e:
            logger.error(f"Error inserting debt item: {e}")

    def _update_recurrence(self, item_id: str, decision_id: str):
        """Update an existing item's recurrence count and status."""
        try:
            with self.storage.transaction() as conn:
                conn.execute(
                    """UPDATE debt_items
                    SET recurrence_count = recurrence_count + 1,
                        status = 'recurring',
                        last_seen = ?,
                        decision_id = ?
                    WHERE id = ?""",
                    (datetime.now().isoformat(), decision_id, item_id),
                )
        except Exception as e:
            logger.error(f"Error updating recurrence: {e}")
