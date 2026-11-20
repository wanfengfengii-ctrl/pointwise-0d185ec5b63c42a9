import json
import sqlite3
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

from analysis import correct_revision, initialize_analysis, inspect_revision
from handover import claim, initialize_handover, review_claim
from issuance import initialize_issuance, sign
from measurements import Reading, bind_read_origin, freeze_revision, record_corrected_origin
from rounds import open_round


class ReplyInterrupted(ConnectionError):
    pass


def prepare(source, round_id):
    open_round(source, round_id, 'A', 'B', '车间复测线', 10)
    a = Reading(round_id, 'A', 8, bind_read_origin('A', f'{round_id}-Z', '测厚记录/一'))
    b = Reading(round_id, 'B', 12, bind_read_origin('B', f'{round_id}-A', '测厚记录/二'))
    freeze_revision(source, round_id, 'R1', (b, a))
    corrected_b = Reading(round_id, 'B', 10, record_corrected_origin(
        b.origin, f'{round_id}-勘误', '更正记录/一'
    ))
    freeze_revision(source, round_id, 'R2', (a, corrected_b), parent_revision='R1')
    return inspect_revision(source, round_id, 'R1')


def interrupt_reply(stage, detail):
    if stage == 'confirmed':
        raise ReplyInterrupted('交班回包断开')
    return None


def main():
    with TemporaryDirectory() as temporary:
        root = Path(temporary)
        source_path, desk_path = root / 'analysis.sqlite', root / 'issuance.sqlite'
        with closing(sqlite3.connect(source_path)) as source, closing(sqlite3.connect(desk_path)) as desk:
            initialize_analysis(source)
            initialize_issuance(desk)
            initialize_handover(desk)
            preview = prepare(source, '早班甲')
            assert (str(preview.mean), preview.decision) == ('10', 'retest')
            print(f'早班甲 R1 预览 {preview.mean} μm，复测')

            def hold_at_candidate(stage, detail):
                return stage != 'candidate_saved'

            backlog = sign(source, desk, '早班甲', 'R1', '甲-原', progress=hold_at_candidate)
            assert backlog.status == 'pending' and claim(desk, '早班甲') is None
            assert correct_revision(source, '早班甲', 'R2').status == 'active'
            assert sign(source, desk, '早班甲', 'R1', '甲-原').status == 'stale'
            new = sign(source, desk, '早班甲', 'R2', '甲-更')
            assert new.status == 'issued'

            prepare(source, '早班乙')
            try:
                sign(source, desk, '早班乙', 'R1', '乙-原', progress=interrupt_reply)
            except ReplyInterrupted:
                correction = correct_revision(source, '早班乙', 'R2')
                assert (correction.status, str(correction.snapshot.mean)) == ('view_only', '9')
            else:
                raise RuntimeError('the demonstration did not reach the reply boundary')

        with closing(sqlite3.connect(desk_path)) as desk:
            initialize_issuance(desk)
            initialize_handover(desk)
            renewed = sign(None, desk, '早班乙', 'R1', '乙-原')
            assert renewed.status == 'issued'
            for round_id, expected in [('早班甲', ('R2', '9', 'release')),
                                       ('早班乙', ('R1', '10', 'retest'))]:
                delivery = claim(desk, round_id)
                assert delivery is not None
                payload = delivery.report.payload
                assert (payload.revision_id, str(payload.mean), payload.decision) == expected
                assert review_claim(desk, round_id, delivery.record.report_id) == delivery
                receipt = new if round_id == '早班甲' else renewed
                assert receipt.report == delivery.report
                print(json.dumps({
                    '轮': round_id,
                    '回执': delivery.report.request_id,
                    '修订': payload.revision_id,
                    '均值': {'分子': payload.mean.numerator, '分母': payload.mean.denominator,
                             '单位': payload.rule.unit},
                    '判定': payload.decision,
                    '逐片出处': [{'片': row.specimen_id, '偏差': row.deviation,
                                  '记录': row.origin.record_id, '位置': row.origin.location,
                                  '原读记录': row.origin.original_record_id}
                                 for row in delivery.origins],
                }, ensure_ascii=False))


if __name__ == '__main__':
    main()
