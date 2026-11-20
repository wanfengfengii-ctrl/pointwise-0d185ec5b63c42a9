from fractions import Fraction

from analysis import correct_revision, inspect_revision
from analysis.qualification import QualificationStore
from handover import claim, review_claim
from issuance import sign
from issuance.reports import ReportStore
from issuance.requests import RequestLedger

from . import LabCase


class TestFirstIssueIncident(LabCase):
    """Regression for the night-shift retest handover incident (INCIDENT.md)."""

    def _pause(self, stage):
        return lambda current, _: current != stage

    def test_correction_first_only_r2_can_be_official(self):
        original = self.original()
        self.correction(original)
        pending = sign(self.source, self.desk, self.round_id, 'R1', 'OLD',
                       progress=self._pause('candidate_saved'))
        self.assertEqual(pending.status, 'pending')
        self.assertIsNone(claim(self.desk, self.round_id))
        self.assertEqual(QualificationStore(self.source).current(self.round_id), 'R1')

        self.assertEqual(correct_revision(self.source, self.round_id, 'R2').status, 'active')
        self.assertEqual(QualificationStore(self.source).current(self.round_id), 'R2')
        self.reopen()

        old = sign(self.source, self.desk, self.round_id, 'R1', 'OLD')
        self.assertEqual(old.status, 'stale')
        self.assertIsNone(old.report)
        self.assertIsNone(claim(self.desk, self.round_id))

        new = sign(self.source, self.desk, self.round_id, 'R2', 'NEW')
        self.assertEqual(new.status, 'issued')
        self.assertEqual(new.report.payload.revision_id, 'R2')
        self.assertEqual(str(new.report.payload.mean), '9')
        self.assertEqual(new.report.payload.decision, 'release')
        self.assertEqual(self.report_count(), 1)

        self.reopen()
        self.close_source()
        delivery = claim(self.desk, self.round_id)
        self.assertEqual(delivery.report, new.report)
        self.assertEqual(review_claim(self.desk, self.round_id, delivery.record.report_id), delivery)
        self.assertEqual([(row.specimen_id, row.deviation, row.origin.record_id,
                           row.origin.original_record_id) for row in delivery.origins],
                         [('A', 8, 'Z', 'Z'), ('B', 10, '勘误-R2', 'A')])
        self.assertEqual(self.claim_count(), 1)

    def test_first_issue_first_keeps_r1_and_r2_is_view_only(self):
        original = self.original()
        self.correction(original)

        def stop_after_decision(stage, detail):
            if stage == 'decided':
                self.assertEqual((detail.revision_id, detail.request_id), ('R1', 'OLD'))
                return False
            return None

        pending = sign(self.source, self.desk, self.round_id, 'R1', 'OLD',
                       progress=stop_after_decision)
        self.assertEqual(pending.status, 'pending')
        self.assertIsNone(claim(self.desk, self.round_id))
        self.assertEqual(QualificationStore(self.source).find_winner(self.round_id).revision_id, 'R1')

        self.reopen()
        correction = correct_revision(self.source, self.round_id, 'R2')
        self.assertEqual(correction.status, 'view_only')
        self.assertEqual(correction.snapshot.mean, Fraction(9))
        self.assertEqual(QualificationStore(self.source).current(self.round_id), 'R1')

        old = sign(self.source, self.desk, self.round_id, 'R1', 'OLD')
        self.assertEqual(old.status, 'issued')
        self.assertEqual(old.report.payload.readings, original.readings)
        self.assertEqual(old.report.payload.mean, Fraction(10))
        self.assertEqual(old.report.payload.decision, 'retest')

        later = sign(self.source, self.desk, self.round_id, 'R2', 'NEW')
        self.assertEqual(later.status, 'stale')
        self.assertIsNone(later.report)
        self.assertEqual(self.report_count(), 1)

        self.reopen()
        self.close_source()
        delivery = claim(self.desk, self.round_id)
        self.assertEqual(delivery.report, old.report)
        self.assertEqual(review_claim(self.desk, self.round_id, delivery.record.report_id), delivery)
        self.assertEqual((delivery.report.request_id, delivery.report.payload.revision_id,
                          str(delivery.report.payload.mean), delivery.report.payload.decision),
                         ('OLD', 'R1', '10', 'retest'))
        self.assertEqual(self.claim_count(), 1)

    def test_second_revision_cannot_add_a_second_official_decision(self):
        original = self.original()
        self.correction(original)
        self.assertEqual(correct_revision(self.source, self.round_id, 'R2').status, 'active')
        self.assertEqual(sign(self.source, self.desk, self.round_id, 'R2', 'NEW').status, 'issued')
        self.assertEqual(sign(self.source, self.desk, self.round_id, 'R1', 'OTHER').status, 'stale')
        self.assertEqual(correct_revision(self.source, self.round_id, 'R2').status, 'view_only')
        self.assertEqual(self.report_count(), 1)
        self.assertEqual(ReportStore(self.desk).find_confirmed(self.round_id).payload.revision_id, 'R2')
        self.assertEqual(inspect_revision(self.source, self.round_id, 'R1').mean, Fraction(10))

    def test_request_number_stays_bound_after_official_report(self):
        original = self.original()
        self.correction(original)
        self.assertEqual(correct_revision(self.source, self.round_id, 'R2').status, 'active')
        issued = sign(self.source, self.desk, self.round_id, 'R2', 'NEW')
        self.assertEqual(issued.status, 'issued')
        self.reopen()
        with self.assertRaises(ValueError):
            sign(self.source, self.desk, self.round_id, 'R1', 'NEW')
        self.assertEqual(sign(self.source, self.desk, self.round_id, 'R2', 'NEW'), issued)
        self.assertEqual(self.report_count(), 1)

    def test_unpublished_reservation_yields_to_the_active_revision(self):
        """A crash between reserving and recording the decision must not wedge
        the round: once R2 is active, R2 can still become the one official
        revision, and the resumed R1 number is stale."""
        original = self.original()
        self.correction(original)
        pending = sign(self.source, self.desk, self.round_id, 'R1', 'OLD',
                       progress=self._pause('candidate_saved'))
        self.assertEqual(pending.status, 'pending')
        ledger = RequestLedger(self.desk)
        request = ledger.find('OLD')
        self.assertIsNotNone(request.candidate)
        # Reserve R1 but stop before the first-issue notice, as a hard crash
        # right after the issuance commit would.
        self.assertEqual(ReportStore(self.desk).reserve_revision('OLD', request.candidate), 'OLD')

        self.assertEqual(correct_revision(self.source, self.round_id, 'R2').status, 'active')
        self.reopen()

        old = sign(self.source, self.desk, self.round_id, 'R1', 'OLD')
        self.assertEqual(old.status, 'stale')
        new = sign(self.source, self.desk, self.round_id, 'R2', 'NEW')
        self.assertEqual(new.status, 'issued')
        self.assertEqual(new.report.payload.revision_id, 'R2')
        self.assertEqual(self.report_count(), 1)
        self.reopen()
        self.close_source()
        self.assertEqual(claim(self.desk, self.round_id).report, new.report)
