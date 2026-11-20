from dataclasses import replace

from analysis import inspect_revision
from measurements import bind_read_origin, freeze_revision
from measurements.frozen_store import FrozenRevisionStore
from rounds import open_round

from . import LabCase


class TestMeasurements(LabCase):
    def test_incomplete_or_mixed_round(self):
        first, second = self.readings()
        observed = []
        for revision, readings in [('missing', (first,)),
                                   ('mixed', (first, replace(second, round_id='Q-2')))]:
            with self.subTest(revision=revision):
                with self.assertRaises(ValueError) as captured:
                    freeze_revision(self.source, self.round_id, revision, readings)
                observed.append(type(captured.exception).__name__)
        self.reopen()
        store = FrozenRevisionStore(self.source)
        self.scenario('v2', {'specimens': ['A', 'B'], 'attempts': ['missing', 'mixed']},
                      ['ValueError', 'ValueError'], observed, [True, True],
                      [store.fetch(self.round_id, revision) is None
                       for revision in ('missing', 'mixed')],
                      ['measurements/intake.py', 'measurements/freeze.py', 'measurements/frozen_store.py'],
                      '单片和外轮读数均无法覆盖本轮两片，重开后两版均不存在')

    def test_pair_validation_and_atomic_reject(self):
        first, second = self.readings()
        foreign = replace(second, specimen_id='C', origin=bind_read_origin('C', 'C', '单/3'))
        for readings in ((first, first), (first, foreign),
                         (first, replace(second, deviation=8.5)),
                         (first, replace(second, deviation=None)),
                         (first, replace(second, origin=first.origin))):
            with self.subTest(readings=readings):
                with self.assertRaises(ValueError):
                    freeze_revision(self.source, self.round_id, 'R1', readings)
        with self.assertRaises(ValueError):
            bind_read_origin('A', 'Z', ' ')
        self.reopen()
        store = FrozenRevisionStore(self.source)
        self.assertIsNone(store.fetch(self.round_id, 'R1'))
        self.assertEqual(self.source.execute('SELECT count(*) FROM frozen_readings').fetchone()[0], 0)
        frozen = self.original(reverse=True)
        self.assertEqual(frozen.readings, (first, second))
        with self.assertRaises(ValueError):
            freeze_revision(self.source, self.round_id, 'R1', self.readings(0, 0))
        self.assertEqual(store.fetch(self.round_id, 'R1'), frozen)

    def test_correction_lineage(self):
        original = self.original()
        open_round(self.source, 'Q-2', 'A', 'B', 'QC-10', 10)
        freeze_revision(self.source, 'Q-2', 'OTHER', self.readings(round_id='Q-2'))
        with self.assertRaises(LookupError):
            freeze_revision(self.source, self.round_id, 'BAD', original.readings, parent_revision='OTHER')
        with self.assertRaises(LookupError):
            inspect_revision(self.source, self.round_id, 'OTHER')
        with self.assertRaises(ValueError):
            first, second = original.readings
            freeze_revision(self.source, self.round_id, 'R2',
                            (first, replace(second, deviation=10)), parent_revision='R1')
        correction = self.correction(original)
        self.reopen()
        store = FrozenRevisionStore(self.source)
        self.assertIsNone(store.fetch(self.round_id, 'BAD'))
        self.assertEqual(store.fetch(self.round_id, 'R1'), original)
        self.assertEqual(store.fetch(self.round_id, 'R2'), correction)
        updated = inspect_revision(self.source, self.round_id, 'R2')
        self.assertEqual(updated.link.parent_revision, 'R1')
        self.assertEqual(updated.readings[0], original.readings[0])
        self.assertEqual(updated.readings[1].origin.original_locator, ('A', '原测单/第2行'))
        self.assertEqual(updated.readings[1].origin.locator, ('勘误-R2', '勘误单/第1行'))
