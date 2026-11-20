from fractions import Fraction

from analysis import correct_revision
from analysis.qualification import QualificationStore
from handover import claim, review_claim
from handover.claim_records import ClaimLedger
from issuance import sign
from issuance.requests import RequestLedger

from . import LabCase


class TestHandover(LabCase):
    def test_offline_claim(self):
        original = self.original(reverse=True)
        issued = sign(self.source, self.desk, self.round_id, 'R1', 'HANDOVER')
        self.assertEqual(issued.status, 'issued')
        self.reopen()
        self.close_source()
        received = claim(self.desk, self.round_id)
        self.assertEqual(received.report, issued.report)
        self.assertEqual(received.report.payload.readings, original.readings)
        self.assertEqual(received.report.payload.rule.unit, 'μm')
        self.assertEqual(received.report.payload.mean, Fraction(10))
        self.assertEqual(received.report.payload.decision, 'retest')
        self.assertEqual(claim(self.desk, self.round_id), received)
        reviewed = review_claim(self.desk, self.round_id, received.report.report_id)
        self.assertEqual(reviewed, received)
        self.assertIsNone(review_claim(self.desk, self.round_id, 'wrong-report'))
        self.assertEqual(self.claim_count(), 1)
        self.reopen()
        self.close_source()
        self.assertEqual(claim(self.desk, self.round_id), received)
        self.assertEqual(self.claim_count(), 1)
        self.scenario('v5', {'submitted': [['B', 'A'], ['A', 'Z']], 'source': 'offline'},
                      [['A', 'Z'], ['B', 'A']],
                      [[value.specimen_id, value.origin.record_id] for value in received.origins],
                      ['R1', '10', 'retest'], [reviewed.report.payload.revision_id,
                                              str(reviewed.report.payload.mean), reviewed.report.payload.decision],
                      ['issuance/reports.py', 'handover/queue.py', 'handover/provenance.py',
                       'handover/claim_records.py', 'handover/review.py'],
                      '逆序提交后 A 片仍来自 Z，B 片仍来自 A，原正式判定为复测')

    def test_fractional_payload_survives_source_shutdown(self):
        self.original(8, 11)
        saved = sign(self.source, self.desk, self.round_id, 'R1', 'HALF')
        self.reopen()
        self.close_source()
        delivery = claim(self.desk, self.round_id)
        self.assertEqual(delivery.report, saved.report)
        payload = delivery.report.payload
        self.assertEqual((payload.mean.numerator, payload.mean.denominator), (19, 2))
        self.assertEqual((payload.rule.unit, payload.decision), ('μm', 'release'))
        self.assertEqual(review_claim(self.desk, self.round_id, 'HALF'), delivery)

    def test_pending_then_reopen(self):
        original = self.original()
        self.correction(original)

        def defer_before_decision(stage, detail):
            return stage != 'candidate_saved'

        pending = sign(self.source, self.desk, self.round_id, 'R1', 'WAIT', progress=defer_before_decision)
        self.assertIsNone(pending.report)
        self.assertIsNone(QualificationStore(self.source).find_winner(self.round_id))
        self.assertIsNotNone(RequestLedger(self.desk).find('WAIT').candidate)
        absent = claim(self.desk, self.round_id)
        self.assertIsNone(absent)
        self.assertIsNone(ClaimLedger(self.desk).find(self.round_id))
        self.reopen()

        def defer_after_decision(stage, detail):
            if stage == 'decided':
                self.assertEqual((detail.revision_id, detail.request_id), ('R1', 'WAIT'))
                return False
            return None

        awaiting_delivery = sign(self.source, self.desk, self.round_id, 'R1', 'WAIT',
                                 progress=defer_after_decision)
        self.assertEqual(awaiting_delivery.status, 'pending')
        self.assertEqual(self.report_count(), 0)
        self.assertEqual(QualificationStore(self.source).find_winner(self.round_id).request_id, 'WAIT')
        self.assertEqual(correct_revision(self.source, self.round_id, 'R2').status, 'view_only')
        self.close_source()
        self.assertEqual(sign(None, self.desk, self.round_id, 'R1', 'WAIT').status, 'pending')
        self.assertIsNone(claim(self.desk, self.round_id))
        self.assertEqual(self.claim_count(), 0)
        self.reopen()
        final = sign(self.source, self.desk, self.round_id, 'R1', 'WAIT')
        self.assertEqual(final.status, 'issued')
        self.assertEqual(final.report.payload.readings, original.readings)
        self.assertEqual(final.report.payload.mean, Fraction(10))
        self.assertEqual(final.report.payload.decision, 'retest')
        self.reopen()
        self.close_source()
        delivery = claim(self.desk, self.round_id)
        self.assertEqual(delivery.report, final.report)
        self.assertEqual(sign(None, self.desk, self.round_id, 'R1', 'WAIT'), final)
        self.assertEqual(claim(self.desk, self.round_id), delivery)
        self.scenario('v6', {'request': 'WAIT', 'interruptions': ['before_decision', 'before_delivery']},
                      ['pending', True], [pending.status, absent is None], ['R1', 1, 1],
                      [delivery.report.payload.revision_id, self.report_count(), self.claim_count()],
                      ['issuance/reconcile.py', 'issuance/reports.py', 'handover/queue.py',
                       'handover/claim_records.py'],
                      '两次中断均未到可领提交，按原裁决恢复后恰有一份正式件和一条领用')
