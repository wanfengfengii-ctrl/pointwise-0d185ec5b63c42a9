import sqlite3
from collections.abc import Callable
from dataclasses import dataclass

from analysis.qualification import QualificationDecision, QualificationStore

from .reports import IssuedReport, ReportStore
from .requests import IssueRequest, RequestLedger

Progress = Callable[[str, object], bool | None]


@dataclass(frozen=True)
class SignResult:
    status: str
    report: IssuedReport | None = None


def _read_terminal(reports: ReportStore, request: IssueRequest) -> SignResult | None:
    if request.status == 'pending':
        return None
    if request.status == 'stale':
        return SignResult('stale')
    report = reports.find_confirmed(request.round_id, request.revision_id)
    if (report is None or report.report_id != request.report_id
            or report.request_id != request.request_id
            or report.payload.revision_id != request.revision_id):
        raise RuntimeError('terminal request has no matching confirmed report')
    return SignResult('issued', report)


def _settle(
    db: sqlite3.Connection,
    request_id: str,
    winner: QualificationDecision | None = None,
) -> SignResult:
    ledger, reports = RequestLedger(db), ReportStore(db)
    with db:
        db.execute('BEGIN IMMEDIATE')
        current = ledger.find(request_id)
        if current is None:
            raise RuntimeError('request binding disappeared before settlement')
        terminal = _read_terminal(reports, current)
        if terminal is not None:
            return terminal
        report = reports.find_confirmed(current.round_id, current.revision_id)
        if winner is not None:
            if (winner.round_id, winner.revision_id, winner.request_id) != (
                current.round_id, current.revision_id, current.request_id
            ):
                raise RuntimeError('winning decision does not match the request')
            if current.candidate is None:
                return SignResult('pending')
            report = reports.publish_confirmed(winner.request_id, current.candidate)
        if report is not None and report.request_id == request_id:
            if report.payload.revision_id != current.revision_id:
                raise RuntimeError('report revision does not match the request binding')
            ledger.finish(request_id, report.report_id)
            return SignResult('issued', report)
        ledger.finish(request_id, None)
        return SignResult('stale')


def reconcile_request(
    source: sqlite3.Connection | None,
    db: sqlite3.Connection,
    request: IssueRequest,
    *,
    progress: Progress | None = None,
) -> SignResult:
    reports = ReportStore(db)
    terminal = _read_terminal(reports, request)
    if terminal is not None:
        return terminal
    # A round has one official report.  If it was already committed for any
    # revision, settle this request against it even when the analysis desk is
    # offline: the original number gets its report, a superseded one is stale.
    if reports.find_confirmed(request.round_id) is not None:
        return _settle(db, request.request_id)
    if source is None:
        return SignResult('pending')
    with db:
        db.execute('BEGIN IMMEDIATE')
        live = RequestLedger(db).find(request.request_id)
        if live is None:
            raise RuntimeError('request binding disappeared before signoff')
        terminal = _read_terminal(reports, live)
        if terminal is not None:
            return terminal
        # The round settles exactly one official revision.  A request loses
        # its eligibility when another revision already holds the round's
        # confirmed report or first-issue decision, or when the round's
        # current revision has moved past the one this request is bound to.
        existing = reports.find_confirmed(live.round_id)
        if existing is not None and existing.request_id != live.request_id:
            RequestLedger(db).finish(live.request_id, None)
            return SignResult('stale')
        store = QualificationStore(source)
        winner = store.find_winner(live.round_id)
        if winner is not None and winner.request_id != live.request_id:
            RequestLedger(db).finish(live.request_id, None)
            return SignResult('stale')
        if store.current(live.round_id) != live.revision_id:
            RequestLedger(db).finish(live.request_id, None)
            return SignResult('stale')
        approved = (reports.reserve_revision(live.request_id, live.candidate)
                    if live.candidate is not None else None)
    if approved != request.request_id:
        return _settle(db, request.request_id)
    winner = QualificationDecision(request.round_id, request.revision_id, request.request_id)
    QualificationStore(source).note_first_issue(winner)
    if progress is not None and progress('decided', winner) is False:
        return SignResult('pending')
    return _settle(db, request.request_id, winner)
