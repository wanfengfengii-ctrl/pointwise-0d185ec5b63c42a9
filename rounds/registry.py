import sqlite3
from dataclasses import dataclass
from fractions import Fraction

from .rules import InspectionRule, make_inspection_rule
from .specimens import SpecimenPair, register_specimens


@dataclass(frozen=True)
class InspectionRound:
    round_id: str
    specimens: SpecimenPair
    rule: InspectionRule


class RoundRegistry:
    def __init__(self, db: sqlite3.Connection):
        self.db = db

    def initialize(self) -> None:
        self.db.execute('''
            CREATE TABLE IF NOT EXISTS inspection_rounds (
                round_id TEXT PRIMARY KEY NOT NULL,
                first_specimen TEXT NOT NULL,
                second_specimen TEXT NOT NULL CHECK (second_specimen <> first_specimen),
                rule_name TEXT NOT NULL,
                line_num TEXT NOT NULL,
                line_den TEXT NOT NULL,
                unit TEXT NOT NULL
            )
        ''')

    def add(self, record: InspectionRound) -> None:
        rule = record.rule
        with self.db:
            result = self.db.execute('''
                INSERT INTO inspection_rounds VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(round_id) DO NOTHING
            ''', (record.round_id, record.specimens.first, record.specimens.second,
                  rule.name, format(rule.threshold.numerator, 'x'),
                  format(rule.threshold.denominator, 'x'), rule.unit))
            if result.rowcount == 0:
                raise ValueError(f'round already registered: {record.round_id}')

    def get(self, round_id: str) -> InspectionRound:
        row = self.db.execute('''
            SELECT first_specimen, second_specimen, rule_name, line_num, line_den, unit
            FROM inspection_rounds WHERE round_id = ?
        ''', (round_id,)).fetchone()
        if row is None:
            raise LookupError(f'unknown round: {round_id}')
        first, second, name, numerator, denominator, unit = row
        rule = make_inspection_rule(name, Fraction(int(numerator, 16), int(denominator, 16)), unit)
        return InspectionRound(round_id, register_specimens(first, second), rule)
