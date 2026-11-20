import sqlite3
from fractions import Fraction

from .registry import InspectionRound, RoundRegistry
from .rules import MICROMETRE_UNIT, make_inspection_rule
from .specimens import register_specimens, require_name


def open_round(
    db: sqlite3.Connection,
    round_id: str,
    first_specimen: str,
    second_specimen: str,
    rule_name: str,
    threshold: int | Fraction,
    unit: str = MICROMETRE_UNIT,
) -> InspectionRound:
    require_name(round_id, 'round identifier')
    specimens = register_specimens(first_specimen, second_specimen)
    rule = make_inspection_rule(rule_name, threshold, unit)
    record = InspectionRound(round_id, specimens, rule)
    RoundRegistry(db).add(record)
    return record
