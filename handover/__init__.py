import sqlite3

from .claim import ClaimResult as ClaimResult
from .claim import claim as claim
from .claim_records import ClaimLedger
from .review import review_claim as review_claim


def initialize_handover(db: sqlite3.Connection) -> None:
    ClaimLedger(db).initialize()
