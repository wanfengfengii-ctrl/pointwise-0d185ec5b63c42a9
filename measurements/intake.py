from collections.abc import Iterable
from dataclasses import dataclass

from rounds.registry import InspectionRound
from rounds.specimens import match_specimen_pair, require_name

from .origins import ReadOrigin


@dataclass(frozen=True)
class Reading:
    round_id: str
    specimen_id: str
    deviation: int
    origin: ReadOrigin


def accept_reading_pair(
    record: InspectionRound, readings: Iterable[Reading]
) -> tuple[Reading, Reading]:
    submitted = tuple(readings)
    for reading in submitted:
        if not isinstance(reading, Reading) or reading.round_id != record.round_id:
            raise ValueError('each reading must belong to the target round')
        require_name(reading.specimen_id, 'reading specimen')
        if type(reading.deviation) is not int:
            raise ValueError('reading deviation must be an integer in μm')
        if not isinstance(reading.origin, ReadOrigin) or reading.origin.specimen_id != reading.specimen_id:
            raise ValueError('reading origin must identify the same specimen')
    ids = tuple(reading.specimen_id for reading in submitted)
    first, second = match_specimen_pair(record.specimens, ids)
    return submitted[first], submitted[second]
