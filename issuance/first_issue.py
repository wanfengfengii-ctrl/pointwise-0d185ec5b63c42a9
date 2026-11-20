import sqlite3

from analysis.qualification import QualificationStore, confirmation_unavailable
from analysis.snapshots import inspect_revision

from .reconcile import Progress, SignResult, reconcile_request
from .report_payload import pack_report_payload
from .reports import ReportStore
from .requests import RequestLedger


class _ProgressError(Exception):
    def __init__(self, original: sqlite3.OperationalError):
        self.original = original


def sign(
    source: sqlite3.Connection | None,
    db: sqlite3.Connection,
    round_id: str,
    revision_id: str,
    request_id: str,
    *,
    progress: Progress | None = None,
) -> SignResult:
    def notify(stage: str, detail: object) -> bool | None:
        if progress is None:
            return None
        try:
            return progress(stage, detail)
        except sqlite3.OperationalError as error:
            raise _ProgressError(error) from error

    ledger = RequestLedger(db)
    try:
        request = ledger.bind(request_id, round_id, revision_id)
        if request.status == 'pending' and source is not None:
            if request.candidate is None and ReportStore(db).find_confirmed(round_id) is None:
                snapshot = inspect_revision(source, round_id, revision_id)
                if QualificationStore(source).current(round_id) == revision_id:
                    request = ledger.save_candidate(request, pack_report_payload(snapshot))
            if request.status == 'pending' and request.candidate is not None and progress is not None:
                observed = QualificationStore(source).current(round_id)
                if notify('candidate_saved', observed) is False:
                    return SignResult('pending')
        outcome = reconcile_request(source, db, request, progress=notify if progress is not None else None)
    except _ProgressError as error:
        raise error.original from None
    except sqlite3.OperationalError as error:
        if not confirmation_unavailable(error):
            raise
        return SignResult('pending')
    if progress is not None and outcome.report is not None:
        progress('confirmed', outcome.report)
    return outcome
