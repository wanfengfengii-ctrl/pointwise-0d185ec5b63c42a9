import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class RevisionLink:
    round_id: str
    revision_id: str
    parent_revision: str | None


class RevisionHistory:
    def __init__(self, db: sqlite3.Connection):
        self.db = db

    def initialize(self) -> None:
        self.db.execute('''
            CREATE TABLE IF NOT EXISTS measurement_revisions (
                round_id TEXT NOT NULL REFERENCES inspection_rounds(round_id),
                revision_id TEXT NOT NULL,
                parent_revision TEXT,
                PRIMARY KEY (round_id, revision_id),
                FOREIGN KEY (round_id, parent_revision)
                    REFERENCES measurement_revisions(round_id, revision_id)
            )
        ''')
        self.db.execute('''
            CREATE UNIQUE INDEX IF NOT EXISTS one_original_per_round
            ON measurement_revisions(round_id) WHERE parent_revision IS NULL
        ''')

    def append(self, link: RevisionLink) -> None:
        if link.parent_revision is not None and self.get(link.round_id, link.parent_revision) is None:
            raise LookupError('parent revision is absent from the target round')
        result = self.db.execute('''
            INSERT INTO measurement_revisions (round_id, revision_id, parent_revision)
            VALUES (?, ?, ?) ON CONFLICT DO NOTHING
        ''', (link.round_id, link.revision_id, link.parent_revision))
        if result.rowcount == 0:
            raise ValueError('duplicate revision identifier or original revision')

    def get(self, round_id: str, revision_id: str) -> RevisionLink | None:
        row = self.db.execute('''
            SELECT parent_revision FROM measurement_revisions
            WHERE round_id = ? AND revision_id = ?
        ''', (round_id, revision_id)).fetchone()
        if row is None:
            return None
        return RevisionLink(round_id, revision_id, row[0])

    def initial(self, round_id: str) -> RevisionLink | None:
        row = self.db.execute('''
            SELECT revision_id FROM measurement_revisions
            WHERE round_id = ? AND parent_revision IS NULL
        ''', (round_id,)).fetchone()
        if row is None:
            return None
        return RevisionLink(round_id, row[0], None)
