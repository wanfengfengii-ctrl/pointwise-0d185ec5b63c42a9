import sqlite3
from dataclasses import dataclass

from .intake import Reading
from .origins import ReadOrigin
from .revisions import RevisionHistory, RevisionLink


@dataclass(frozen=True)
class FrozenRevision:
    link: RevisionLink
    readings: tuple[Reading, Reading]


class FrozenRevisionStore:
    def __init__(self, db: sqlite3.Connection):
        self.db = db
        self.history = RevisionHistory(db)

    def initialize(self) -> None:
        self.history.initialize()
        self.db.execute('''
            CREATE TABLE IF NOT EXISTS frozen_readings (
                round_id TEXT NOT NULL,
                revision_id TEXT NOT NULL,
                position INTEGER NOT NULL CHECK (position IN (0, 1)),
                specimen_id TEXT NOT NULL,
                deviation TEXT NOT NULL,
                record_id TEXT NOT NULL,
                location TEXT NOT NULL,
                original_record_id TEXT NOT NULL,
                original_location TEXT NOT NULL,
                PRIMARY KEY (round_id, revision_id, position),
                FOREIGN KEY (round_id, revision_id)
                    REFERENCES measurement_revisions(round_id, revision_id)
            )
        ''')

    def store(self, frozen: FrozenRevision) -> None:
        rows = []
        for position, reading in enumerate(frozen.readings):
            origin = reading.origin
            rows.append((frozen.link.round_id, frozen.link.revision_id, position,
                         reading.specimen_id, format(reading.deviation, 'x'),
                         origin.record_id, origin.location,
                         origin.original_record_id, origin.original_location))
        self.db.executemany('''
            INSERT INTO frozen_readings VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', rows)

    def fetch(self, round_id: str, revision_id: str) -> FrozenRevision | None:
        link = self.history.get(round_id, revision_id)
        if link is None:
            return None
        rows = self.db.execute('''
            SELECT specimen_id, deviation, record_id, location, original_record_id, original_location
            FROM frozen_readings WHERE round_id = ? AND revision_id = ? ORDER BY position
        ''', (round_id, revision_id)).fetchall()
        if len(rows) != 2:
            raise RuntimeError('frozen revision is missing part of its reading pair')
        readings = []
        for specimen, deviation, record, location, original_record, original_location in rows:
            origin = ReadOrigin(specimen, record, location, original_record, original_location)
            readings.append(Reading(round_id, specimen, int(deviation, 16), origin))
        return FrozenRevision(link, (readings[0], readings[1]))
