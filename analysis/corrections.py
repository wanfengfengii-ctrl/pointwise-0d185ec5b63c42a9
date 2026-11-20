import sqlite3
from dataclasses import dataclass

from .qualification import QualificationStore, confirmation_unavailable
from .snapshots import FrozenAnalysis, inspect_revision


@dataclass(frozen=True)
class CorrectionResult:
    status: str
    snapshot: FrozenAnalysis | None


def correct_revision(
    db: sqlite3.Connection | None, round_id: str, revision_id: str
) -> CorrectionResult:
    if db is None:
        return CorrectionResult('pending', None)
    snapshot = None
    try:
        snapshot = inspect_revision(db, round_id, revision_id)
        status = QualificationStore(db).apply_correction(snapshot)
    except sqlite3.OperationalError as error:
        if not confirmation_unavailable(error):
            raise
        return CorrectionResult('pending', snapshot)
    return CorrectionResult(status, snapshot)
