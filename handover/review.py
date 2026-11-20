import sqlite3

from .claim import ClaimResult, describe_claim
from .claim_records import ClaimLedger
from .queue import ConfirmedHandoverQueue


def review_claim(db: sqlite3.Connection, round_id: str, report_id: str) -> ClaimResult | None:
    record = ClaimLedger(db).find(round_id)
    if record is None or record.report_id != report_id:
        return None
    report = ConfirmedHandoverQueue(db).find_by_round(round_id)
    if report is None:
        raise RuntimeError('claimed report is missing from confirmed handover')
    return describe_claim(record, report)
