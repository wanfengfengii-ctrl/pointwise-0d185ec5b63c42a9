import sqlite3
from contextlib import closing
from fractions import Fraction

from analysis import correct_revision, initialize_analysis, inspect_revision
from analysis.qualification import QualificationStore
from handover import claim
from issuance import initialize_issuance, sign
from issuance.reports import ReportStore
from issuance.requests import RequestLedger

from . import LabCase


class ReplyLost(ConnectionError):
    pass


class TestIssuance(LabCase):
    def test_correction_wins(self):
        original = self.original()
        self.correction(original)
        self.assertEqual(inspect_revision(self.source, self.round_id, 'R2').mean, Fraction(9))
        self.assertEqual(QualificationStore(self.source).current(self.round_id), 'R1')
        observations = []

        def after_last_read(stage, detail):
            if stage != 'candidate_saved':
                return None
            self.assertEqual(detail, 'R1')
            self.assertIsNone(QualificationStore(self.source).find_winner(self.round_id))
            with closing(sqlite3.connect(self.desk_path)) as other_desk:
                initialize_issuance(other_desk)
                saved = RequestLedger(other_desk).find('OLD')
                self.assertEqual((saved.status, saved.candidate.revision_id), ('pending', 'R1'))
                self.assertIsNone(claim(other_desk, self.round_id))
            with closing(sqlite3.connect(self.source_path)) as analyst:
                initialize_analysis(analyst)
                result = correct_revision(analyst, self.round_id, 'R2')
                observations.append(result.status)
                self.assertEqual(QualificationStore(analyst).current(self.round_id), 'R2')
            return None

        stale = sign(self.source, self.desk, self.round_id, 'R1', 'OLD', progress=after_last_read)
        self.assertIsNone(stale.report, 'FIRST_ISSUE_REVISION: superseded R1 became official')
        self.assertIsNone(claim(self.desk, self.round_id), 'FIRST_ISSUE_REVISION: stale material was claimable')
        self.assertEqual(inspect_revision(self.source, self.round_id, 'R1').mean, Fraction(10))
        issued = sign(self.source, self.desk, self.round_id, 'R2', 'NEW')
        self.assertEqual(issued.status, 'issued', 'FIRST_ISSUE_REVISION: R2 failed to become official')
        self.reopen()
        self.close_source()
        delivery = claim(self.desk, self.round_id)
        self.assertEqual(delivery.report, issued.report)
        self.assertEqual(self.report_count(), 1)
        self.scenario('v3', {'R1': [8, 12], 'R2': [8, 10], 'line': 10},
                      ['active', 'stale'], observations + [stale.status], ['R2', '9', 'release'],
                      [delivery.report.payload.revision_id, str(delivery.report.payload.mean),
                       delivery.report.payload.decision],
                      ['analysis/corrections.py', 'analysis/qualification.py',
                       'issuance/first_issue.py', 'issuance/reconcile.py', 'handover/claim.py'],
                      'R2 已启用才恢复旧请求，只有均值 9 的 R2 能首签并领用')

    def test_issue_wins_with_lost_reply(self):
        original = self.original()
        confirmations = []

        def discard_reply(stage, detail):
            if stage == 'confirmed':
                confirmations.append(detail)
                raise ReplyLost('caller disconnected after the report commit')
            return None

        with self.assertRaises(ReplyLost):
            sign(self.source, self.desk, self.round_id, 'R1', 'ORIGINAL', progress=discard_reply)
        self.assertEqual(len(confirmations), 1)
        original_report = ReportStore(self.desk).find_confirmed(self.round_id)
        self.assertEqual(original_report, confirmations[0])
        correction = self.correction(original)
        outcome = correct_revision(self.source, self.round_id, 'R2')
        self.assertEqual(outcome.snapshot.mean, Fraction(9))
        self.reopen()
        self.assertEqual(inspect_revision(self.source, self.round_id, 'R2').readings, correction.readings)
        self.assertEqual(inspect_revision(self.source, self.round_id, 'R1').readings, original.readings)
        self.assertEqual(sign(self.source, self.desk, self.round_id, 'R2', 'LATER').status, 'stale')
        self.close_source()
        receipt = sign(None, self.desk, self.round_id, 'R1', 'ORIGINAL')
        delivery = claim(self.desk, self.round_id)
        self.assertEqual((receipt.report, delivery.report), (original_report, original_report))
        self.assertEqual(self.report_count(), 1)
        self.scenario('v4', {'R1': [8, 12], 'R2': [8, 10], 'reply': 'lost'},
                      ['view_only', 'issued'], [outcome.status, receipt.status],
                      ['ORIGINAL', 'R1', '10', 'retest'],
                      [delivery.report.request_id, delivery.report.payload.revision_id,
                       str(delivery.report.payload.mean), delivery.report.payload.decision],
                      ['analysis/qualification.py', 'issuance/requests.py',
                       'issuance/reconcile.py', 'handover/claim.py'],
                      'R1 已正式提交才更正，复测义务及原号固定在 R1')

    def test_request_parameter_conflict(self):
        self.correction(self.original())
        first = sign(self.source, self.desk, self.round_id, 'R1', 'BOUND')
        self.reopen()
        with self.assertRaises(ValueError) as captured:
            sign(self.source, self.desk, self.round_id, 'R2', 'BOUND')
        self.assertEqual(sign(self.source, self.desk, self.round_id, 'R1', 'BOUND'), first)
        fixed = ReportStore(self.desk).find_confirmed(self.round_id)
        self.assertEqual(fixed, first.report)
        self.scenario('v7', {'request': 'BOUND', 'initial': 'R1', 'changed': 'R2'},
                      'ValueError', type(captured.exception).__name__, ['R1', 1],
                      [fixed.payload.revision_id, self.report_count()],
                      ['issuance/requests.py', 'issuance/first_issue.py', 'issuance/reports.py'],
                      'BOUND 初次绑定 R1，改为 R2 须拒绝，正式件仍为原来的一份')

    def test_pending_request_parameter_binding(self):
        self.correction(self.original())

        def stop_after_fetch(stage, detail):
            return stage != 'candidate_saved'

        result = sign(self.source, self.desk, self.round_id, 'R1', 'PENDING', progress=stop_after_fetch)
        self.assertEqual(result.status, 'pending')
        self.reopen()
        with self.assertRaises(ValueError):
            sign(self.source, self.desk, self.round_id, 'R2', 'PENDING')
        with self.assertRaises(ValueError):
            sign(self.source, self.desk, 'OTHER', 'R1', 'PENDING')
        self.assertEqual(self.report_count(), 0)
        self.assertEqual(sign(self.source, self.desk, self.round_id, 'R1', 'PENDING').status, 'issued')

    def test_declined_request_keeps_its_original_outcome(self):
        self.correction(self.original())
        self.assertEqual(sign(self.source, self.desk, self.round_id, 'R2', 'EARLY').status, 'stale')
        self.assertEqual(correct_revision(self.source, self.round_id, 'R2').status, 'active')
        self.reopen()
        self.assertEqual(sign(self.source, self.desk, self.round_id, 'R2', 'EARLY').status, 'stale')
        self.assertEqual(sign(self.source, self.desk, self.round_id, 'R2', 'ACTIVE').status, 'issued')
