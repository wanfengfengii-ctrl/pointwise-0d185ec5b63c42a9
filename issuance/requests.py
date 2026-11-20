import sqlite3
from dataclasses import dataclass

from rounds.specimens import require_name

from .report_payload import ReportPayload, unpack_report_payload


@dataclass(frozen=True)
class IssueRequest:
    request_id: str
    round_id: str
    revision_id: str
    status: str
    candidate: ReportPayload | None
    report_id: str | None


class RequestLedger:
    def __init__(self, db: sqlite3.Connection):
        self.db = db

    def initialize(self) -> None:
        self.db.execute('''
            CREATE TABLE IF NOT EXISTS issue_requests (
                request_id TEXT PRIMARY KEY NOT NULL,
                round_id TEXT NOT NULL,
                revision_id TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'stale', 'issued')),
                candidate TEXT,
                report_id TEXT REFERENCES confirmed_reports(report_id),
                CHECK ((status = 'issued') = (report_id IS NOT NULL))
            )
        ''')

    def find(self, request_id: str) -> IssueRequest | None:
        row = self.db.execute('''
            SELECT round_id, revision_id, status, candidate, report_id
            FROM issue_requests WHERE request_id = ?
        ''', (request_id,)).fetchone()
        if row is None:
            return None
        round_id, revision_id, status, encoded, report_id = row
        candidate = unpack_report_payload(encoded) if encoded is not None else None
        return IssueRequest(request_id, round_id, revision_id, status, candidate, report_id)

    def bind(self, request_id: str, round_id: str, revision_id: str) -> IssueRequest:
        require_name(request_id, 'request identifier')
        require_name(round_id, 'round identifier')
        require_name(revision_id, 'revision identifier')
        request = self.find(request_id)
        if request is None:
            with self.db:
                self.db.execute('''
                    INSERT INTO issue_requests (request_id, round_id, revision_id)
                    VALUES (?, ?, ?) ON CONFLICT(request_id) DO NOTHING
                ''', (request_id, round_id, revision_id))
                request = self.find(request_id)
        if (request.round_id, request.revision_id) != (round_id, revision_id):
            raise ValueError(f'request number {request_id!r} already has different parameters')
        return request

    def save_candidate(self, request: IssueRequest, payload: ReportPayload) -> IssueRequest:
        if (request.round_id, request.revision_id) != (payload.round_id, payload.revision_id):
            raise ValueError('candidate material does not match the bound request')
        with self.db:
            self.db.execute('''
                UPDATE issue_requests SET candidate = ?
                WHERE request_id = ? AND status = 'pending' AND candidate IS NULL
            ''', (payload.to_json(), request.request_id))
            saved = self.find(request.request_id)
            if saved is None or (saved.candidate is not None and saved.candidate != payload):
                raise RuntimeError('request no longer matches its frozen candidate')
        return saved

    def finish(self, request_id: str, report_id: str | None) -> None:
        status = 'issued' if report_id is not None else 'stale'
        result = self.db.execute('''
            UPDATE issue_requests SET status = ?, report_id = ?
            WHERE request_id = ? AND status = 'pending'
        ''', (status, report_id, request_id))
        if result.rowcount != 1:
            raise RuntimeError('request must be pending when its outcome is saved')
