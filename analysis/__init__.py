import sqlite3

from measurements.frozen_store import FrozenRevisionStore
from rounds.registry import RoundRegistry

from .corrections import CorrectionResult as CorrectionResult
from .corrections import correct_revision as correct_revision
from .qualification import QualificationStore
from .snapshots import FrozenAnalysis as FrozenAnalysis
from .snapshots import SnapshotStore
from .snapshots import inspect_revision as inspect_revision


def initialize_analysis(db: sqlite3.Connection) -> None:
    db.execute('PRAGMA foreign_keys = ON')
    RoundRegistry(db).initialize()
    FrozenRevisionStore(db).initialize()
    SnapshotStore(db).initialize()
    QualificationStore(db).initialize()
