import json
import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

from analysis import correct_revision, initialize_analysis
from demo import prepare
from handover import claim, initialize_handover, review_claim
from issuance import initialize_issuance, sign


class ReplyLost(ConnectionError):
    pass


@contextmanager
def lab(root):
    with closing(sqlite3.connect(root / 'analysis.sqlite')) as source:
        with closing(sqlite3.connect(root / 'issuance.sqlite')) as desk:
            initialize_analysis(source)
            initialize_issuance(desk)
            initialize_handover(desk)
            yield source, desk


def exercise(root, pause_at):
    with lab(root) as (source, desk):
        prepare(source, 'Q')
        paused = sign(source, desk, 'Q', 'R1', 'old',
                      progress=lambda stage, _: stage != pause_at)
        hidden = paused.report is None and claim(desk, 'Q') is None

    with lab(root) as (source, desk):
        change = correct_revision(source, 'Q', 'R2')
        lost = False
        if pause_at == 'decided':
            def lose_reply(stage, _):
                if stage == 'confirmed':
                    raise ReplyLost('caller lost the completed reply')

            try:
                sign(source, desk, 'Q', 'R1', 'old', progress=lose_reply)
            except ReplyLost:
                lost = True
        old = sign(source, desk, 'Q', 'R1', 'old')
        new = sign(source, desk, 'Q', 'R2', 'new')

    expected_request = ('R2', 'new') if pause_at == 'candidate_saved' else ('R1', 'old')
    with closing(sqlite3.connect(root / 'issuance.sqlite')) as desk:
        initialize_issuance(desk)
        initialize_handover(desk)
        receipt = sign(None, desk, 'Q', *expected_request)
        delivery = claim(desk, 'Q')
        visible = None
        same_receipt = reviewed = False
        if delivery is not None:
            report = delivery.report
            payload = report.payload
            visible = (report.request_id, payload.revision_id, str(payload.mean), payload.decision,
                       tuple((row.specimen_id, row.deviation, row.origin.record_id,
                              row.origin.original_record_id) for row in payload.readings))
            same_receipt = receipt.status == 'issued' and receipt.report == report
            reviewed = review_claim(desk, 'Q', delivery.record.report_id) == delivery
    corrected_mean = str(change.snapshot.mean) if change.snapshot is not None else None
    return (paused.status, hidden, change.status, corrected_mean, lost,
            old.status, new.status, visible, same_receipt, reviewed)


CASES = (
    ('candidate_saved',
     ('pending', True, 'active', '9', False, 'stale', 'issued',
      ('new', 'R2', '9', 'release', (('A', 8, 'Q-Z', 'Q-Z'), ('B', 10, 'Q-勘误', 'Q-A'))), True, True)),
    ('decided',
     ('pending', True, 'view_only', '9', True, 'issued', 'stale',
      ('old', 'R1', '10', 'retest', (('A', 8, 'Q-Z', 'Q-Z'), ('B', 12, 'Q-A', 'Q-A'))), True, True)),
)


def main():
    failed = False
    with TemporaryDirectory() as temp:
        for stage, expected in CASES:
            root = Path(temp) / stage
            root.mkdir()
            actual = exercise(root, stage)
            observation = {'stage': stage, 'expected': expected, 'actual': actual}
            print(json.dumps(observation, ensure_ascii=False))
            failed |= actual != expected
    if failed:
        print('FIRST_ISSUE_REVISION: first issue and correction disagree')
    return int(failed)


if __name__ == '__main__':
    raise SystemExit(main())
