import sqlite3
from dataclasses import dataclass

from .report_payload import ReportPayload, unpack_report_payload


@dataclass(frozen=True)
class IssuedReport:
    report_id: str
    request_id: str
    payload: ReportPayload


class ReportStore:
    def __init__(self, db: sqlite3.Connection):
        self.db = db

    def initialize(self) -> None:
        self.db.execute('''
            CREATE TABLE IF NOT EXISTS confirmed_reports (
                report_id TEXT PRIMARY KEY NOT NULL,
                round_id TEXT NOT NULL,
                revision_id TEXT NOT NULL,
                request_id TEXT NOT NULL UNIQUE,
                payload TEXT NOT NULL,
                UNIQUE (round_id, revision_id),
                UNIQUE (round_id, report_id)
            )
        ''')

        self.db.execute('''
            CREATE TABLE IF NOT EXISTS revision_signoffs (
                round_id TEXT NOT NULL,
                revision_id TEXT NOT NULL,
                request_id TEXT NOT NULL UNIQUE,
                PRIMARY KEY (round_id, revision_id)
            )
        ''')

    def reserve_revision(self, request_id: str, payload: ReportPayload) -> str:
        self.db.execute('''
            INSERT INTO revision_signoffs (round_id, revision_id, request_id)
            VALUES (?, ?, ?) ON CONFLICT(round_id, revision_id) DO NOTHING
        ''', (payload.round_id, payload.revision_id, request_id))
        return self.db.execute('''
            SELECT request_id FROM revision_signoffs WHERE round_id = ? AND revision_id = ?
        ''', (payload.round_id, payload.revision_id)).fetchone()[0]

    def publish_confirmed(self, request_id: str, payload: ReportPayload) -> IssuedReport:
        provided = IssuedReport(request_id, request_id, payload)
        self.db.execute('''
            INSERT INTO confirmed_reports (report_id, round_id, revision_id, request_id, payload)
            VALUES (?, ?, ?, ?, ?) ON CONFLICT(round_id, revision_id) DO NOTHING
        ''', (provided.report_id, payload.round_id, payload.revision_id, request_id, payload.to_json()))
        existing = self.find_confirmed(payload.round_id, payload.revision_id)
        if existing != provided:
            raise RuntimeError('confirmed report differs from the settled winner')
        return existing

    def find_confirmed(self, round_id: str, revision_id: str | None = None) -> IssuedReport | None:
        row = self.db.execute('''
            SELECT report_id, request_id, revision_id, payload FROM confirmed_reports
            WHERE round_id = ? AND (? IS NULL OR revision_id = ?)
            ORDER BY rowid LIMIT 1
        ''', (round_id, revision_id, revision_id)).fetchone()
        if row is None:
            return None
        report_id, request_id, stored_revision, encoded = row
        payload = unpack_report_payload(encoded)
        if (payload.round_id, payload.revision_id) != (round_id, stored_revision):
            raise RuntimeError('stored report does not match its round and revision')
        return IssuedReport(report_id, request_id, payload)
