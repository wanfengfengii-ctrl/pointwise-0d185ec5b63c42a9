from dataclasses import dataclass
from fractions import Fraction

from .specimens import require_name

MICROMETRE_UNIT = 'μm'


@dataclass(frozen=True)
class InspectionRule:
    name: str
    threshold: Fraction
    unit: str


def make_inspection_rule(
    name: str, threshold: int | Fraction, unit: str = MICROMETRE_UNIT
) -> InspectionRule:
    require_name(name, 'rule name')
    if unit != MICROMETRE_UNIT:
        raise ValueError('the inspection unit must be μm')
    if type(threshold) is not int and not isinstance(threshold, Fraction):
        raise ValueError('threshold must be an integer or Fraction')
    if threshold < 0:
        raise ValueError('threshold must be nonnegative')
    return InspectionRule(name, Fraction(threshold), unit)
