from dataclasses import dataclass

from rounds.specimens import require_name


@dataclass(frozen=True)
class ReadOrigin:
    specimen_id: str
    record_id: str
    location: str
    original_record_id: str
    original_location: str

    def __post_init__(self) -> None:
        require_name(self.specimen_id, 'origin specimen')
        require_name(self.record_id, 'reading record')
        require_name(self.location, 'reading location')
        require_name(self.original_record_id, 'original record')
        require_name(self.original_location, 'original location')

    @property
    def locator(self) -> tuple[str, str]:
        return self.record_id, self.location

    @property
    def original_locator(self) -> tuple[str, str]:
        return self.original_record_id, self.original_location


def bind_read_origin(specimen_id: str, record_id: str, location: str) -> ReadOrigin:
    return ReadOrigin(specimen_id, record_id, location, record_id, location)


def inherit_read_origin(origin: ReadOrigin) -> ReadOrigin:
    return origin


def record_corrected_origin(origin: ReadOrigin, record_id: str, location: str) -> ReadOrigin:
    locator = record_id, location
    if locator in (origin.locator, origin.original_locator):
        raise ValueError('a corrected reading needs a distinct correction record location')
    return ReadOrigin(origin.specimen_id, record_id, location, *origin.original_locator)
