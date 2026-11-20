import sqlite3
from dataclasses import dataclass

from issuance.reports import IssuedReport


@dataclass(frozen=True)
class ClaimRecord:
    round_id: str
    report_id: str


class ClaimLedger:
    def __init__(self, db: sqlite3.Connection):
        self.db = db

    def initialize(self) -> None:
        self.db.execute('''
            CREATE TABLE IF NOT EXISTS handover_claims (
                round_id TEXT PRIMARY KEY NOT NULL,
                report_id TEXT NOT NULL UNIQUE,
                FOREIGN KEY (round_id, report_id) REFERENCES confirmed_reports(round_id, report_id)
            )
        ''')

    def record(self, report: IssuedReport) -> ClaimRecord:
        expected = ClaimRecord(report.payload.round_id, report.report_id)
        with self.db:
            self.db.execute('''
                INSERT INTO handover_claims (round_id, report_id) VALUES (?, ?)
                ON CONFLICT(round_id) DO NOTHING
            ''', (expected.round_id, expected.report_id))
            existing = self.find(expected.round_id)
            if existing != expected:
                raise RuntimeError('existing claim records a different report')
        return existing

    def find(self, round_id: str) -> ClaimRecord | None:
        row = self.db.execute('SELECT report_id FROM handover_claims WHERE round_id = ?',
                              (round_id,)).fetchone()
        if row is None:
            return None
        return ClaimRecord(round_id, row[0])
