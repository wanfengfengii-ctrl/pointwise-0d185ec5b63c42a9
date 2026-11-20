from dataclasses import dataclass


def require_name(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{label} must be a nonblank string')
    return value


@dataclass(frozen=True)
class SpecimenPair:
    first: str
    second: str

    def __post_init__(self) -> None:
        require_name(self.first, 'first specimen')
        require_name(self.second, 'second specimen')
        if self.first == self.second:
            raise ValueError('the round needs two different specimens')


def register_specimens(first: str, second: str) -> SpecimenPair:
    return SpecimenPair(first, second)


def match_specimen_pair(
    registered: SpecimenPair, submitted: tuple[str, ...]
) -> tuple[int, int]:
    if len(submitted) != 2 or set(submitted) != {registered.first, registered.second}:
        raise ValueError('readings must cover exactly the two registered specimens')
    return submitted.index(registered.first), submitted.index(registered.second)
