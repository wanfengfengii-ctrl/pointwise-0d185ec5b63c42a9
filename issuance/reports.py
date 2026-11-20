import sqlite3
from dataclasses import dataclass

from .report_payload import ReportPayload, unpack_report_payload


@dataclass(frozen=True)
class IssuedReport:
    report_id: str
    request_id: str
    payload: ReportPayload


def _ensure_unique_index(db: sqlite3.Connection, name: str, table: str, column: str) -> None:
    """Add a round-scoped uniqueness index without destroying stored history.

    A database written by an older build may already hold rows that violate
    the new rule.  In that case the index is skipped and the entry points
    enforce the rule in code; no committed row is rewritten on reopen.
    """
    try:
        with db:
            db.execute(f'CREATE UNIQUE INDEX IF NOT EXISTS {name} ON {table}({column})')
    except sqlite3.IntegrityError:
        pass


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
                UNIQUE (round_id),
                UNIQUE (round_id, revision_id),
                UNIQUE (round_id, report_id)
            )
        ''')
        # A round settles exactly one official report.  The table constraint
        # covers fresh databases; the index also covers databases opened from
        # an earlier build.  Illegal duplicates already on disk are left
        # untouched rather than deleted.
        _ensure_unique_index(self.db, 'one_report_per_round',
                             'confirmed_reports', 'round_id')

        self.db.execute('''
            CREATE TABLE IF NOT EXISTS revision_signoffs (
                round_id TEXT PRIMARY KEY NOT NULL,
                revision_id TEXT NOT NULL,
                request_id TEXT NOT NULL UNIQUE
            )
        ''')
        # Older builds used (round_id, revision_id) as the key and could
        # reserve several revisions in one round.  The earliest reservation
        # is that round's legal approval; every read below is by round.
        _ensure_unique_index(self.db, 'one_signoff_per_round',
                             'revision_signoffs', 'round_id')

    def reserve_revision(self, request_id: str, payload: ReportPayload) -> str:
        existing = self.db.execute('''
            SELECT revision_id, request_id FROM revision_signoffs
            WHERE round_id = ? ORDER BY rowid LIMIT 1
        ''', (payload.round_id,)).fetchone()
        if existing is None:
            self.db.execute('''
                INSERT INTO revision_signoffs (round_id, revision_id, request_id)
                VALUES (?, ?, ?) ON CONFLICT DO NOTHING
            ''', (payload.round_id, payload.revision_id, request_id))
        elif existing[1] != request_id and existing[0] != payload.revision_id:
            # The caller has already confirmed that the round's current
            # revision is this payload's revision, so an earlier reservation
            # for another revision can no longer become official.  Reclaim the
            # round so an interrupted reservation cannot block it forever.
            self.db.execute('''
                DELETE FROM revision_signoffs
                WHERE round_id = ? AND request_id = ? AND revision_id = ?
            ''', (payload.round_id, existing[1], existing[0]))
            self.db.execute('''
                INSERT INTO revision_signoffs (round_id, revision_id, request_id)
                VALUES (?, ?, ?) ON CONFLICT DO NOTHING
            ''', (payload.round_id, payload.revision_id, request_id))
        return self.db.execute('''
            SELECT request_id FROM revision_signoffs
            WHERE round_id = ? ORDER BY rowid LIMIT 1
        ''', (payload.round_id,)).fetchone()[0]

    def publish_confirmed(self, request_id: str, payload: ReportPayload) -> IssuedReport:
        provided = IssuedReport(request_id, request_id, payload)
        existing = self.find_confirmed(payload.round_id)
        if existing is not None:
            if existing != provided:
                raise RuntimeError('round already has a different confirmed report')
            return existing
        self.db.execute('''
            INSERT INTO confirmed_reports (report_id, round_id, revision_id, request_id, payload)
            VALUES (?, ?, ?, ?, ?) ON CONFLICT DO NOTHING
        ''', (provided.report_id, payload.round_id, payload.revision_id, request_id, payload.to_json()))
        existing = self.find_confirmed(payload.round_id)
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
