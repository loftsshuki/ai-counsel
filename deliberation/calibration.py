"""Model Calibration System — track per-model accuracy by domain.

Persists model performance data to SQLite, enabling accuracy tracking
over time and confidence-weighted recommendations.
"""
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional

from decision_graph.storage import DecisionGraphStorage

logger = logging.getLogger(__name__)


class ModelCalibration:
    """Tracks model accuracy by domain, persisted to SQLite."""

    def __init__(self, storage: DecisionGraphStorage):
        self.storage = storage
        self._ensure_table()

    def _ensure_table(self):
        """Create model_calibration table if it doesn't exist."""
        try:
            with self.storage.transaction() as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS model_calibration (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        model_id TEXT NOT NULL,
                        domain TEXT NOT NULL,
                        decision_id TEXT NOT NULL,
                        prediction TEXT NOT NULL,
                        outcome TEXT,
                        was_correct INTEGER,
                        confidence REAL,
                        timestamp TEXT NOT NULL
                    )
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_calibration_model
                    ON model_calibration(model_id)
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_calibration_domain
                    ON model_calibration(domain)
                """)
            logger.debug("Model calibration table initialized")
        except Exception as e:
            logger.warning(f"Failed to create model_calibration table: {e}")

    def record_prediction(
        self,
        model_id: str,
        domain: str,
        decision_id: str,
        prediction: str,
        confidence: float = 0.0,
    ):
        """
        Record a model's prediction from a deliberation.

        Called automatically after each deliberation to log what each model
        recommended. Outcome is recorded later via record_outcome().
        """
        try:
            with self.storage.transaction() as conn:
                conn.execute(
                    """INSERT INTO model_calibration
                    (model_id, domain, decision_id, prediction, confidence, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?)""",
                    (model_id, domain, decision_id, prediction, confidence,
                     datetime.now().isoformat()),
                )
            logger.debug(f"Recorded prediction for {model_id} in {domain}")
        except Exception as e:
            logger.error(f"Error recording prediction: {e}")

    def record_outcome(self, decision_id: str, outcome: str):
        """
        Record the actual outcome for a decision.

        Call this when a recommendation is implemented (correct) or rejected (incorrect).
        Updates all predictions for this decision with the outcome.
        """
        try:
            # Get all predictions for this decision
            cursor = self.storage.conn.execute(
                "SELECT id, prediction FROM model_calibration WHERE decision_id = ?",
                (decision_id,),
            )
            rows = cursor.fetchall()

            with self.storage.transaction() as conn:
                for row_id, prediction in rows:
                    # Simple correctness: did the model's prediction match the outcome?
                    was_correct = 1 if prediction.lower().strip() == outcome.lower().strip() else 0
                    conn.execute(
                        "UPDATE model_calibration SET outcome = ?, was_correct = ? WHERE id = ?",
                        (outcome, was_correct, row_id),
                    )

            logger.info(f"Recorded outcome '{outcome}' for decision {decision_id} ({len(rows)} predictions updated)")
        except Exception as e:
            logger.error(f"Error recording outcome: {e}")

    def get_model_accuracy(self, model_id: Optional[str] = None) -> List[Dict]:
        """
        Get accuracy stats per model, optionally per domain.

        Returns list of {model_id, domain, total, correct, accuracy_pct}.
        """
        try:
            query = """
                SELECT model_id, domain,
                    COUNT(*) as total,
                    SUM(CASE WHEN was_correct = 1 THEN 1 ELSE 0 END) as correct,
                    COUNT(CASE WHEN outcome IS NOT NULL THEN 1 END) as evaluated
                FROM model_calibration
                GROUP BY model_id, domain
                ORDER BY model_id, domain
            """
            params = []
            if model_id:
                query = """
                    SELECT model_id, domain,
                        COUNT(*) as total,
                        SUM(CASE WHEN was_correct = 1 THEN 1 ELSE 0 END) as correct,
                        COUNT(CASE WHEN outcome IS NOT NULL THEN 1 END) as evaluated
                    FROM model_calibration
                    WHERE model_id = ?
                    GROUP BY model_id, domain
                    ORDER BY domain
                """
                params = [model_id]

            cursor = self.storage.conn.execute(query, params)
            results = []
            for row in cursor.fetchall():
                evaluated = row[4]
                accuracy = (row[3] / evaluated * 100) if evaluated > 0 else None
                results.append({
                    "model_id": row[0],
                    "domain": row[1],
                    "total_predictions": row[2],
                    "evaluated": evaluated,
                    "correct": row[3],
                    "accuracy_pct": round(accuracy, 1) if accuracy is not None else None,
                })
            return results
        except Exception as e:
            logger.error(f"Error getting model accuracy: {e}")
            return []

    def get_model_ranking(self, domain: Optional[str] = None) -> List[Dict]:
        """
        Rank models by accuracy, optionally filtered by domain.

        Only includes models with at least 3 evaluated predictions.
        """
        try:
            if domain:
                query = """
                    SELECT model_id,
                        COUNT(*) as total,
                        SUM(CASE WHEN was_correct = 1 THEN 1 ELSE 0 END) as correct,
                        COUNT(CASE WHEN outcome IS NOT NULL THEN 1 END) as evaluated
                    FROM model_calibration
                    WHERE domain = ?
                    GROUP BY model_id
                    HAVING evaluated >= 3
                    ORDER BY (CAST(correct AS REAL) / evaluated) DESC
                """
                cursor = self.storage.conn.execute(query, [domain])
            else:
                query = """
                    SELECT model_id,
                        COUNT(*) as total,
                        SUM(CASE WHEN was_correct = 1 THEN 1 ELSE 0 END) as correct,
                        COUNT(CASE WHEN outcome IS NOT NULL THEN 1 END) as evaluated
                    FROM model_calibration
                    GROUP BY model_id
                    HAVING evaluated >= 3
                    ORDER BY (CAST(correct AS REAL) / evaluated) DESC
                """
                cursor = self.storage.conn.execute(query)

            results = []
            for row in cursor.fetchall():
                evaluated = row[3]
                accuracy = (row[2] / evaluated * 100) if evaluated > 0 else 0
                results.append({
                    "model_id": row[0],
                    "total_predictions": row[1],
                    "evaluated": evaluated,
                    "correct": row[2],
                    "accuracy_pct": round(accuracy, 1),
                })
            return results
        except Exception as e:
            logger.error(f"Error getting model ranking: {e}")
            return []
