import sqlite3

from issuance.reports import IssuedReport, ReportStore


class ConfirmedHandoverQueue:
    def __init__(self, issuance_db: sqlite3.Connection):
        self.reports = ReportStore(issuance_db)

    def find_by_round(self, round_id: str) -> IssuedReport | None:
        return self.reports.find_confirmed(round_id)
