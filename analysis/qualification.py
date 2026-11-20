import sqlite3
from dataclasses import dataclass

from measurements.revisions import RevisionHistory

from .snapshots import FrozenAnalysis, SnapshotStore


@dataclass(frozen=True)
class QualificationDecision:
    round_id: str
    revision_id: str
    request_id: str


def confirmation_unavailable(error: sqlite3.OperationalError) -> bool:
    code = getattr(error, 'sqlite_errorcode', 0) & 0xff
    return code in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED,
                    sqlite3.SQLITE_IOERR, sqlite3.SQLITE_CANTOPEN)


class QualificationStore:
    def __init__(self, db: sqlite3.Connection):
        self.db = db

    def initialize(self) -> None:
        self.db.execute('''
            CREATE TABLE IF NOT EXISTS active_corrections (
                round_id TEXT PRIMARY KEY NOT NULL,
                revision_id TEXT NOT NULL,
                FOREIGN KEY (round_id, revision_id)
                    REFERENCES frozen_analyses(round_id, revision_id)
            )
        ''')
        self.db.execute('''
            CREATE TABLE IF NOT EXISTS first_issue_notices (
                round_id TEXT NOT NULL,
                revision_id TEXT NOT NULL,
                request_id TEXT NOT NULL UNIQUE,
                PRIMARY KEY (round_id, revision_id),
                FOREIGN KEY (round_id, revision_id)
                    REFERENCES frozen_analyses(round_id, revision_id)
            )
        ''')

    def current(self, round_id: str) -> str | None:
        row = self.db.execute('SELECT revision_id FROM active_corrections WHERE round_id = ?',
                              (round_id,)).fetchone()
        if row is not None:
            return row[0]
        initial = RevisionHistory(self.db).initial(round_id)
        return initial.revision_id if initial is not None else None

    def find_winner(
        self, round_id: str, revision_id: str | None = None
    ) -> QualificationDecision | None:
        row = self.db.execute('''
            SELECT revision_id, request_id FROM first_issue_notices
            WHERE round_id = ? AND (? IS NULL OR revision_id = ?)
            ORDER BY rowid LIMIT 1
        ''', (round_id, revision_id, revision_id)).fetchone()
        if row is None:
            return None
        return QualificationDecision(round_id, *row)

    def note_first_issue(self, decision: QualificationDecision) -> None:
        with self.db:
            self.db.execute('''
                INSERT INTO first_issue_notices (round_id, revision_id, request_id)
                VALUES (?, ?, ?) ON CONFLICT(round_id, revision_id) DO NOTHING
            ''', (decision.round_id, decision.revision_id, decision.request_id))
            if self.find_winner(decision.round_id, decision.revision_id) != decision:
                raise RuntimeError('issue notice conflicts with the stored request')

    def apply_correction(self, snapshot: FrozenAnalysis) -> str:
        link = snapshot.link
        if link.parent_revision is None:
            raise ValueError('only a frozen correction can be activated')
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            if SnapshotStore(self.db).fetch(link.round_id, link.revision_id) != snapshot:
                raise ValueError('correction does not match the frozen analysis')
            if self.find_winner(link.round_id, link.revision_id) is not None:
                return 'view_only'
            self.db.execute('''
                INSERT INTO active_corrections (round_id, revision_id) VALUES (?, ?)
                ON CONFLICT(round_id) DO UPDATE SET revision_id = excluded.revision_id
            ''', (link.round_id, link.revision_id))
        return 'active'
