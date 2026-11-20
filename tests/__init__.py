import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from analysis import initialize_analysis
from handover import initialize_handover
from issuance import initialize_issuance
from measurements import (
    Reading,
    bind_read_origin,
    freeze_revision,
    inherit_read_origin,
    record_corrected_origin,
)
from rounds import open_round


class LabCase(unittest.TestCase):
    round_id = 'Q-1'

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.source_path = Path(self.directory.name) / 'analysis.sqlite'
        self.desk_path = Path(self.directory.name) / 'issuance.sqlite'
        self.source = None
        self.desk = None
        self.addCleanup(self.close_databases)
        self.reopen()
        open_round(self.source, self.round_id, 'A', 'B', 'QC-10', 10)

    def close_source(self):
        if self.source is not None:
            self.source.close()
            self.source = None

    def close_databases(self):
        self.close_source()
        if self.desk is not None:
            self.desk.close()
            self.desk = None

    def reopen(self):
        self.close_databases()
        self.source = sqlite3.connect(self.source_path)
        self.desk = sqlite3.connect(self.desk_path)
        initialize_analysis(self.source)
        initialize_issuance(self.desk)
        initialize_handover(self.desk)

    def readings(self, a=8, b=12, *, round_id=None):
        rid = self.round_id if round_id is None else round_id
        return (Reading(rid, 'A', a, bind_read_origin('A', 'Z', '原测单/第1行')),
                Reading(rid, 'B', b, bind_read_origin('B', 'A', '原测单/第2行')))

    def original(self, a=8, b=12, *, reverse=False):
        readings = self.readings(a, b)
        if reverse:
            readings = readings[::-1]
        return freeze_revision(self.source, self.round_id, 'R1', readings)

    def correction(self, parent, value=10, *, revision='R2'):
        a, b = parent.readings
        readings = (
            Reading(a.round_id, a.specimen_id, a.deviation, inherit_read_origin(a.origin)),
            Reading(b.round_id, b.specimen_id, value,
                    record_corrected_origin(b.origin, f'勘误-{revision}', '勘误单/第1行')),
        )
        return freeze_revision(self.source, a.round_id, revision, readings,
                               parent_revision=parent.link.revision_id)

    def report_count(self):
        return self.desk.execute('SELECT count(*) FROM confirmed_reports').fetchone()[0]

    def claim_count(self):
        return self.desk.execute('SELECT count(*) FROM handover_claims').fetchone()[0]

    def scenario(self, case_id, inputs, expected, actual, downstream_expected,
                 downstream_actual, paths, oracle):
        self.assertEqual(actual, expected)
        self.assertEqual(downstream_actual, downstream_expected)
        record = dict(case_id=case_id, input=inputs, expected=expected, actual=actual,
                      downstream_expected=downstream_expected, downstream_actual=downstream_actual,
                      code_paths=paths, oracle=oracle)
        print('POINTWISE_SCENARIO ' + json.dumps(record, ensure_ascii=False, sort_keys=True))
