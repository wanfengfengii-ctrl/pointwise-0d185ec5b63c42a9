import json
from dataclasses import asdict, dataclass
from fractions import Fraction

from analysis.snapshots import FrozenAnalysis
from analysis.threshold import RecheckDecision
from measurements.intake import Reading
from measurements.origins import ReadOrigin
from rounds.rules import InspectionRule, make_inspection_rule


def _ratio(value: Fraction) -> list[str]:
    return [format(value.numerator, 'x'), format(value.denominator, 'x')]


def _read_ratio(parts: list[str]) -> Fraction:
    numerator, denominator = parts
    return Fraction(int(numerator, 16), int(denominator, 16))


@dataclass(frozen=True)
class ReportPayload:
    round_id: str
    revision_id: str
    readings: tuple[Reading, Reading]
    rule: InspectionRule
    mean: Fraction
    decision: RecheckDecision

    def to_json(self) -> str:
        readings = []
        for reading in self.readings:
            readings.append({'specimen': reading.specimen_id,
                             'deviation': format(reading.deviation, 'x'),
                             'origin': asdict(reading.origin)})
        return json.dumps({
            'round': self.round_id,
            'revision': self.revision_id,
            'readings': readings,
            'rule': self.rule.name,
            'line': _ratio(self.rule.threshold),
            'unit': self.rule.unit,
            'mean': _ratio(self.mean),
            'decision': self.decision.value,
        }, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def pack_report_payload(snapshot: FrozenAnalysis) -> ReportPayload:
    return ReportPayload(snapshot.link.round_id, snapshot.link.revision_id, snapshot.readings,
                         snapshot.rule, snapshot.mean, snapshot.decision)


def unpack_report_payload(encoded: str) -> ReportPayload:
    document = json.loads(encoded)
    round_id = document['round']
    first, second = (Reading(round_id, item['specimen'], int(item['deviation'], 16),
                             ReadOrigin(**item['origin'])) for item in document['readings'])
    if first.specimen_id == second.specimen_id:
        raise ValueError('stored report must identify two different specimens')
    if any(reading.origin.specimen_id != reading.specimen_id for reading in (first, second)):
        raise ValueError('stored report has a misplaced reading origin')
    rule = make_inspection_rule(document['rule'], _read_ratio(document['line']), document['unit'])
    return ReportPayload(round_id, document['revision'], (first, second), rule,
                         _read_ratio(document['mean']), RecheckDecision(document['decision']))
