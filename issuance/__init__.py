import sqlite3

from .first_issue import sign as sign
from .reconcile import SignResult as SignResult
from .reports import IssuedReport as IssuedReport
from .reports import ReportStore
from .requests import RequestLedger


def initialize_issuance(db: sqlite3.Connection) -> None:
    db.execute('PRAGMA foreign_keys = ON')
    ReportStore(db).initialize()
    RequestLedger(db).initialize()
