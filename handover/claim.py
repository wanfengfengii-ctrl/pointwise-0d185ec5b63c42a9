import sqlite3
from dataclasses import dataclass

from issuance.reports import IssuedReport

from .claim_records import ClaimLedger, ClaimRecord
from .provenance import ClaimOrigin, describe_claim_origins
from .queue import ConfirmedHandoverQueue


@dataclass(frozen=True)
class ClaimResult:
    record: ClaimRecord
    report: IssuedReport
    origins: tuple[ClaimOrigin, ClaimOrigin]


def describe_claim(record: ClaimRecord, report: IssuedReport) -> ClaimResult:
    if (record.round_id, record.report_id) != (report.payload.round_id, report.report_id):
        raise RuntimeError('claim record and fixed report disagree')
    return ClaimResult(record, report, describe_claim_origins(report.payload))


def claim(db: sqlite3.Connection, round_id: str) -> ClaimResult | None:
    report = ConfirmedHandoverQueue(db).find_by_round(round_id)
    if report is None:
        return None
    record = ClaimLedger(db).record(report)
    return describe_claim(record, report)
