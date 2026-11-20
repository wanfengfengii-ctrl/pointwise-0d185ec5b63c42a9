import sqlite3
from dataclasses import dataclass
from fractions import Fraction

from measurements.frozen_store import FrozenRevisionStore
from measurements.intake import Reading
from measurements.revisions import RevisionLink
from rounds.registry import RoundRegistry
from rounds.rules import InspectionRule, make_inspection_rule

from .mean import exact_mean
from .threshold import RecheckDecision, classify_mean


@dataclass(frozen=True)
class FrozenAnalysis:
    link: RevisionLink
    readings: tuple[Reading, Reading]
    rule: InspectionRule
    mean: Fraction
    decision: RecheckDecision


class SnapshotStore:
    def __init__(self, db: sqlite3.Connection):
        self.db = db
        self.frozen = FrozenRevisionStore(db)

    def initialize(self) -> None:
        self.db.execute('''
            CREATE TABLE IF NOT EXISTS frozen_analyses (
                round_id TEXT NOT NULL,
                revision_id TEXT NOT NULL,
                rule_name TEXT NOT NULL,
                line_num TEXT NOT NULL,
                line_den TEXT NOT NULL,
                unit TEXT NOT NULL,
                mean_num TEXT NOT NULL,
                mean_den TEXT NOT NULL,
                decision TEXT NOT NULL CHECK (decision IN ('retest', 'release')),
                PRIMARY KEY (round_id, revision_id),
                FOREIGN KEY (round_id, revision_id)
                    REFERENCES measurement_revisions(round_id, revision_id)
            )
        ''')

    def fetch(self, round_id: str, revision_id: str) -> FrozenAnalysis | None:
        row = self.db.execute('''
            SELECT rule_name, line_num, line_den, unit, mean_num, mean_den, decision
            FROM frozen_analyses WHERE round_id = ? AND revision_id = ?
        ''', (round_id, revision_id)).fetchone()
        if row is None:
            return None
        frozen = self.frozen.fetch(round_id, revision_id)
        if frozen is None:
            raise RuntimeError('analysis has lost its frozen reading pair')
        name, line_num, line_den, unit, mean_num, mean_den, decision = row
        rule = make_inspection_rule(name, Fraction(int(line_num, 16), int(line_den, 16)), unit)
        mean = Fraction(int(mean_num, 16), int(mean_den, 16))
        return FrozenAnalysis(frozen.link, frozen.readings, rule, mean, RecheckDecision(decision))

    def save_once(self, snapshot: FrozenAnalysis) -> FrozenAnalysis:
        link, rule, mean = snapshot.link, snapshot.rule, snapshot.mean
        with self.db:
            self.db.execute('''
                INSERT INTO frozen_analyses VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(round_id, revision_id) DO NOTHING
            ''', (link.round_id, link.revision_id, rule.name,
                  format(rule.threshold.numerator, 'x'), format(rule.threshold.denominator, 'x'),
                  rule.unit, format(mean.numerator, 'x'), format(mean.denominator, 'x'),
                  snapshot.decision.value))
            existing = self.fetch(link.round_id, link.revision_id)
            if existing != snapshot:
                raise RuntimeError('saved analysis differs from its immutable input')
        return existing


def inspect_revision(db: sqlite3.Connection, round_id: str, revision_id: str) -> FrozenAnalysis:
    store = SnapshotStore(db)
    existing = store.fetch(round_id, revision_id)
    if existing is not None:
        return existing
    frozen = store.frozen.fetch(round_id, revision_id)
    if frozen is None:
        raise LookupError(f'no frozen revision {revision_id!r} in round {round_id!r}')
    rule = RoundRegistry(db).get(round_id).rule
    first, second = frozen.readings
    mean = exact_mean(first.deviation, second.deviation)
    snapshot = FrozenAnalysis(frozen.link, frozen.readings, rule, mean, classify_mean(mean, rule))
    return store.save_once(snapshot)
