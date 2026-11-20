from fractions import Fraction

from analysis import inspect_revision
from handover import claim
from issuance import sign
from rounds import open_round
from rounds.registry import RoundRegistry

from . import LabCase


class TestAnalysis(LabCase):
    def test_threshold_equality(self):
        self.original()
        result = inspect_revision(self.source, self.round_id, 'R1')
        signed = sign(self.source, self.desk, self.round_id, 'R1', 'EQUALITY')
        self.assertEqual(signed.status, 'issued')
        delivery = claim(self.desk, self.round_id)
        self.assertEqual(delivery.report, signed.report)
        self.assertEqual(result.mean, Fraction(10))
        self.assertEqual(result.rule.threshold, Fraction(10))
        self.assertEqual(result.rule.unit, 'μm')
        self.scenario('v1', {'readings': [8, 12], 'line': 10}, ['10', 'retest'],
                      [str(result.mean), result.decision], ['R1', 'retest'],
                      [delivery.report.payload.revision_id, delivery.report.payload.decision],
                      ['analysis/mean.py', 'analysis/threshold.py', 'handover/claim.py'],
                      '8 加 12 得 20，除以二等于复测线，班组须复测')

    def test_fractional_mean(self):
        self.original(8, 11)
        result = inspect_revision(self.source, self.round_id, 'R1')
        issued = sign(self.source, self.desk, self.round_id, 'R1', 'FRACTION')
        self.assertEqual(result.mean, Fraction(19, 2))
        self.assertEqual(issued.status, 'issued')
        self.scenario('v8', {'readings': [8, 11], 'line': 10}, ['19/2', 'release'],
                      [str(result.mean), result.decision], ['19/2', 'release'],
                      [str(issued.report.payload.mean), issued.report.payload.decision],
                      ['analysis/snapshots.py', 'issuance/report_payload.py'],
                      '和为 19，精确均值 19/2 小于 10')

    def test_invalid_round_rules_leave_no_round(self):
        cases = [
            ('A', 'A', 'QC', 10, 'μm'), ('A', 'B', 'QC', -1, 'μm'),
            ('A', 'B', 'QC', 10.0, 'μm'), ('A', 'B', 'QC', True, 'μm'),
            ('A', 'B', 'QC', 10, 'mm'), ('A', 'B', ' ', 10, 'μm'),
        ]
        for args in cases:
            with self.subTest(args=args):
                with self.assertRaises(ValueError):
                    open_round(self.source, 'BAD', *args)
                with self.assertRaises(LookupError):
                    RoundRegistry(self.source).get('BAD')
        with self.assertRaises(ValueError):
            open_round(self.source, self.round_id, 'A', 'C', 'REPLACE', 20)
        self.assertEqual(RoundRegistry(self.source).get(self.round_id).rule.name, 'QC-10')

    def test_round_rule_binding_survives_reopen(self):
        self.original()
        open_round(self.source, 'Q-2', 'A', 'B', 'QC-11', 11)
        from measurements import freeze_revision

        freeze_revision(self.source, 'Q-2', 'R1', self.readings(round_id='Q-2'))
        self.reopen()
        older = inspect_revision(self.source, self.round_id, 'R1')
        later = inspect_revision(self.source, 'Q-2', 'R1')
        self.assertEqual((older.rule.name, older.rule.unit, older.rule.threshold, older.decision),
                         ('QC-10', 'μm', Fraction(10), 'retest'))
        self.assertEqual((later.rule.name, later.rule.unit, later.rule.threshold, later.decision),
                         ('QC-11', 'μm', Fraction(11), 'release'))
        self.assertEqual(older.mean, later.mean)

    def test_fractional_rule_and_signed_deviations(self):
        from measurements import freeze_revision

        open_round(self.source, 'Q-3', 'A', 'B', 'QC-HALF', Fraction(1, 2))
        freeze_revision(self.source, 'Q-3', 'R1', self.readings(-2, 3, round_id='Q-3'))
        snapshot = inspect_revision(self.source, 'Q-3', 'R1')
        self.assertEqual((snapshot.mean, snapshot.rule.threshold, snapshot.decision),
                         (Fraction(1, 2), Fraction(1, 2), 'retest'))
